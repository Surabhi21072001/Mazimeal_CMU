"""
Reading the real database instead of the fixtures.

Two things are worth knowing about this file:

1. **It calls the rules engine directly, not over HTTP.** `detect_rules.py` and
   `evaluate_rules.py` live in this repository and take a DB connection, so
   there is no reason to make the network carry a call between two processes
   that will be deployed as one. Their HTTP API still exists and is mounted
   beside ours for anyone testing it with Postman.

2. **Not everything is in the database yet.** Households, members and their
   targets live in the recommender schema, which this project has not loaded,
   and the recommender itself has not been delivered. Those two stay on
   fixtures, and `source` says so per payload rather than for the app as a
   whole - a screen can be truthful about one half being live.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import date
from pathlib import Path
from uuid import UUID

from . import config

# The rules engine imports its siblings by bare name (`from recipe_facts
# import ...`), which is why their own entry point runs with --app-dir scripts.
SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

DSN = os.environ.get("SUPABASE_DB_URL") or os.environ.get("MAZIMEAL_DSN", "")

# Nutrients the cook screen shows, in the order it shows them.
NUTRIENT_ORDER = [
    "Energy", "Macro_Protein", "Macro_Carbohydrate", "Macro_Fat", "Fiber",
    "Sodium", "Iron", "Vitamin_C", "Calcium", "Zinc", "Folate",
]
NUTRIENT_LABEL = {
    "Energy": "Calories", "Macro_Protein": "Protein", "Macro_Fat": "Fat",
    "Macro_Carbohydrate": "Carbohydrates", "Fiber": "Fiber", "Sodium": "Sodium",
    "Iron": "Iron", "Vitamin_C": "Vitamin C", "Calcium": "Calcium",
    "Zinc": "Zinc", "Folate": "Folate",
}

# How the rules engine's verdict reads on a cook screen. APPLICABLE means the
# rule would improve the recipe; NOT_APPLICABLE, in every branch they implement,
# means the recipe already does it - which is the nicest thing on the page.
STATUS_FROM_APPLICABILITY = {
    "APPLICABLE": "not_satisfied",
    "NOT_APPLICABLE": "satisfied",
    "NEEDS_CONTEXT": "advisory",
}


# Food.com's recipes arrived with uuid primary keys, but the screens, the
# committed fixtures and the one reviewed suggestion were all written against
# these slugs first. This is the only place the two id schemes meet: a slug in
# the url reads the real row, so every link in the repo and in docs/deploy.md
# shows live data instead of a 404.
DEMO_ALIASES = {
    "falafel-001": "907c9d1f-618e-49c9-a1fd-61be09d75559",        # Falafel
    "souvlaki-002": "53548206-5aaf-46c3-b24c-e500cd68847e",       # Souvlaki
    "sloppy-joes-003": "bfad8d75-c041-4502-8c58-015b81eb2078",    # Best Ever Sloppy Joes
    "tuna-salad-004": "a38f0788-2bdf-4ae9-a82c-509ffb2ae43f",     # Kittencal's Tuna Salad Sandwiches
    "tomato-spaghetti-005": "714e5793-d16f-4fb5-a4d0-41ba2c94ba27",  # Fresh Tomato Spaghetti Sauce
}


def _resolve(recipe_id: str) -> str | None:
    """The uuid to query, or None when the id cannot name a row.

    recipe_id is a uuid column, so an id that is not a uuid makes Postgres
    raise rather than return nothing - which would reach the caller as a 500
    for what is really a missing recipe. Checking the shape here keeps that a
    clean 404.
    """
    candidate = DEMO_ALIASES.get(recipe_id, recipe_id)
    try:
        return str(UUID(candidate))
    except (ValueError, AttributeError, TypeError):
        return None


# Words that say how an ingredient was prepared, not what it is. Matching a
# step on these would put "Cook tomatoes with oil" against every chopped thing
# in the recipe.
_MODIFIERS = {
    "chopped", "plain", "fresh", "dried", "ground", "frozen", "canned", "sliced",
    "minced", "whole", "large", "small", "cooked", "raw", "unsweetened",
    "shredded", "low-fat", "nonfat", "reduced-sodium", "condensed", "crushed",
    "diced", "grated", "boneless", "skinless", "extra", "virgin", "olive",
}


def _steps_for_rule(steps, ingredient_names):
    """The step numbers a rule should be shown against.

    This reads the method text rather than the engine's own matched_steps, for
    a reason worth writing down. The engine cites every step that contributed a
    process fact, and some of its facts are deliberately loose - garlic_heated
    falls back to "a heat verb appears anywhere" - so on one recipe it cites
    the step that heats the oil rather than the step that adds the garlic. For
    deciding a verdict that is sound. For deciding where a cook should read the
    advice it is not: the useful place for "rest the garlic" is the step where
    the garlic goes in.

    So a rule marks the steps that name the ingredient it fired on, and marks
    nothing when the method never names it - which happens, for instance when a
    recipe says "remaining marinade ingredients". A wrong mark costs more than
    a missing one.

    SPEC.md calls this approximate, and it is. The exact version needs the
    engine to say which step it means; see docs/rules_api_contract.md.
    """
    nouns = set()
    for name in ingredient_names:
        for word in re.split(r"[^a-z]+", name.lower()):
            if len(word) > 3 and word not in _MODIFIERS:
                nouns.add(word)
                # "fresh tomatoes" has to find a step that says "tomato".
                for suffix in ("es", "s"):
                    if word.endswith(suffix) and len(word) - len(suffix) > 3:
                        nouns.add(word[: -len(suffix)])
    if not nouns:
        return []
    # The first step that names it, and only that one. Tomatoes often appear
    # twice - "add tomato" and then "add tomato sauce for consistency" - and
    # marking both would print the same rule card twice in one method. Advice
    # belongs where the ingredient is first handled.
    for step in steps:
        if step["step_number"] is None:
            continue
        if any(noun in step["instruction"].lower() for noun in nouns):
            return [step["step_number"]]
    return []


def _connect():
    if not DSN:
        raise RuntimeError("SUPABASE_DB_URL is not set; run with MAZI_REPO=fixture instead.")
    import psycopg

    return psycopg.connect(DSN)


class SupabaseRepo:
    """Recipes and rules from Postgres; household and recommendations still fixtures."""

    name = "supabase"

    def __init__(self, fallback):
        # Whatever the database cannot answer yet comes from here, so a screen
        # keeps working while one half is still being built.
        self.fallback = fallback

    # ---------------------------------------------------------------- household
    def household(self):
        data = self.fallback.household()
        return {**data, "source": "fixture"} if data else None

    def recommendations(self, member_id, meal, target_nutrient):
        data = self.fallback.recommendations(member_id, meal, target_nutrient)
        return {**data, "source": "fixture"} if data else None

    # ------------------------------------------------------------------ recipe
    def recipe(self, recipe_id):
        db_id = _resolve(recipe_id)
        if db_id is None:
            return None
        with _connect() as conn:
            row = self._recipe_row(conn, db_id)
            if not row:
                return None
            ingredients = self._ingredients(conn, db_id)
            steps = self._steps(conn, db_id)
            payload = {
                # The id the caller used, not the row's, so a slug stays a slug
                # for the next request - the suggestions endpoint is keyed on it.
                "recipe_id": recipe_id,
                "db_recipe_id": str(row["recipe_id"]),
                "name": row["recipe_name"],
                "meal": row["meal_category"],
                "servings": row["servings"] or 4,
                "time_min": (row["prep_time_min"] or 0) + (row["cook_time_min"] or 0),
                "tags": list(row["dietary_tags"] or []),
                "image_url": None,
                "ingredients": ingredients,
                "nutrition_per_serving": self._nutrition(conn, db_id, row["servings"] or 4),
                "steps": steps,
                "matched_rules": self._rules(conn, db_id, ingredients, steps),
                "source": "supabase",
            }
        return payload

    @staticmethod
    def _recipe_row(conn, recipe_id):
        cur = conn.execute(
            """SELECT recipe_id, recipe_name, meal_category, servings, prep_time_min,
                      cook_time_min, dietary_tags
               FROM recipes WHERE recipe_id = %s""",
            (recipe_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return dict(zip([c.name for c in cur.description], row))

    @staticmethod
    def _ingredients(conn, recipe_id):
        cur = conn.execute(
            """SELECT ri.line_id, i.ingredient_name, ri.quantity, ri.unit, ri.measure,
                      ri.quantity_g, ri.grams_source, ri.is_optional, ri.preparation_note
               FROM recipe_ingredients ri
               JOIN ingredients i USING (ingredient_id)
               WHERE ri.recipe_id = %s
               ORDER BY ri.sequence_order NULLS LAST, i.ingredient_name""",
            (recipe_id,),
        )
        return [
            {
                "line_id": str(line_id),
                "name": name,
                "quantity": float(quantity) if quantity is not None else None,
                "unit": measure or unit,
                "grams": float(grams) if grams is not None else None,
                "grams_source": grams_source,
                "is_optional": bool(is_optional),
                "required_by_rule": None,
                "notes": note,
            }
            for line_id, name, quantity, unit, measure, grams, grams_source, is_optional, note in cur
        ]

    def _nutrition(self, conn, recipe_id, servings):
        """Published values where the dataset has them, derived from grams otherwise."""
        published = {
            nutrient: (float(value), unit)
            for nutrient, value, unit in conn.execute(
                "SELECT nutrient_id, per_serving, unit FROM recipe_nutrition WHERE recipe_id = %s",
                (recipe_id,),
            )
        }
        derived = {
            nutrient: (float(value), unit)
            for nutrient, value, unit in conn.execute(
                """SELECT n.nutrient_id,
                          SUM(n.value_per_100g * ri.quantity_g / 100.0) / NULLIF(%s, 0),
                          MIN(n.unit)
                     FROM recipe_ingredients ri
                     -- The view, not the table underneath it: once a second
                     -- source sits beside USDA there are two rows per nutrient
                     -- and summing the table would count the ingredient twice.
                     -- The view picks one by data_sources.precedence.
                     JOIN v_ingredient_nutrition n USING (ingredient_id)
                    WHERE ri.recipe_id = %s AND ri.quantity_g IS NOT NULL
                    GROUP BY n.nutrient_id""",
                (servings, recipe_id),
            )
        }

        out = []
        for nutrient in NUTRIENT_ORDER:
            if nutrient in published:
                value, unit = published[nutrient]
                source, confidence = "published", 1.0
            elif nutrient in derived:
                value, unit = derived[nutrient]
                source, confidence = "derived", 0.6
            else:
                continue
            out.append(
                {
                    "nutrient": nutrient,
                    "label": NUTRIENT_LABEL.get(nutrient, nutrient),
                    "value": round(value, 1),
                    "unit": unit,
                    "source": source,
                    "confidence": confidence,
                    "pct_of_target": None,  # the screen works this out per member
                    "top_sources": [],
                }
            )
        return out

    @staticmethod
    def _steps(conn, recipe_id):
        return [
            {
                "step_number": number,
                "title": None,
                "instruction": instruction,
                "duration_min": duration,
                "is_key_step": False,
                "ingredient_line_ids": [],
                "technique": None,
            }
            for number, instruction, duration in conn.execute(
                """SELECT step_number, instruction, duration_min FROM recipe_steps
                   WHERE recipe_id = %s ORDER BY step_number""",
                (recipe_id,),
            )
        ]

    def _rules(self, conn, recipe_id, ingredients, steps):
        """The rules engine's output, reshaped into what the screens read."""
        from detect_rules import detect_rules_from_facts
        from evaluate_rules import evaluate_rule, extract_process_facts
        from recipe_facts import RecipeNotFound, build_recipe_facts

        try:
            facts = build_recipe_facts(conn, recipe_id)
        except RecipeNotFound:
            return []

        candidates = detect_rules_from_facts(conn, facts)
        if not candidates:
            return []
        process_facts = extract_process_facts(facts)

        by_name = {item["name"].lower(): item["line_id"] for item in ingredients}
        meta = self._rule_metadata(conn, [c.rule_id for c in candidates])

        out = []
        for candidate in candidates:
            evaluated = evaluate_rule(candidate, facts, process_facts)
            info = meta.get(candidate.rule_id, {})
            status = STATUS_FROM_APPLICABILITY.get(
                str(evaluated.applicability_status), "advisory"
            )
            # do_not_automate never reaches a cook, whatever the verdict was.
            if info.get("automation_status") == "do_not_automate":
                status = "needs_review"

            # RecipeFacts already carries the codes tagged on each line, so the
            # ingredients a rule fired on are in hand - no second query.
            line_ids = [
                by_name[fact.ingredient_name.lower()]
                for fact in facts.ingredients
                if candidate.trigger_code in fact.rule_codes
                and fact.ingredient_name.lower() in by_name
            ]
            matched_names = [name for _, name in evaluated.matched_ingredients]
            step_numbers = _steps_for_rule(steps, matched_names)
            out.append(
                {
                    "rule_id": candidate.rule_id,
                    "name": candidate.rule_name,
                    "status": status,
                    "automation_status": info.get("automation_status"),
                    "evidence_tier": info.get("evidence_tier"),
                    "target_code": info.get("target_code"),
                    "target_nutrient": info.get("target_nutrient_or_outcome"),
                    # type names the primary target, for readers written
                    # against the original contract; step_numbers is additive,
                    # because a rule about resting garlic is about both the
                    # garlic line and the step that heats it.
                    "applies_to": {
                        "type": (
                            "ingredients" if line_ids
                            else "step" if step_numbers
                            else "meal"
                        ),
                        "line_ids": line_ids,
                        "step_numbers": step_numbers,
                    },
                    "engine_action": info.get("recipe_engine_instruction") or info.get("action"),
                    "why": info.get("mechanism") or evaluated.reason,
                    "source_url": info.get("source_url"),
                }
            )
        return out

    @staticmethod
    def _rule_metadata(conn, rule_ids):
        if not rule_ids:
            return {}
        cur = conn.execute(
            """SELECT rule_id, automation_status, evidence_tier, target_code,
                      target_nutrient_or_outcome, action, recipe_engine_instruction,
                      mechanism, source_url
                 FROM business_rules WHERE rule_id = ANY(%s)""",
            (list(rule_ids),),
        )
        columns = [c.name for c in cur.description]
        return {row[0]: dict(zip(columns, row)) for row in cur}

def get_supabase_repo(fallback):
    return SupabaseRepo(fallback)
