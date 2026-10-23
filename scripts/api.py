#!/usr/bin/env python3
"""MaziMeal rule-engine HTTP API (FastAPI).

Exposes the existing Business Rule Engine over HTTP for the React frontend. It
does not change any rule semantics; it reshapes the evaluation output into a
richer, frontend-friendly JSON response.

    GET /api/recipes                      list recipes (paginated, filterable)
    GET /api/recipes/{recipe_id}/evaluate evaluate rules for one recipe

Pipeline (all existing):
    recipe_id -> RecipeFacts -> candidate detection -> process facts
              -> condition evaluation -> enriched rule metadata + matched_on

Run:
    pip install "fastapi[standard]" "psycopg[binary]"
    MAZIMEAL_DSN="dbname=mazimeal_dev" uvicorn api:app --app-dir scripts --reload
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from recipe_facts import RecipeNotFound, build_recipe_facts
from detect_rules import detect_rules_from_facts, _q
from evaluate_rules import extract_process_facts, evaluate_rule

DSN = os.environ.get("MAZIMEAL_DSN", "dbname=mazimeal")

app = FastAPI(title="MaziMeal Rule Engine API", version="1.0")


# --------------------------------------------------------------------------
# Response models
# --------------------------------------------------------------------------
class MatchedIngredient(BaseModel):
    ingredient_id: str
    name: str


class MatchedStep(BaseModel):
    step_number: int | None = None
    text: str


class MatchedOn(BaseModel):
    ingredients: list[MatchedIngredient] = []
    steps: list[MatchedStep] = []


class RuleEvaluationResponse(BaseModel):
    rule_id: str
    rule_name: str
    rule_category: str | None = None
    rule_type: str | None = None
    automation_status: str | None = None
    evidence_tier: str | None = None
    applicability_status: str

    trigger_code: str
    target_code: str | None = None
    target_nutrient_or_outcome: str | None = None

    action: str | None = None
    recipe_engine_instruction: str | None = None
    mechanism: str | None = None
    conditions_and_limits: str | None = None

    conditions_checked: list[str] = []
    conditions_passed: list[str] = []
    conditions_failed: list[str] = []

    matched_on: MatchedOn

    reason: str

    source_title: str | None = None
    source_url: str | None = None


class RecipeEvaluationResponse(BaseModel):
    recipe_id: str
    recipe_name: str
    evaluated_at: datetime
    rules: list[RuleEvaluationResponse]


class RecipeSummary(BaseModel):
    recipe_id: str
    recipe_name: str
    meal_category: str | None = None
    dietary_tags: list[str] = []
    servings: int | None = None
    calories_per_serving: float | None = None
    difficulty_level: str | None = None
    regional_origin: str | None = None
    data_source: str | None = None


class RecipeListResponse(BaseModel):
    total: int           # total rows matching the filters (ignoring paging)
    limit: int
    offset: int
    recipes: list[RecipeSummary]


# --------------------------------------------------------------------------
# Connection handling
# --------------------------------------------------------------------------
def _connect():
    try:
        import psycopg
        return psycopg.connect(DSN)
    except ImportError:
        pass
    import psycopg2
    return psycopg2.connect(DSN)


# --------------------------------------------------------------------------
# Mapping: EvaluatedRule -> response model (uses as_dict so it stays in sync)
# --------------------------------------------------------------------------
def _to_response(evaluated) -> RuleEvaluationResponse:
    d = evaluated.as_dict()
    return RuleEvaluationResponse(**d)


def _as_tag_list(tags) -> list[str]:
    """Normalize dietary_tags to a list. Postgres TEXT[] arrives as a list;
    a comma-joined string (e.g. SQLite) is split; NULL/empty becomes []."""
    if not tags:
        return []
    if isinstance(tags, (list, tuple)):
        return list(tags)
    return [t for t in str(tags).split(",") if t]


def _is_invalid_id_error(exc: Exception) -> bool:
    """True when a DB error is caused by a malformed recipe_id value (e.g. a
    string that is not valid UUID syntax). Detected by SQLSTATE/class name to
    stay driver-agnostic (psycopg2 / psycopg3)."""
    sqlstate = getattr(exc, "sqlstate", None) or getattr(
        getattr(exc, "diag", None), "sqlstate", None)
    if sqlstate in {"22P02", "22023"}:  # invalid_text_representation, invalid_parameter_value
        return True
    text = f"{type(exc).__name__}: {exc}".lower()
    return "invalid input syntax for type uuid" in text or "invalidtextrepresentation" in text


# --------------------------------------------------------------------------
# Endpoint
# --------------------------------------------------------------------------
@app.get("/api/recipes/{recipe_id}/evaluate", response_model=RecipeEvaluationResponse)
def evaluate_recipe(recipe_id: str) -> RecipeEvaluationResponse:
    conn = _connect()
    try:
        try:
            facts = build_recipe_facts(conn, recipe_id)
        except RecipeNotFound:
            raise HTTPException(status_code=404,
                                detail=f"recipe not found: {recipe_id}")
        except Exception as exc:
            # A malformed recipe_id (e.g. not valid UUID syntax) makes the DB
            # raise a data-type error. Treat it as "not found" rather than 500.
            if _is_invalid_id_error(exc):
                if hasattr(conn, "rollback"):
                    conn.rollback()
                raise HTTPException(status_code=404,
                                    detail=f"recipe not found: {recipe_id}")
            raise

        candidates = detect_rules_from_facts(conn, facts)
        process_facts = extract_process_facts(facts)
        evaluated = [evaluate_rule(c, facts, process_facts) for c in candidates]

        return RecipeEvaluationResponse(
            recipe_id=facts.recipe_id,
            recipe_name=facts.recipe_name,
            evaluated_at=datetime.now(timezone.utc),
            rules=[_to_response(e) for e in evaluated],
        )
    finally:
        conn.close()


@app.get("/api/recipes", response_model=RecipeListResponse)
def list_recipes(
    limit: int = Query(50, ge=1, le=200, description="max rows to return"),
    offset: int = Query(0, ge=0, description="rows to skip (pagination)"),
    meal_category: str | None = Query(
        None, description="exact filter: Breakfast | Lunch | Dinner | Snack"),
    search: str | None = Query(
        None, min_length=1, description="case-insensitive substring of recipe_name"),
) -> RecipeListResponse:
    """List recipes with pagination and optional filters.

    Reads the recipes table directly (soft-deleted rows excluded). Returns a
    lightweight summary per recipe plus the total match count so the frontend
    can page. Use a returned recipe_id with /api/recipes/{id}/evaluate.
    """
    conn = _connect()
    try:
        # Build WHERE from the optional filters. Parameterized, no interpolation.
        where = ["deleted_at IS NULL"]
        params: list = []
        if meal_category:
            where.append("meal_category = ?")
            params.append(meal_category)
        if search:
            # lower(...) LIKE lower(...) is case-insensitive on both Postgres
            # and SQLite (ILIKE is Postgres-only).
            where.append("lower(recipe_name) LIKE lower(?)")
            params.append(f"%{search}%")
        where_sql = " AND ".join(where)

        cur = conn.cursor()
        cur.execute(_q(conn, f"SELECT count(*) FROM recipes WHERE {where_sql}"),
                    tuple(params))
        total = cur.fetchone()[0]

        cur = conn.cursor()
        cur.execute(
            _q(conn, f"""
            SELECT recipe_id, recipe_name, meal_category, dietary_tags, servings,
                   calories_per_serving, difficulty_level, regional_origin, data_source
            FROM recipes
            WHERE {where_sql}
            ORDER BY recipe_name
            LIMIT ? OFFSET ?
            """),
            tuple(params) + (limit, offset),
        )
        recipes = []
        for row in cur.fetchall():
            (rid, name, meal, tags, servings, cals,
             difficulty, origin, source) = row
            recipes.append(RecipeSummary(
                recipe_id=str(rid),
                recipe_name=name,
                meal_category=meal,
                dietary_tags=_as_tag_list(tags),
                servings=servings,
                calories_per_serving=float(cals) if cals is not None else None,
                difficulty_level=difficulty,
                regional_origin=origin,
                data_source=source,
            ))

        return RecipeListResponse(
            total=total, limit=limit, offset=offset, recipes=recipes)
    finally:
        conn.close()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
