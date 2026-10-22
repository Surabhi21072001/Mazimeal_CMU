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
import time

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import ask as ask_module
from . import cache, config, content, providers
from .repo import get_repo

app = FastAPI(title="MaziMeal API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
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


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "repo": repo.name,
        "provider": config.PROVIDER,
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
