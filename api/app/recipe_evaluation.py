"""Evaluate a recipe's rules for a member and a meal. Authenticated.

The rules engine's own endpoint (scripts/api.py, mounted at /rules) evaluates a recipe on its own
and names a person only by ?user_id=, an identifier that is also the credential. This endpoint
is the one that may personalise a verdict, so it is the one that checks who is asking:

  * the caller comes from the verified token (auth.signed_in), never from the body;
  * `member_id` is loaded only for a household the caller owns (member_context.load_member_context),
    and a member that is not theirs answers exactly like one that does not exist;
  * conditions, medications and supplements are never logged, and the response reports only
    whether they were provided.

A caller may also declare context inline (no member_id). That reads nothing from the database,
so there is nothing to authorize: it is the caller's own statement about themselves.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .supabase_repo import _connect

MAX_ITEMS = 100
MAX_TEXT = 200


class MealContextBody(BaseModel):
    intended_portions: float | None = Field(default=None, gt=0, le=100)
    meal_position: str | None = Field(default=None, max_length=MAX_TEXT)
    eating_sequence: list[str] = Field(default_factory=list, max_length=MAX_ITEMS)
    accompanying_foods: list[str] = Field(default_factory=list, max_length=MAX_ITEMS)
    post_meal_activity: str | None = Field(default=None, max_length=MAX_TEXT)


class EvaluateBody(BaseModel):
    """Everything is optional: an empty body evaluates the recipe on its own.

    For the list fields, omitted (null) and [] are different on purpose: null means the caller
    did not say, [] means the caller says there are none."""

    member_id: str | None = Field(default=None, max_length=64)
    meal_context: MealContextBody | None = None
    conditions: list[str] | None = Field(default=None, max_length=MAX_ITEMS)
    medications: list[str] | None = Field(default=None, max_length=MAX_ITEMS)
    supplements: list[str] | None = Field(default=None, max_length=MAX_ITEMS)
    goals: list[str] | None = Field(default=None, max_length=MAX_ITEMS)
    activity_level: str | None = Field(default=None, max_length=MAX_TEXT)
    life_stage: str | None = Field(default=None, max_length=MAX_TEXT)
    # Equipment the caller says will be used ('cast iron skillet'). About the meal, not the member.
    equipment: list[str] | None = Field(default=None, max_length=MAX_ITEMS)


def _too_long(values) -> bool:
    return any(len(v) > MAX_TEXT for v in (values or []))


def build_context(conn, body: EvaluateBody, caller_user_id: str):
    """The EvaluationContext for a request, or None when it asks for none."""
    from evaluation_context import EvaluationContext, MealContext
    from member_context import MemberAccessDenied, load_member_context

    for field in ("conditions", "medications", "supplements", "goals", "equipment"):
        if _too_long(getattr(body, field)):
            raise HTTPException(status_code=422, detail="items must be at most %d characters" % MAX_TEXT)
    if _too_long(body.meal_context.eating_sequence if body.meal_context else None):
        raise HTTPException(status_code=422, detail="items must be at most %d characters" % MAX_TEXT)

    meal = None
    if body.meal_context is not None:
        m = body.meal_context
        meal = MealContext(intended_portions=m.intended_portions, meal_position=m.meal_position,
                           eating_sequence=tuple(m.eating_sequence),
                           accompanying_foods=tuple(m.accompanying_foods),
                           post_meal_activity=m.post_meal_activity)

    declared = {k: getattr(body, k) for k in ("conditions", "medications", "supplements", "goals",
                                              "activity_level", "life_stage", "equipment")
                if getattr(body, k) is not None}

    if body.member_id:
        try:
            ctx = load_member_context(conn, body.member_id, caller_user_id, meal_context=meal)
        except MemberAccessDenied:
            # Same answer for 'not yours' and 'does not exist'.
            raise HTTPException(status_code=404, detail="member not found") from None
        # What the owner states explicitly overrides what the database can only call unknown.
        return dataclasses.replace(ctx, **declared) if declared else ctx
    if declared or meal is not None:
        return EvaluationContext(meal_context=meal, **declared)
    return None


def evaluate(recipe_id: str, body: EvaluateBody, caller_user_id: str) -> dict:
    import evaluate_rules
    from recipe_facts import RecipeNotFound, build_recipe_facts

    with _connect() as conn:
        context = build_context(conn, body, caller_user_id)
        try:
            facts = build_recipe_facts(conn, recipe_id)
        except RecipeNotFound:
            raise HTTPException(status_code=404, detail="recipe not found") from None
        except Exception as exc:
            if getattr(exc, "sqlstate", None) in {"22P02", "22023"}:     # malformed uuid
                conn.rollback()
                raise HTTPException(status_code=404, detail="recipe not found") from None
            raise
        evaluated = evaluate_rules.evaluate_all_rules(conn, facts, context)

    return {
        "recipe_id": facts.recipe_id,
        "recipe_name": facts.recipe_name,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "context": context.as_dict() if context else None,
        "rules": [e.as_dict() for e in evaluated],
    }
