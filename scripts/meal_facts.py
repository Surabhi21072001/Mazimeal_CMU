#!/usr/bin/env python3
"""Meal-level facts: GLY-005 (food order) and GLY-010 (walk after meals).

Neither rule is about an ingredient, and neither can be settled from the recipe, because
both concern what the member DOES: the order they eat in, and what they do afterwards. So
the recipe may call the rule, but the verdict needs the MealContext the caller supplies.
The engine never infers behaviour from the recipe.

  MEAL_MIXED    'mixed meal with starch'. Called when the recipe, or what is eaten with
                it, contains a starch. Whether the meal is MIXED, and in what order it is
                eaten, comes from meal_context.eating_sequence, never from a guess.
  BEH_POSTMEAL  'post-meal period'. Called only when the caller supplied a meal context,
                that is, said there IS a meal being eaten. A recipe alone is not a meal.
"""
from __future__ import annotations

from derived_facts import DerivedFact, recipe_starch_ingredients, starch_mentions

# Foods the rule calls 'starch' beyond the rice/pasta/potato of GLY-015: any tagged cereal
# grain (ING_GRAIN) as well.
STARCH_CODES = ("ING_PASTA", "ING_GRAIN")

# Words a caller may use in eating_sequence, grouped into the three categories the rule
# distinguishes. Anything else is ignored and reported, never guessed.
SEQUENCE_CATEGORIES = {
    "starch": {"starch", "starches", "carbohydrate", "carbohydrates", "carb", "carbs", "grain", "grains",
               "rice", "pasta", "bread", "potato", "potatoes", "noodles"},
    "protein": {"protein", "proteins", "meat", "fish", "poultry", "chicken", "egg", "eggs", "tofu",
                "legumes", "beans"},
    "vegetables": {"vegetables", "vegetable", "veg", "veggies", "non_starchy_vegetables", "salad", "greens"},
}


def classify_sequence(sequence) -> dict:
    """Positions of each category in an eating sequence.

    Returns {'starch': [i...], 'protein': [...], 'vegetables': [...], 'ignored': [tokens]}."""
    out = {"starch": [], "protein": [], "vegetables": [], "ignored": []}
    for i, token in enumerate(sequence):
        for cat, words in SEQUENCE_CATEGORIES.items():
            if token in words:
                out[cat].append(i)
                break
        else:
            out["ignored"].append(token)
    return out


def recipe_or_meal_starch(facts, context) -> list[dict]:
    """Starch in the recipe (by tag or name) or in the foods eaten with it."""
    found = []
    for ing in facts.ingredients:
        by_tag = [c for c in STARCH_CODES if c in ing.rule_codes]
        words = starch_mentions(ing.ingredient_name)
        if by_tag or words:
            found.append({"where": "recipe", "name": ing.ingredient_name,
                          "matched_on": "tag " + by_tag[0] if by_tag else "name: " + words[0]})
    meal = getattr(context, "meal_context", None)
    if meal is not None:
        for food in meal.accompanying_foods:
            words = starch_mentions(food)
            if words:
                found.append({"where": "accompanying_foods", "name": food, "matched_on": "name: " + words[0]})
    return found


def meal_candidate_facts(facts, context=None) -> list[DerivedFact]:
    out: list[DerivedFact] = []
    starch = recipe_or_meal_starch(facts, context)
    if starch:
        first = starch[0]
        out.append(DerivedFact(
            code="MEAL_MIXED", source="meal_context",
            value={"starch": [s["name"] for s in starch]},
            evidence="starch in the meal: %s (%s, %s)" % (first["name"], first["where"], first["matched_on"]),
            confidence="medium"))
    meal = getattr(context, "meal_context", None)
    if meal is not None:
        out.append(DerivedFact(
            code="BEH_POSTMEAL", source="meal_context",
            value={"meal_position": meal.meal_position},
            evidence="a meal context was supplied, so this recipe is being eaten as a meal",
            confidence="high"))
    return out
