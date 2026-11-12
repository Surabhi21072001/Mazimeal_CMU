"""Shared builders for the derived-fact tests: an in-memory recipe database and RecipeFacts.

No network, no PostgreSQL. The SQLite schema carries only the columns the detector and the
fact builder read, which is what the existing fixtures in tests/test_rules.py also do.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import recipe_facts  # noqa: E402

# Trigger codes and the rules that name them, copied from schema/seed/business_rules.sql.
RULES = {
    "GLY-002": "MACRO_CARB", "GLY-003": "MACRO_CARB", "GLY-004": "MACRO_CARB", "GLY-009": "MACRO_CARB",
    "GLY-005": "MEAL_MIXED", "GLY-010": "BEH_POSTMEAL", "GLY-011": "MACRO_AVAIL_CARB",
    "GLY-015": "PROC_COOL_REHEAT", "INH-011": "MACRO_FAT_LOW", "SYN-012": "PROC_COOKWARE",
    "INH-012": "RULE_CONFLICT",
}


def build_db(rules=RULES, recipes=None, extra_rules=()) -> sqlite3.Connection:
    """recipes: {recipe_id: {'name', 'servings', 'ingredients': [(name, (codes...))],
    'steps': [text...] | None, 'nutrition': {nutrient_id: (value, unit)} | None}}"""
    conn = sqlite3.connect(":memory:")
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE recipes (recipe_id TEXT PRIMARY KEY, recipe_name TEXT);
        CREATE TABLE ingredients (ingredient_id TEXT PRIMARY KEY, ingredient_name TEXT);
        CREATE TABLE recipe_ingredients (recipe_id TEXT, ingredient_id TEXT, quantity REAL, unit TEXT);
        CREATE TABLE ingredient_rule_tags (ingredient_id TEXT, rule_code TEXT);
        CREATE TABLE business_rules (rule_id TEXT, rule_name TEXT, trigger_code TEXT,
                                     automation_status TEXT, is_active INTEGER);
        CREATE TABLE recipe_nutrition (recipe_id TEXT, nutrient_id TEXT, per_serving REAL, unit TEXT);
        CREATE TABLE recipe_steps (recipe_id TEXT, step_number INTEGER, instruction TEXT);
        CREATE TABLE rule_code_components (composite_code TEXT, component_code TEXT);
    """)
    for rid, trig in list(rules.items()) + list(extra_rules):
        c.execute("INSERT INTO business_rules VALUES (?,?,?,?,1)", (rid, "Rule " + rid, trig, "recipe_safe"))
    seen = {}
    for rid, spec in (recipes or {}).items():
        c.execute("INSERT INTO recipes VALUES (?,?)", (rid, spec.get("name", rid)))
        for name, codes in spec.get("ingredients", []):
            iid = seen.setdefault(name, "i-%d" % len(seen))
            if not c.execute("SELECT 1 FROM ingredients WHERE ingredient_id=?", (iid,)).fetchone():
                c.execute("INSERT INTO ingredients VALUES (?,?)", (iid, name))
                for code in codes:
                    c.execute("INSERT INTO ingredient_rule_tags VALUES (?,?)", (iid, code))
            c.execute("INSERT INTO recipe_ingredients VALUES (?,?,1,'unit')", (rid, iid))
        for n, text in enumerate(spec.get("steps") or [], start=1):
            c.execute("INSERT INTO recipe_steps VALUES (?,?,?)", (rid, n, text))
        for nid, (val, unit) in (spec.get("nutrition") or {}).items():
            c.execute("INSERT INTO recipe_nutrition VALUES (?,?,?,?)", (rid, nid, val, unit))
    conn.commit()
    return conn


def facts_for(ingredients=(), steps=None, nutrition=None, servings=None, codes=(), equipment=(), metadata=None):
    """A RecipeFacts built directly (no database). `ingredients` are names; `codes` the union
    of ingredient codes. `nutrition` is {nutrient_id: (value, unit)}."""
    ings = tuple(recipe_facts.RecipeIngredientFact(
        ingredient_id="i-%d" % i, ingredient_name=n, quantity=None, unit=None, rule_codes=())
        for i, n in enumerate(ingredients))
    nutrients = {k: float(v[0]) for k, v in (nutrition or {}).items()}
    meta = {"nutrient_units": {k: v[1] for k, v in (nutrition or {}).items()},
            "nutrition_basis": "per_serving"}
    if servings is not None:
        meta["servings"] = servings
    meta.update(metadata or {})
    text = "\n".join("%d. %s" % (n, t) for n, t in enumerate(steps, start=1)) if steps else None
    kwargs = {}
    if equipment:
        kwargs["equipment"] = tuple(equipment)
    return recipe_facts.RecipeFacts(
        recipe_id="r-x", recipe_name="Test Recipe", ingredients=ings,
        ingredient_codes=frozenset(codes), nutrients=nutrients, instructions=text, metadata=meta, **kwargs)
