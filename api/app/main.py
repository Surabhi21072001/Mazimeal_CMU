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
from . import admin_people, auth, cache, config, content_review, nutrition_review
from . import profile as profile_module
from . import providers, recipe_evaluation, rule_admin, rule_codes
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


class CodeBody(BaseModel):
    """A new word for the code vocabulary.

    Not reviewed, and safe not to be: no ingredient carries a new code, so no
    rule naming it can fire. Saying which foods it means is a separate,
    written-down step.
    """

    code: str
    code_type: str | None = None
    display_name: str
    description: str | None = None


class GrantBody(BaseModel):
    """Add a reviewer.

    No `granted_by`: who granted it comes from the verified token. A list of
    who may approve changes is worth nothing if the browser fills in who
    authorised each entry.
    """

    email: str
    note: str | None = None


class ContentVersionBody(BaseModel):
    """One reviewer decision on a recipe's suggestion text.

    Every field except `outcome` is optional, and a field left out is
    inherited from the current version rather than cleared - two reviewers
    working on the same recipe must not undo each other by omission.

    No reviewer and no author: both come from the verified token. A record
    whose point is who decided cannot take that from the browser.
    """

    outcome: str
    suggestions: list[dict] | None = None
    summary: dict | None = None
    rules_removed: list[str] | None = None
    status_overrides: dict | None = None
    position_overrides: dict | None = None
    headline_rule_id: str | None = None
    not_optimizable: bool | None = None
    tags: list[str] = []
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


def _suggestions_payload(
    recipe_id: str, data: dict, member_id: str, rule_ids: list[str] | None, refresh: bool
) -> dict:
    """The suggestion text for one recipe: reviewed, cached or newly written.

    A function rather than only an endpoint because the review screen needs
    exactly this, and it has to be the same text. Version 1 of a review record
    is "what the model said", so it cannot come from a second, separately
    generated payload - still less from the browser.
    """
    # Reviewed text wins over anything a model would write now. It comes from
    # recipe_content_versions, which is also what GET .../review serves, so the
    # words a cook reads and the words a reviewer approved cannot drift apart.
    if not refresh:
        reviewed = content_review.current(recipe_id)
        if reviewed:
            return {
                "recipe_id": recipe_id,
                "member_id": member_id,
                "suggestions": reviewed["suggestions"],
                "summary": reviewed["summary"],
                "source": "reviewed",
                # Which model wrote the text a reviewer then worked on. The
                # version records its inputs as recipe|rules|model, and that
                # last field is the only place the name survives an edit.
                "model": (reviewed.get("inputs_fingerprint") or "").split("|")[-1] or None,
                "reviewed_by": reviewed["review"]["reviewer"],
                "review_version": reviewed["version"],
                "disclaimer": DISCLAIMER,
            }

    key = cache.key_for(
        recipe_id, rule_ids,
        config.PROVIDER, config.LLM_MODEL,
        providers.SYSTEM + providers.SUMMARY_SYSTEM,  # either prompt changing means new text
    )
    if not refresh:
        hit = cache.get(key)
        if hit:
            # Say it came from the cache, but keep the model that wrote it.
            return {**hit["payload"], "source": "cache", "cached_at": hit["created_at"]}

    started = time.perf_counter()
    items, source, model, summary = providers.suggestions_for(data, rule_ids)
    payload = {
        "recipe_id": recipe_id,
        "member_id": member_id,
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
    return _suggestions_payload(
        recipe_id, data, request.member_id, request.rule_ids or None, refresh
    )


# The reviewed version of one recipe, for the cook screen. Open, because the
# corrected text is what a cook is meant to read - a correction that only its
# author can see is the thing this replaced. Writing it is closed.
@app.get("/api/recipes/{recipe_id}/review")
def recipe_review(recipe_id: str):
    return {"recipe_id": recipe_id, "version": content_review.current(recipe_id)}


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


@app.get("/api/admin/codes")
def admin_codes(
    field: str | None = Query(default=None, pattern="^(trigger_code|target_code|action_code)$"),
    q: str | None = None,
):
    """The code vocabulary, with what each code reaches.

    Open, like the rules themselves: the form needs it before anyone signs in,
    and the codes are published research vocabulary rather than anything
    private.
    """
    return rule_codes.codes(field=field, query=q)


@app.post("/api/admin/codes")
def admin_create_code(body: CodeBody, caller: auth.Caller = Depends(auth.signed_in)):
    return rule_codes.create_code(
        code=body.code,
        code_type=body.code_type,
        display_name=body.display_name,
        description=body.description,
        by=caller.email or caller.user_id,
    )


@app.get("/api/admin/rules/next-id")
def admin_next_rule_id(category: str):
    """The next free rule_id for a category. The prefix follows the category."""
    return rule_codes.next_rule_id(category)


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


# ------------------------------------------------------------------- profile
#
# The signed-in person's own profile, keyed on the verified token rather than
# on a uuid in the query string. The rules engine's ?user_id= still works and
# still serves the seeded demo row; this is what the app uses, so an
# identifier that never expires does not have to travel in a URL.


@app.get("/api/profile/me")
def profile_me(caller: auth.Caller = Depends(auth.signed_in)):
    return {**profile_module.me(caller.user_id), "email": caller.email}


# ------------------------------------------------- evaluate for a member
#
# The rules engine's own /rules/api/recipes/{id}/evaluate evaluates a recipe
# on its own. This one can also take the member and the meal into account, so
# it needs to know who is asking: the caller is the verified token, and a
# member_id is loaded only for a household that account owns.


@app.post("/api/recipes/{recipe_id}/evaluate")
def evaluate_for_member(
    recipe_id: str,
    body: recipe_evaluation.EvaluateBody,
    caller: auth.Caller = Depends(auth.signed_in),
):
    return recipe_evaluation.evaluate(recipe_id, body, caller.user_id)


# ------------------------------------------------------------ reviewer list
#
# Who may approve a rule change. Two sources: MAZI_ADMIN_EMAILS, which no
# request can touch, and the app_admins table, which any reviewer may edit.
# Reading the list needs to be a reviewer too - it is a list of named people,
# and there is no reason for it to be public.


@app.get("/api/admin/people")
def admin_people_list(caller: auth.Caller = Depends(auth.admin)):
    return {**admin_people.listing(auth.env_admin_emails()), "you": caller.email}


@app.post("/api/admin/people")
def admin_people_grant(body: GrantBody, caller: auth.Caller = Depends(auth.admin)):
    return admin_people.grant(body.email, by=caller.email or caller.user_id, note=body.note)


@app.delete("/api/admin/people/{email}")
def admin_people_revoke(email: str, caller: auth.Caller = Depends(auth.admin)):
    return admin_people.revoke(
        email, by=caller.email or caller.user_id, env_emails=auth.env_admin_emails()
    )


# ------------------------------------------------------------ content review
#
# The suggestion text, as versions. Reviewer-only on both sides: reading the
# record means reading an unpublished draft and every earlier decision, and
# writing one publishes text to every cook who opens the recipe.
#
# The GET writes version 1 when a recipe has never been opened, from the same
# payload the suggestions endpoint serves. That is the baseline every later
# diff is read against, which is why the server produces it rather than
# accepting one.


@app.get("/api/review/content/{recipe_id}")
def content_review_record(recipe_id: str, caller: auth.Caller = Depends(auth.admin)):
    data = repo.recipe(recipe_id)
    if not data:
        raise HTTPException(status_code=404, detail={"error": "recipe_not_found", "recipe_id": recipe_id})
    payload = _suggestions_payload(recipe_id, data, "maya", None, False)
    return {
        "record": content_review.seed(data, payload),
        "payload": payload,
        "fingerprint": content_review.fingerprint(data, payload),
        "reviewer": caller.email,
    }


@app.post("/api/review/content/{recipe_id}")
def content_review_add(
    recipe_id: str,
    body: ContentVersionBody,
    caller: auth.Caller = Depends(auth.admin),
):
    record = content_review.add_version(
        recipe_id, body.model_dump(), reviewer=caller.email or caller.user_id
    )
    return {"record": record, "reviewer": caller.email}


@app.get("/api/review/content-stats")
def content_review_stats(caller: auth.Caller = Depends(auth.admin)):
    return content_review.stats()


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
