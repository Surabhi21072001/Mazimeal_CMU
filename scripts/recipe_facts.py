#!/usr/bin/env python3
"""RecipeFacts: a normalized snapshot of one recipe for rule evaluation.

RecipeFacts is the stable boundary between DATABASE DATA and BUSINESS-RULE
EVALUATION. It gathers everything the rule layer needs about a recipe into one
immutable, serializable Python object, so future evaluation code depends on this
shape rather than on the database schema.

    recipes -> recipe_ingredients -> ingredients -> ingredient_rule_tags
            -> recipe_nutrition -> recipe_steps -> RecipeFacts

It is a runtime object only. Nothing here is persisted and no new tables are
created. It reads existing MaziMeal tables and never fabricates missing values.

Nutrients are exposed with the NATIVE nutrient_id keys stored in
recipe_nutrition ('Energy', 'Macro_Protein', ...). The repository has no mapping
from those ids to the NUT_* rule codes, so none is invented here; a
nutrient-code mapping layer is a future step (see docs/phase2_recipe_facts.md).

Like detect_rules.py these functions take any DB-API 2.0 connection (psycopg2,
psycopg3 or sqlite3). Parameters use '?' placeholders, rewritten to '%s' when
the driver needs it.

CLI:
    python3 scripts/recipe_facts.py --dsn "dbname=mazimeal" <recipe_id> [...]
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field


# --------------------------------------------------------------------------
# DB-API helpers (same approach as detect_rules.py)
# --------------------------------------------------------------------------
def _paramstyle(conn) -> str:
    module = type(conn).__module__.split(".")[0]
    return "?" if module == "sqlite3" else "%s"


def _q(conn, sql: str) -> str:
    return sql if _paramstyle(conn) == "?" else sql.replace("?", "%s")


def _table_exists(conn, table: str) -> bool:
    """Return True if a table is present. Lets facts degrade gracefully when an
    optional table (recipe_nutrition, recipe_steps) is absent."""
    cur = conn.cursor()
    if _paramstyle(conn) == "?":  # sqlite
        cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (table,)
        )
    else:  # postgres
        cur.execute(_q(conn, "SELECT to_regclass(?)"), (f"public.{table}",))
        return cur.fetchone()[0] is not None
    return cur.fetchone() is not None


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class RecipeIngredientFact:
    """One ingredient line of a recipe, with the rule codes tagged on it."""
    ingredient_id: str
    ingredient_name: str
    quantity: float | None
    unit: str | None
    rule_codes: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "ingredient_id": self.ingredient_id,
            "ingredient_name": self.ingredient_name,
            "quantity": self.quantity,
            "unit": self.unit,
            "rule_codes": list(self.rule_codes),
        }


@dataclass(frozen=True)
class RecipeFacts:
    """Normalized, immutable snapshot of a recipe for rule evaluation.

    Attributes:
        recipe_id         the recipe primary key (as text)
        recipe_name       display name
        ingredients       one RecipeIngredientFact per ingredient line
        ingredient_codes  union of every rule code present in the recipe
        nutrients         {native nutrient_id: per_serving value}, NOT NUT_* codes
        instructions      joined recipe_steps text, or None if unavailable
        metadata          extra recipe fields + nutrient_units (free-form dict)
    """
    recipe_id: str
    recipe_name: str
    ingredients: tuple[RecipeIngredientFact, ...]
    ingredient_codes: frozenset[str]
    nutrients: dict[str, float] = field(default_factory=dict)
    instructions: str | None = None
    metadata: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "recipe_id": self.recipe_id,
            "recipe_name": self.recipe_name,
            "ingredients": [i.as_dict() for i in self.ingredients],
            "ingredient_codes": sorted(self.ingredient_codes),
            "nutrients": dict(self.nutrients),
            "instructions": self.instructions,
            "metadata": dict(self.metadata),
        }


class RecipeNotFound(LookupError):
    """Raised when build_recipe_facts is given an unknown recipe_id."""


# --------------------------------------------------------------------------
# Loaders (one concern each, so they are easy to test and reuse)
# --------------------------------------------------------------------------
def _load_recipe_row(conn, recipe_id):
    """Return the recipe's core + metadata columns, or None if absent.

    Selects a superset of columns and tolerates schemas that lack the optional
    ones (the SQLite test fixture only has recipe_id/recipe_name)."""
    cols_full = ("recipe_name, meal_category, servings, calories_per_serving, "
                 "data_source, recipe_description")
    cur = conn.cursor()
    try:
        cur.execute(
            _q(conn, f"SELECT {cols_full} FROM recipes WHERE recipe_id = ?"),
            (recipe_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "recipe_name": row[0],
            "meal_category": row[1],
            "servings": row[2],
            "calories_per_serving": float(row[3]) if row[3] is not None else None,
            "data_source": row[4],
            "recipe_description": row[5],
        }
    except Exception:
        # Minimal schema (tests): fall back to name only.
        conn.rollback() if hasattr(conn, "rollback") else None
        cur = conn.cursor()
        cur.execute(_q(conn, "SELECT recipe_name FROM recipes WHERE recipe_id = ?"),
                    (recipe_id,))
        row = cur.fetchone()
        if row is None:
            return None
        return {"recipe_name": row[0]}


def _load_ingredients(conn, recipe_id) -> list[RecipeIngredientFact]:
    """Load ingredient lines joined with their rule-code tags.

    One row per (ingredient, code); grouped here into one fact per ingredient.
    A LEFT JOIN keeps ingredients that carry no codes. Falls back to a query
    without quantity/unit for minimal schemas that lack those columns."""
    cur = conn.cursor()
    full_sql = _q(conn, """
        SELECT ri.ingredient_id, i.ingredient_name, ri.quantity, ri.unit, t.rule_code
        FROM recipe_ingredients ri
        JOIN ingredients i          ON i.ingredient_id = ri.ingredient_id
        LEFT JOIN ingredient_rule_tags t ON t.ingredient_id = ri.ingredient_id
        WHERE ri.recipe_id = ?
        ORDER BY i.ingredient_name, t.rule_code
        """)
    try:
        cur.execute(full_sql, (recipe_id,))
    except Exception:
        if hasattr(conn, "rollback"):
            conn.rollback()
        cur = conn.cursor()
        cur.execute(
            _q(conn, """
            SELECT ri.ingredient_id, i.ingredient_name, NULL, NULL, t.rule_code
            FROM recipe_ingredients ri
            JOIN ingredients i          ON i.ingredient_id = ri.ingredient_id
            LEFT JOIN ingredient_rule_tags t ON t.ingredient_id = ri.ingredient_id
            WHERE ri.recipe_id = ?
            ORDER BY i.ingredient_name, t.rule_code
            """),
            (recipe_id,),
        )
    # Preserve first-seen order; collect codes per ingredient.
    order: list[str] = []
    acc: dict[str, dict] = {}
    for ing_id, name, qty, unit, code in cur.fetchall():
        key = str(ing_id)
        if key not in acc:
            order.append(key)
            acc[key] = {
                "ingredient_id": key,
                "ingredient_name": name,
                "quantity": float(qty) if qty is not None else None,
                "unit": unit,
                "codes": [],
            }
        if code is not None:
            acc[key]["codes"].append(code)

    facts = []
    for key in order:
        d = acc[key]
        facts.append(
            RecipeIngredientFact(
                ingredient_id=d["ingredient_id"],
                ingredient_name=d["ingredient_name"],
                quantity=d["quantity"],
                unit=d["unit"],
                rule_codes=tuple(sorted(set(d["codes"]))),
            )
        )
    return facts


def _load_nutrients(conn, recipe_id):
    """Return ({native_nutrient_id: per_serving}, {native_nutrient_id: unit}).

    Native ids ('Energy', 'Macro_Protein', ...). These are NOT NUT_* rule codes
    and are deliberately left un-mapped. Returns empty dicts when the table is
    absent or the recipe has no nutrition rows."""
    if not _table_exists(conn, "recipe_nutrition"):
        return {}, {}
    cur = conn.cursor()
    cur.execute(
        _q(conn, """
        SELECT nutrient_id, per_serving, unit
        FROM recipe_nutrition
        WHERE recipe_id = ?
        ORDER BY nutrient_id
        """),
        (recipe_id,),
    )
    nutrients: dict[str, float] = {}
    units: dict[str, str] = {}
    for nutrient_id, per_serving, unit in cur.fetchall():
        if per_serving is None:
            continue  # never fabricate a value
        nutrients[nutrient_id] = float(per_serving)
        if unit is not None:
            units[nutrient_id] = unit
    return nutrients, units


def _load_instructions(conn, recipe_id) -> str | None:
    """Join ordered recipe_steps into one instructions string, or None.

    Returns None when the table is absent or the recipe has no steps; the
    caller treats None as 'instructions not available'."""
    if not _table_exists(conn, "recipe_steps"):
        return None
    cur = conn.cursor()
    cur.execute(
        _q(conn, """
        SELECT step_number, instruction
        FROM recipe_steps
        WHERE recipe_id = ?
        ORDER BY step_number
        """),
        (recipe_id,),
    )
    steps = [row[1] for row in cur.fetchall() if row[1]]
    if not steps:
        return None
    return "\n".join(f"{n}. {text}" for n, text in enumerate(steps, start=1))


# --------------------------------------------------------------------------
# Public builder
# --------------------------------------------------------------------------
def build_recipe_facts(conn, recipe_id) -> RecipeFacts:
    """Assemble a RecipeFacts for one recipe from existing tables.

    Raises RecipeNotFound if the recipe_id does not exist. Never fabricates
    nutrient values or instructions; missing data is simply absent/None.
    """
    recipe = _load_recipe_row(conn, recipe_id)
    if recipe is None:
        raise RecipeNotFound(f"no recipe with recipe_id={recipe_id!r}")

    ingredients = _load_ingredients(conn, recipe_id)
    ingredient_codes = frozenset(
        code for ing in ingredients for code in ing.rule_codes
    )
    nutrients, nutrient_units = _load_nutrients(conn, recipe_id)
    instructions = _load_instructions(conn, recipe_id)

    # Metadata: recipe fields beyond name, plus nutrient units so the raw
    # nutrient dict stays a clean {id: value} map.
    metadata: dict = {}
    for k in ("meal_category", "servings", "calories_per_serving",
              "data_source", "recipe_description"):
        if k in recipe and recipe[k] is not None:
            metadata[k] = recipe[k]
    if nutrient_units:
        metadata["nutrient_units"] = nutrient_units
    metadata["nutrient_id_scheme"] = "native_recipe_nutrition"  # not NUT_* codes

    return RecipeFacts(
        recipe_id=str(recipe_id),
        recipe_name=recipe["recipe_name"],
        ingredients=tuple(ingredients),
        ingredient_codes=ingredient_codes,
        nutrients=nutrients,
        instructions=instructions,
        metadata=metadata,
    )


# --------------------------------------------------------------------------
# CLI / debug output
# --------------------------------------------------------------------------
def format_facts(facts: RecipeFacts) -> str:
    lines = [
        f"Recipe:\n  {facts.recipe_name}  [{facts.recipe_id}]",
        "",
        "Ingredients:",
    ]
    if not facts.ingredients:
        lines.append("  (none)")
    for ing in facts.ingredients:
        qty = ""
        if ing.quantity is not None:
            qty = f" — {ing.quantity:g} {ing.unit or ''}".rstrip()
        lines.append(f"- {ing.ingredient_name}{qty}")
        codes = ", ".join(ing.rule_codes) if ing.rule_codes else "(no codes)"
        lines.append(f"  codes: {codes}")

    lines += ["", "Ingredient codes:"]
    lines.append("  " + (", ".join(sorted(facts.ingredient_codes)) or "(none)"))

    lines += ["", "Nutrition (native recipe_nutrition ids, per serving):"]
    if facts.nutrients:
        units = facts.metadata.get("nutrient_units", {})
        for nid in sorted(facts.nutrients):
            unit = units.get(nid, "")
            lines.append(f"  {nid}: {facts.nutrients[nid]:g} {unit}".rstrip())
    else:
        lines.append("  not available")

    lines += ["", "Instructions:"]
    lines.append("  " + (facts.instructions.replace("\n", "\n  ")
                         if facts.instructions else "not available"))

    if facts.metadata:
        meta = {k: v for k, v in facts.metadata.items() if k != "nutrient_units"}
        lines += ["", "Metadata:"]
        for k in sorted(meta):
            lines.append(f"  {k}: {meta[k]}")
    return "\n".join(lines)


def _connect(dsn: str):
    try:
        import psycopg  # psycopg3
        return psycopg.connect(dsn)
    except ImportError:
        pass
    import psycopg2
    return psycopg2.connect(dsn)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("recipe_ids", nargs="+", help="recipe_id value(s) to inspect")
    ap.add_argument("--dsn", default="dbname=mazimeal", help="libpq connection string")
    ap.add_argument("--json", action="store_true", help="emit as_dict() JSON instead")
    args = ap.parse_args(argv)

    conn = _connect(args.dsn)
    try:
        for rid in args.recipe_ids:
            try:
                facts = build_recipe_facts(conn, rid)
            except RecipeNotFound as e:
                print(f"\n{e}")
                continue
            if args.json:
                import json
                print(json.dumps(facts.as_dict(), indent=2, default=str))
            else:
                print("\n" + format_facts(facts))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
