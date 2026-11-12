#!/usr/bin/env python3
"""Deterministic rule detection for a recipe.

First iteration of the Phase 2 optimization layer. Given a recipe, it finds the
business rules that apply, purely from stored data:

    recipe -> recipe_ingredients -> ingredient_rule_tags -> trigger codes
           -> business_rules whose trigger_code matches -> detected rules

A trigger code may also be composite: rule_code_components lists the codes
that must ALL be present for it to fire. That is for rules whose trigger is a
pairing - SYN-007 needs a legume and a grain, SYN-009 an allium with a grain
or legume - which a tag cannot express, since a tag says one thing about one
ingredient. A composite is never tagged on an ingredient; its components are,
in the ordinary way. A database without rule_code_components behaves exactly
as it did before.

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
    # Enrichment metadata loaded in the same candidate query (no N+1). All
    # optional so existing constructors/tests that pass only the core fields
    # keep working unchanged.
    rule_category: str | None = None
    rule_type: str | None = None
    evidence_tier: str | None = None
    target_code: str | None = None
    target_nutrient_or_outcome: str | None = None
    action: str | None = None
    recipe_engine_instruction: str | None = None
    mechanism: str | None = None
    conditions_and_limits: str | None = None
    source_title: str | None = None
    source_url: str | None = None
    # Which facts called this rule, and where they came from. 'ingredient' for the original
    # tag mechanism, otherwise the DerivedFact sources (recipe_nutrition, recipe_process, ...).
    trigger_source: str | None = None
    matched_facts: tuple = ()          # tuple[DerivedFact, ...]

    def as_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "automation_status": self.automation_status,
            "trigger_code": self.trigger_code,
            "reason": self.reason,
        }


# Columns pulled for each candidate rule, in SELECT order. Kept in one place so
# the query and the row->DetectedRule mapping stay in sync.
_RULE_METADATA_COLUMNS = (
    "rule_id", "rule_name", "automation_status", "trigger_code",
    "rule_category", "rule_type", "evidence_tier", "target_code",
    "target_nutrient_or_outcome", "action", "recipe_engine_instruction",
    "mechanism", "conditions_and_limits", "source_title", "source_url",
)


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


def _composite_codes(conn, present: dict[str, list[str]]) -> dict[str, list[str]]:
    """Composite codes satisfied by the codes already present, with the
    ingredients that satisfied them.

    A composite fires only when every one of its components is present. The
    ingredient list is the union of the ingredients that matched each
    component, so the reason a rule fired names the pairing rather than one
    half of it.

    Returns {} when rule_code_components does not exist, which keeps this
    working against the SQLite fixture and any database where the migration
    has not run.
    """
    if not present:
        return {}

    cur = conn.cursor()
    try:
        cur.execute(_q(conn, """
            SELECT composite_code, component_code
            FROM rule_code_components
            ORDER BY composite_code, component_code
        """))
        rows = cur.fetchall()
    except Exception:
        if hasattr(conn, "rollback"):
            conn.rollback()
        return {}

    components: dict[str, list[str]] = {}
    for composite, component in rows:
        components.setdefault(composite, []).append(component)

    satisfied: dict[str, list[str]] = {}
    for composite, needed in components.items():
        if not all(code in present for code in needed):
            continue
        # Keep the components grouped, so the reason can say which ingredient
        # played which part instead of listing them all in one heap.
        names: list[str] = []
        for code in needed:
            for name in present[code]:
                label = "%s (%s)" % (name, code)
                if label not in names:
                    names.append(label)
        satisfied[composite] = names
    return satisfied


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
def _summarise_fact(fact) -> str:
    """One short phrase naming a derived fact, for a candidate's reason."""
    bits = [fact.code]
    if isinstance(fact.value, dict):
        step = fact.value.get("instruction_step")
        role = fact.value.get("role")
        if step is not None:
            bits.append("step %s" % step)
        if role:
            bits.append(str(role))
    elif fact.value is not None:
        bits.append("= %s%s" % (fact.value, (" " + fact.unit) if fact.unit else ""))
    if fact.evidence:
        bits.append("(%s)" % fact.evidence)
    return " ".join(bits)


def detect_rules_from_facts(conn, facts: RecipeFacts, context=None,
                            include_derived: bool = True) -> list[DetectedRule]:
    """Return the active business rules triggered by a RecipeFacts.

    A rule is triggered when its trigger_code is established by an ingredient tag, by a
    composite of tagged ingredients, or (new) by a DERIVED fact: recipe nutrition, a
    cooking process, the intended meal or the equipment (see scripts/derived_facts.py).
    Only is_active rules are returned. Preferred entry point once a RecipeFacts exists.

    `context` (an EvaluationContext) is optional and only used to derive meal and user
    facts. `include_derived=False` gives the original ingredient-only behaviour exactly.
    Engine-level rules (INH-012) are never triggered here; they run after evaluation.
    """
    ingredient_codes = _codes_to_ingredients(facts)

    # Derived facts, grouped by the trigger code they establish.
    derived_by_code: dict[str, list] = {}
    if include_derived:
        from derived_facts import collect_candidate_facts
        for fact in collect_candidate_facts(facts, context):
            derived_by_code.setdefault(fact.code, []).append(fact)

    # No tagged ingredients and no derived facts -> no applicable rules.
    if not ingredient_codes and not derived_by_code:
        return []

    # Composite codes are not tagged; they are satisfied by their components.
    # Added after the direct codes so a composite cannot mask one.
    composites = _composite_codes(conn, ingredient_codes)
    codes = {**ingredient_codes, **composites}
    # A derived code is present with no ingredient names; it must not overwrite one.
    for code in derived_by_code:
        codes.setdefault(code, [])

    placeholders = ", ".join("?" for _ in codes)
    params = tuple(codes.keys())

    # Load the full metadata in the SAME query (no N+1). Fall back to the core
    # four columns for minimal schemas (e.g. the SQLite test fixture) that lack
    # the metadata columns.
    full_cols = ", ".join(_RULE_METADATA_COLUMNS)
    cur = conn.cursor()
    try:
        cur.execute(
            _q(conn, f"""
            SELECT {full_cols}
            FROM business_rules
            WHERE is_active = TRUE AND trigger_code IN ({placeholders})
            ORDER BY rule_id
            """),
            params,
        )
        rows = cur.fetchall()
        full = True
    except Exception:
        if hasattr(conn, "rollback"):
            conn.rollback()
        cur = conn.cursor()
        cur.execute(
            _q(conn, f"""
            SELECT rule_id, rule_name, automation_status, trigger_code
            FROM business_rules
            WHERE is_active = TRUE AND trigger_code IN ({placeholders})
            ORDER BY rule_id
            """),
            params,
        )
        rows = cur.fetchall()
        full = False

    detected: list[DetectedRule] = []
    for row in rows:
        if full:
            meta = dict(zip(_RULE_METADATA_COLUMNS, row))
        else:
            rid, rname, auto, trig = row
            meta = {"rule_id": rid, "rule_name": rname,
                    "automation_status": auto, "trigger_code": trig}
        trigger_code = meta["trigger_code"]
        from_ingredients = ingredient_codes.get(trigger_code, [])
        derived = derived_by_code.get(trigger_code, [])
        ingredients = codes.get(trigger_code, []) if (from_ingredients or trigger_code in composites) else []
        ing_list = ", ".join(sorted(set(ingredients)))
        if trigger_code in composites:
            # Say that every part was present, because "contains an ingredient
            # tagged X" would be false: nothing is tagged with a composite.
            reason = (
                f"recipe satisfies every component of {trigger_code}"
                + (f": {ing_list}" if ing_list else "")
            )
        elif from_ingredients:
            reason = (
                f"recipe contains ingredient tagged {trigger_code}"
                + (f" ({ing_list})" if ing_list else "")
            )
        else:
            reason = ""
        if derived:
            shown = "; ".join(_summarise_fact(f) for f in derived[:3])
            more = " (+%d more)" % (len(derived) - 3) if len(derived) > 3 else ""
            derived_reason = "recipe-derived fact %s: %s%s" % (trigger_code, shown, more)
            reason = (reason + "; " + derived_reason) if reason else derived_reason

        # Evidence: which facts called the rule, and where each came from. Ingredient
        # evidence is one fact per tagged ingredient, in the same shape as derived facts.
        from derived_facts import DerivedFact
        matched = [DerivedFact(code=trigger_code, source="ingredient", value=name,
                               evidence="ingredient tagged %s" % trigger_code, confidence="high")
                   for name in sorted(set(from_ingredients))]
        if trigger_code in composites:
            matched = [DerivedFact(code=trigger_code, source="ingredient", value=name,
                                   evidence="component of composite %s" % trigger_code, confidence="high")
                       for name in sorted(set(ingredients))]
        matched += derived
        sources = []
        for f in matched:
            if f.source not in sources:
                sources.append(f.source)
        detected.append(DetectedRule(reason=reason, trigger_source="+".join(sources) or None,
                                     matched_facts=tuple(matched), **meta))
    return detected


def detect_rules(conn, recipe_id, context=None) -> list[DetectedRule]:
    """Return the active business rules triggered by this recipe.

    Unchanged public API: accepts a recipe_id, builds a RecipeFacts internally,
    and delegates to detect_rules_from_facts. `context` is optional.
    """
    try:
        facts = build_recipe_facts(conn, recipe_id)
    except RecipeNotFound:
        return []
    return detect_rules_from_facts(conn, facts, context)


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
