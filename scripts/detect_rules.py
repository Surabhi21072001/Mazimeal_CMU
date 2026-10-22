#!/usr/bin/env python3
"""Deterministic rule detection for a recipe.

First iteration of the Phase 2 optimization layer. Given a recipe, it finds the
business rules that apply, purely from stored data:

    recipe -> recipe_ingredients -> ingredient_rule_tags -> trigger codes
           -> business_rules whose trigger_code matches -> detected rules

No LLM, no recipe modification, no conflict resolution, no optimization. It only
proves that the stored rules can be matched against existing recipe data.

The recipe's ingredient data now comes from a RecipeFacts object (see
scripts/recipe_facts.py), the shared boundary between database data and rule
evaluation. detect_rules(conn, recipe_id) still works unchanged: it builds the
facts internally. detect_rules_from_facts(conn, facts) is the preferred entry
point when the caller already has a RecipeFacts.

The functions take any DB-API 2.0 connection (psycopg2, psycopg3 or sqlite3),
so they run against real Postgres in the app and against a lightweight fixture
database in tests. Parameters use the '?' placeholder, rewritten to '%s' when
the driver needs it.

CLI:
    python3 scripts/detect_rules.py --dsn "dbname=mazimeal" <recipe_id> [...]
    python3 scripts/detect_rules.py --dsn "dbname=mazimeal" --show-facts <recipe_id>
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from recipe_facts import RecipeFacts, RecipeNotFound, build_recipe_facts, format_facts


@dataclass(frozen=True)
class DetectedRule:
    rule_id: str
    rule_name: str
    automation_status: str | None
    trigger_code: str
    reason: str

    def as_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "automation_status": self.automation_status,
            "trigger_code": self.trigger_code,
            "reason": self.reason,
        }


def _paramstyle(conn) -> str:
    """Return the placeholder this connection's driver expects."""
    module = type(conn).__module__.split(".")[0]
    # sqlite3 uses '?'; psycopg2/psycopg use '%s'.
    return "?" if module == "sqlite3" else "%s"


def _q(conn, sql: str) -> str:
    """Rewrite '?' placeholders to the connection's style."""
    ph = _paramstyle(conn)
    return sql if ph == "?" else sql.replace("?", "%s")

# For each rule code present in the recipe, collect the ingredient names that
# carry it, so the detection reason can name them.
# Example: {"ING_GARLIC": ["garlic cloves"], "ING_TOMATO": ["tomatoes"]}
def _codes_to_ingredients(facts: RecipeFacts) -> dict[str, list[str]]:
    codes: dict[str, list[str]] = {}
    for ing in facts.ingredients:
        for code in ing.rule_codes:
            codes.setdefault(code, []).append(ing.ingredient_name)
    return codes


def recipe_trigger_codes(conn, recipe_id) -> dict[str, list[str]]:
    """Back-compat helper: {code: [ingredient_name, ...]} for a recipe.

    Preserved for existing callers/tests. Now derives its answer from
    RecipeFacts instead of running its own query.
    """
    try:
        facts = build_recipe_facts(conn, recipe_id)
    except RecipeNotFound:
        return {}
    return _codes_to_ingredients(facts)


# Output: DetectedRule(rule_id, rule_name, automation_status, trigger_code, reason)
# Sample Output: BIO-002  recipe_safe   Crush garlic and rest    reason: ...tagged ING_GARLIC (garlic cloves)
# BIO-003  recipe_safe   Cook tomatoes with oil   reason: ...tagged ING_TOMATO (tomatoes)
# SYN-011  conditional   Fermented dairy cultures reason: ...tagged ING_YOGURT (plain yogurt)
# ...
def detect_rules_from_facts(conn, facts: RecipeFacts) -> list[DetectedRule]:
    """Return the active business rules triggered by a RecipeFacts.

    A rule is triggered when its trigger_code is one of the codes tagged on an
    ingredient in the recipe. Only is_active rules are returned. Preferred entry
    point once a RecipeFacts has been built.
    """
    # No tagged ingredients -> no applicable rules.
    codes = _codes_to_ingredients(facts)
    if not codes:
        return []

    # Find active rules whose trigger_code is present in the recipe.
    cur = conn.cursor()
    placeholders = ", ".join("?" for _ in codes)
    cur.execute(
        _q(conn, f"""
        SELECT rule_id, rule_name, automation_status, trigger_code
        FROM business_rules
        WHERE is_active = TRUE
          AND trigger_code IN ({placeholders})
        ORDER BY rule_id
        """),
        tuple(codes.keys()),
    )

    detected: list[DetectedRule] = []
    for rule_id, rule_name, automation_status, trigger_code in cur.fetchall():
        ingredients = codes.get(trigger_code, [])
        ing_list = ", ".join(sorted(set(ingredients)))
        reason = (
            f"recipe contains ingredient tagged {trigger_code}"
            + (f" ({ing_list})" if ing_list else "")
        )
        detected.append(
            DetectedRule(
                rule_id=rule_id,
                rule_name=rule_name,
                automation_status=automation_status,
                trigger_code=trigger_code,
                reason=reason,
            )
        )
    return detected


def detect_rules(conn, recipe_id) -> list[DetectedRule]:
    """Return the active business rules triggered by this recipe's ingredients.

    Unchanged public API: accepts a recipe_id, builds a RecipeFacts internally,
    and delegates to detect_rules_from_facts. Semantics identical to before.
    """
    try:
        facts = build_recipe_facts(conn, recipe_id)
    except RecipeNotFound:
        return []
    return detect_rules_from_facts(conn, facts)


def recipe_name(conn, recipe_id) -> str | None:
    cur = conn.cursor()
    cur.execute(_q(conn, "SELECT recipe_name FROM recipes WHERE recipe_id = ?"), (recipe_id,))
    row = cur.fetchone()
    return row[0] if row else None


def _connect(dsn: str):
    try:
        import psycopg  # psycopg3
        return psycopg.connect(dsn)
    except ImportError:
        pass
    import psycopg2  # fall back
    return psycopg2.connect(dsn)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("recipe_ids", nargs="+", help="recipe_id value(s) to inspect")
    ap.add_argument("--dsn", default="dbname=mazimeal", help="libpq connection string")
    ap.add_argument("--show-facts", action="store_true",
                    help="print the RecipeFacts object before the detected rules")
    args = ap.parse_args(argv)

    conn = _connect(args.dsn)
    try:
        for rid in args.recipe_ids:
            # Preferred flow: build facts once, then detect from them.
            try:
                facts = build_recipe_facts(conn, rid)
            except RecipeNotFound:
                print(f"\nRecipe: (unknown)  [{rid}]")
                print("  (no such recipe)")
                continue

            if args.show_facts:
                print("\n" + format_facts(facts))

            print(f"\nRecipe: {facts.recipe_name}  [{facts.recipe_id}]")
            rules = detect_rules_from_facts(conn, facts)
            if not rules:
                print("  (no applicable rules)")
                continue
            print("Detected:")
            for r in rules:
                print(f"  {r.rule_id}  [{r.automation_status}]  {r.rule_name}")
                print(f"      Reason: {r.reason}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
