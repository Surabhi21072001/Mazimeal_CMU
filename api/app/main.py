"""
The MaziMeal backend.

It exists for the two things the database cannot do on its own: serving the
rule matches on a recipe, and writing the suggestion text that goes with them.
Everything else (recipes, nutrition, logging) stays with the functions the
other team already wrote.

Run it:

    api/.venv/bin/uvicorn app.main:app --reload --port 8000 --app-dir api

Endpoints follow api/SPEC.md. Every payload carries `source` so the frontend
can say whether it is looking at live data or a fixture.
"""
import sys
import time
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import ask as ask_module
from . import auth, cache, config, content, nutrition_review, providers, rule_admin
from .repo import get_repo

app = FastAPI(title="MaziMeal API", version="0.1.0")


def _mount_rules_engine() -> str | None:
    """Serve the rules engine's own API beside ours, in the same process.

    It is a separate FastAPI app owned by the rules workstream, and it keeps
    its own paths under /rules so their Postman collection still works. One
    process means one cold start on a free host, and no network hop when this
    app asks the engine a question - it imports it directly.
    """
    scripts = Path(__file__).resolve().parent.parent.parent / "scripts"
    if not (scripts / "api.py").exists():
        return None
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    try:
        import api as rules_api  # scripts/api.py

        app.mount("/rules", rules_api.app)
        return "/rules"
    except Exception as exc:  # a broken import there must not take this app down
        print(f"rules engine not mounted: {exc}")
        return None


RULES_MOUNT = _mount_rules_engine()
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_origin_regex=config.CORS_ORIGIN_REGEX,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

repo = get_repo()


DISCLAIMER = (
    "Written from the matched rules. Nutrition figures come from the database, "
    "not from a model."
)


class ReviewRequest(BaseModel):
    status: str
    reviewer: str


class AskRequest(BaseModel):
    question: str
    member_id: str = "maya"


class SuggestionRequest(BaseModel):
    member_id: str = "maya"
    rule_ids: list[str] = []


class RuleRequestBody(BaseModel):
    """A proposed change to one rule.

    There is no `submitted_by`: who is proposing comes from the verified
    token, not from here. A client-supplied author on an audit record is not
    an author.
    """

    kind: str = "update"
    rule_id: str
    proposed: dict = {}
    note: str | None = None


class DecisionBody(BaseModel):
    approve: bool
    note: str | None = None


class NutritionVerdict(BaseModel):
    """A person's judgement on whether a recipe's numbers can be right.

    No ratio and no reviewer: both are taken from the database and the token
    when the row is written, so a verdict always records what was actually on
    screen and who actually decided.
    """

    verdict: str
    reason: str | None = None


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "repo": repo.name,
        "provider": config.PROVIDER,
        "rules_engine": RULES_MOUNT or "not mounted",
        "model": config.LLM_MODEL if config.PROVIDER == "local" else None,
    }


@app.get("/api/household")
def household():
    data = repo.household()
    if not data:
        raise HTTPException(status_code=404, detail={"error": "household_not_found"})
    return {**data, "source": repo.name}


@app.get("/api/recommendations")
def recommendations(
    member_id: str = Query("maya"),
    meal: str = Query("Lunch"),
    target_nutrient: str | None = Query(None),
    limit: int = Query(5, ge=1, le=20),
):
    data = repo.recommendations(member_id, meal, target_nutrient)
    if not data:
        raise HTTPException(status_code=404, detail={"error": "no_recommendations"})
    results = data.get("results", [])[:limit]
    return {**data, "results": results, "source": repo.name}


@app.get("/api/seed-recipes")
def seed_recipes():
    """The recipes the team works against, from the spreadsheet that names them.

    Declared before /api/recipes/{recipe_id} so "seed-recipes" is not read as a
    recipe id - FastAPI matches in definition order.
    """
    data = repo.seed_recipes()
    return {**data, "repo": repo.name}


@app.get("/api/recipes/{recipe_id}")
def recipe(recipe_id: str):
    data = repo.recipe(recipe_id)
    if not data:
        raise HTTPException(status_code=404, detail={"error": "recipe_not_found", "recipe_id": recipe_id})
    return {**data, "source": repo.name}


@app.post("/api/recipes/{recipe_id}/suggestions")
def suggestions(recipe_id: str, request: SuggestionRequest, refresh: bool = Query(False)):
    """
    The first visit to a recipe pays for the model; later visits are served
    from the cache. Pass ?refresh=true to rewrite anyway, which is how the
    model comparison is run.
    """
    data = repo.recipe(recipe_id)
    if not data:
        raise HTTPException(status_code=404, detail={"error": "recipe_not_found", "recipe_id": recipe_id})

    # Reviewed text wins over anything a model would write now.
    if not refresh:
        reviewed = content.approved(recipe_id)
        if reviewed:
            return {
                "recipe_id": recipe_id,
                "member_id": request.member_id,
                "suggestions": reviewed["suggestions"],
                "summary": reviewed.get("summary"),
                "source": "reviewed",
                "model": reviewed.get("model"),
                "reviewed_by": reviewed.get("reviewed_by"),
                "disclaimer": DISCLAIMER,
            }

    key = cache.key_for(
        recipe_id, request.rule_ids or None,
        config.PROVIDER, config.LLM_MODEL,
        providers.SYSTEM + providers.SUMMARY_SYSTEM,  # either prompt changing means new text
    )
    if not refresh:
        hit = cache.get(key)
        if hit:
            # Say it came from the cache, but keep the model that wrote it.
            return {**hit["payload"], "source": "cache", "cached_at": hit["created_at"]}

    started = time.perf_counter()
    items, source, model, summary = providers.suggestions_for(data, request.rule_ids or None)
    payload = {
        "recipe_id": recipe_id,
        "member_id": request.member_id,
        "suggestions": items,
        "summary": summary,
        "source": source,
        "model": model,
        "generated_in_ms": round((time.perf_counter() - started) * 1000),
        "disclaimer": DISCLAIMER,
    }
    if source != "template" or config.PROVIDER == "template":
        cache.put(key, payload)
    return payload


@app.post("/api/recipes/{recipe_id}/ask")
def ask(recipe_id: str, request: AskRequest):
    """
    A free question about one recipe. Nothing here is cached or reviewed: the
    question is not known in advance, so the answer is grounded in the recipe,
    its rules and the member's targets, and refused when it strays.
    """
    recipe = repo.recipe(recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail={"error": "recipe_not_found", "recipe_id": recipe_id})

    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail={"error": "empty_question"})

    household = repo.household() or {}
    member = next(
        (m for m in household.get("members", []) if m["member_id"] == request.member_id),
        None,
    )

    result = ask_module.answer(recipe, member, question)
    return {"recipe_id": recipe_id, "question": question, **result, "disclaimer": DISCLAIMER}


@app.get("/api/content/review-queue")
def review_queue(status: str = Query(content.PENDING)):
    """What a reviewer still has to read. Written by api/pregenerate.py."""
    items = content.queue(status)
    return {"status": status, "count": len(items), "items": items}


@app.post("/api/content/{recipe_id}/review")
def review(recipe_id: str, request: ReviewRequest):
    if request.status not in (content.APPROVED, content.REJECTED, content.PENDING):
        raise HTTPException(status_code=400, detail={"error": "bad_status", "status": request.status})
    entry = content.review(recipe_id, request.status, request.reviewer)
    if not entry:
        raise HTTPException(status_code=404, detail={"error": "no_content_for_recipe", "recipe_id": recipe_id})
    return entry


@app.post("/api/cache/clear")
def clear_cache():
    """For the model comparison: drop everything written by a previous run."""
    return {"cleared": cache.clear()}


# --------------------------------------------------------------------- rule admin
#
# Reading the rules needs no account: they are published research with their
# sources, and the screens already show them on every recipe. Proposing a
# change needs a verified Supabase account. Approving one needs that account to
# be on MAZI_ADMIN_EMAILS, which the server reads from its own environment.


@app.get("/api/admin/me")
def admin_me(caller: auth.Caller = Depends(auth.signed_in)):
    """Who the server thinks is calling. The admin page asks before it renders."""
    return caller.as_json()


@app.get("/api/admin/rules/summary")
def admin_rules_summary():
    return rule_admin.summary()


@app.get("/api/admin/rules")
def admin_rules(
    q: str | None = None,
    category: str | None = None,
    status: str | None = None,
    reach: str | None = Query(default=None, pattern="^(reachable|unreachable)$"),
    active: bool | None = None,
    limit: int = 200,
):
    items = rule_admin.rules(
        query=q, category=category, status=status, reach=reach, active=active, limit=limit
    )
    return {"count": len(items), "items": items, "categories": rule_admin.categories()}


@app.get("/api/admin/rules/{rule_id}")
def admin_rule(rule_id: str):
    found = rule_admin.rule(rule_id)
    if not found:
        raise HTTPException(status_code=404, detail={"error": "no_such_rule", "rule_id": rule_id})
    return found


@app.get("/api/admin/rule-requests")
def admin_rule_requests(
    status: str = "pending",
    limit: int = 100,
    caller: auth.Caller = Depends(auth.admin),
):
    items = rule_admin.requests(status=status, limit=limit)
    return {"status": status, "count": len(items), "items": items, "reviewer": caller.email}


@app.post("/api/admin/rule-requests")
def admin_submit_rule_request(
    body: RuleRequestBody,
    caller: auth.Caller = Depends(auth.signed_in),
):
    return rule_admin.submit(
        kind=body.kind,
        rule_id=body.rule_id,
        proposed=body.proposed,
        note=body.note,
        by=caller.email or caller.user_id,
    )


# ---------------------------------------------------------- nutrition review
#
# Whether a recipe's nutrition is plausible, which is not the same question as
# whether its suggestion text is good. Reading the queue is open - the numbers
# and their disagreement are already on the cook screen - and recording a
# verdict needs a verified account, because the point of the record is that it
# says who decided.


@app.get("/api/review/nutrition")
def nutrition_queue():
    return nutrition_review.queue()


@app.get("/api/review/nutrition/{recipe_id}/history")
def nutrition_history(recipe_id: str):
    return {"recipe_id": recipe_id, "items": nutrition_review.history(recipe_id)}


@app.post("/api/review/nutrition/{recipe_id}")
def nutrition_verdict(
    recipe_id: str,
    body: NutritionVerdict,
    caller: auth.Caller = Depends(auth.signed_in),
):
    return nutrition_review.record(
        recipe_id=recipe_id,
        verdict=body.verdict,
        reason=body.reason,
        reviewer=caller.email or caller.user_id,
    )


@app.post("/api/admin/rule-requests/{request_id}/decide")
def admin_decide_rule_request(
    request_id: str,
    body: DecisionBody,
    caller: auth.Caller = Depends(auth.admin),
):
    return rule_admin.decide(
        request_id=request_id,
        approve=body.approve,
        by=caller.email,
        note=body.note,
    )
