#!/usr/bin/env python3
"""Fill gaps in ingredient_nutrition from USDA FoodData Central.

The 50 seed recipes use 206 ingredients and 16 of them are missing at least
one of the 28 nutrients the database tracks. Almost none of those gaps are an
import that dropped rows: the USDA food the ingredient already points at does
not publish the nutrient. So this does two different things, and keeps them
apart in the data:

  exact       the ingredient's own usda_fdc_id reports a nutrient we have no
              row for. Written under source usda_sr_legacy, because it is the
              same food the existing rows came from.

  substitute  that food reports nothing for it, and a named, hand-chosen USDA
              entry for the same ingredient does. Written under source
              usda_fdc_substitute, at a precedence that can only fill a gap -
              never override an exact value - with the substitute's name and
              id in bioavailability_notes so the choice is reviewable and
              reversible.

Nothing is estimated and nothing is inferred from a name. A substitute has to
be listed in SUBSTITUTES below with a reason, because choosing which food
stands in for "ground beef" is a judgement about food, not a lookup. Running
this with no substitute listed fills only the exact gaps, which is the safe
default.

Usage
    python3 scripts/fill_ingredient_nutrition.py              # report, no network
    python3 scripts/fill_ingredient_nutrition.py --plan       # ask USDA, write nothing
    python3 scripts/fill_ingredient_nutrition.py --apply      # ask USDA and write
    python3 scripts/fill_ingredient_nutrition.py --all        # not just the 50
    python3 scripts/fill_ingredient_nutrition.py --suggest "ground beef"

Environment
    SUPABASE_DB_URL / MAZIMEAL_DSN   the database
    FDC_API_KEY                      a free key from
                                     https://fdc.nal.usda.gov/api-key-signup
                                     DEMO_KEY works but is limited to a few
                                     requests an hour, which is not enough to
                                     survey every ingredient in one run.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# --------------------------------------------------------------------------
# Our nutrient_id to the USDA nutrient number, chosen to match what
# ingredient_nutrition already stores so a fetched value is comparable with
# the rows beside it:
#   Energy is kcal (208), not kJ (268).
#   Vitamin_A is RAE (320), the retinol-activity measure, not IU (318).
#   Vitamin_E is alpha-tocopherol (323) - what "vitamin E" means on a label;
#     the other tocopherols are reported separately and are not it.
#   Vitamin_D is the mcg D2+D3 entry (328), not the IU one (324).
#   Vitamin_K is phylloquinone (430), the plant form with a reference value.
#   Folate is total (417), not DFE (435) or food folate (432), because total
#     is what the existing rows hold.
# --------------------------------------------------------------------------
NUTRIENTS: dict[str, tuple[str, str]] = {
    "Energy": ("208", "kcal"),
    "Macro_Protein": ("203", "g"),
    "Macro_Carbohydrate": ("205", "g"),
    "Macro_Fat": ("204", "g"),
    "Saturated_Fat": ("606", "g"),
    "Fiber": ("291", "g"),
    "Sugar": ("269", "g"),
    "Sodium": ("307", "mg"),
    "Cholesterol": ("601", "mg"),
    "Calcium": ("301", "mg"),
    "Iron": ("303", "mg"),
    "Magnesium": ("304", "mg"),
    "Phosphorus": ("305", "mg"),
    "Potassium": ("306", "mg"),
    "Zinc": ("309", "mg"),
    "Copper": ("312", "mg"),
    "Selenium": ("317", "mcg"),
    "Vitamin_C": ("401", "mg"),
    "Thiamin": ("404", "mg"),
    "Riboflavin": ("405", "mg"),
    "Niacin": ("406", "mg"),
    "Vitamin_B6": ("415", "mg"),
    "Folate": ("417", "mcg"),
    "Vitamin_B12": ("418", "mcg"),
    "Vitamin_A": ("320", "mcg"),
    "Vitamin_E": ("323", "mg"),
    "Vitamin_D": ("328", "mcg"),
    "Vitamin_K": ("430", "mcg"),
}
BY_NUMBER = {num: (name, unit) for name, (num, unit) in NUTRIENTS.items()}

# USDA unit spellings, normalised to ours. A mismatch that is not in here
# stops the row rather than being written in the wrong unit.
UNIT_ALIASES = {
    "kcal": "kcal", "g": "g", "mg": "mg",
    "ug": "mcg", "µg": "mcg", "mcg": "mcg",
    "mg_ate": "mg",       # alpha-tocopherol equivalents
    "ug_re": "mcg", "ug_rae": "mcg",
    "iu": None,           # never silently accepted: IU is not a mass
}

# --------------------------------------------------------------------------
# Substitutes, one line per ingredient, each a decision someone made.
#
# A substitute is a different USDA food used for an ingredient whose own food
# publishes nothing for the nutrients we need. It is listed here rather than
# found automatically because "which beef stands in for this beef" is a
# question about food, and a wrong answer is a plausible-looking number.
#
# Add one with --suggest, which prints the fully-profiled candidates for an
# ingredient and does not write anything.
# --------------------------------------------------------------------------
SUBSTITUTES: dict[str, tuple[int, str]] = {
    # Filled by --suggest, then reviewed. Empty until then on purpose: with no
    # entry this script fills only exact gaps, which cannot be wrong.
}

ALL_NUTRIENTS = set(NUTRIENTS)
RULE_NUTRIENTS = ("Iron", "Vitamin_C", "Calcium", "Zinc", "Folate")

CACHE = pathlib.Path(os.environ.get("FDC_CACHE", "")) if os.environ.get("FDC_CACHE") else None


# ------------------------------------------------------------------ fetching
def _cache_path(name: str) -> pathlib.Path | None:
    if CACHE is None:
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    return CACHE / (name + ".json")


def _get(path: str, params: dict, cache_name: str) -> dict:
    """One FDC request, cached on disk when FDC_CACHE is set.

    DEMO_KEY allows only a few requests an hour, so a run that re-fetches what
    it already has will exhaust the allowance before it finishes. With a cache,
    a rate limit costs the one request that hit it.
    """
    hit = _cache_path(cache_name)
    if hit is not None and hit.exists():
        return json.loads(hit.read_text())

    key = os.environ.get("FDC_API_KEY", "DEMO_KEY")
    url = "https://api.nal.usda.gov/fdc/v1/%s?%s" % (
        path, urllib.parse.urlencode({**params, "api_key": key})
    )
    last: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=45) as response:
                doc = json.load(response)
            if hit is not None:
                hit.write_text(json.dumps(doc))
            return doc
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (429, 503):
                # An hourly allowance, so a short retry is pointless; this
                # only covers a burst limit. The caller is told to wait.
                time.sleep(15 * (attempt + 1))
                continue
            raise
    raise SystemExit(
        "FDC refused the request (%s). DEMO_KEY allows a few requests an hour; "
        "set FDC_API_KEY from https://fdc.nal.usda.gov/api-key-signup" % last
    )


def food(fdc_id) -> dict:
    return _get("food/%s" % fdc_id, {}, "food_%s" % fdc_id)


def search(query: str, size: int = 25) -> dict:
    safe = "".join(ch if ch.isalnum() else "_" for ch in query)[:60]
    return _get(
        "foods/search",
        {"query": query, "dataType": "SR Legacy,Foundation", "pageSize": size},
        "search_%s" % safe,
    )


def reported(doc: dict) -> dict[str, tuple[float, str]]:
    """{our nutrient_id: (value per 100 g, our unit)} for one FDC food.

    A value whose unit is not one we recognise is left out rather than
    converted by guesswork, and an amount of None means the food lists the
    nutrient without a figure, which is not a value.
    """
    out: dict[str, tuple[float, str]] = {}
    for row in doc.get("foodNutrients", []):
        nutrient = row.get("nutrient", {})
        hit = BY_NUMBER.get(str(nutrient.get("number")))
        if not hit:
            continue
        name, our_unit = hit
        amount = row.get("amount")
        if amount is None:
            continue
        theirs = (nutrient.get("unitName") or "").strip().lower()
        if UNIT_ALIASES.get(theirs) != our_unit:
            print("    skipped %s: unit %r is not %s" % (name, theirs, our_unit))
            continue
        out[name] = (float(amount), our_unit)
    return out


# ------------------------------------------------------------------ database
def connect():
    dsn = os.environ.get("SUPABASE_DB_URL") or os.environ.get("MAZIMEAL_DSN")
    if not dsn:
        raise SystemExit("set SUPABASE_DB_URL (or MAZIMEAL_DSN)")
    import psycopg

    return psycopg.connect(dsn)


SEED_SCOPE = """
    JOIN recipes r USING (recipe_id)
    JOIN seed s ON s.ext = r.external_source_id
"""


def gaps(conn, seed_only: bool) -> list[dict]:
    """Every ingredient missing a nutrient, with how much it weighs.

    Weight is the number that decides whether a gap matters. Sixteen
    ingredients with gaps sounds alarming; three of them being 454 g of beef
    and the rest being a bay leaf is the actual situation.
    """
    scope = SEED_SCOPE if seed_only else ""
    rows = conn.execute(
        f"""
        WITH used AS (
          SELECT ri.ingredient_id,
                 count(DISTINCT ri.recipe_id) AS recipes,
                 sum(coalesce(ri.quantity_g, 0)) AS grams
            FROM recipe_ingredients ri {scope}
           GROUP BY 1)
        SELECT i.ingredient_id, i.ingredient_name, i.usda_fdc_id,
               u.recipes, u.grams,
               coalesce(array_agg(v.nutrient_id)
                          FILTER (WHERE v.nutrient_id IS NOT NULL), '{{}}') AS have
          FROM used u
          JOIN ingredients i USING (ingredient_id)
          LEFT JOIN v_ingredient_nutrition v USING (ingredient_id)
         GROUP BY 1, 2, 3, 4, 5
         ORDER BY u.grams DESC NULLS LAST
        """
    ).fetchall()

    out = []
    for ingredient_id, name, fdc_id, recipes, grams, have in rows:
        missing = ALL_NUTRIENTS - set(have or [])
        if not missing:
            continue
        out.append(
            {
                "ingredient_id": ingredient_id,
                "name": name,
                "fdc_id": fdc_id,
                "recipes": recipes,
                "grams": float(grams or 0),
                "missing": sorted(missing),
            }
        )
    return out


def load_seed(conn) -> None:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "api"))
    from app.seed_list import external_ids  # noqa: E402

    conn.execute("CREATE TEMP TABLE seed(ext text PRIMARY KEY)")
    with conn.cursor().copy("COPY seed (ext) FROM STDIN") as copy:
        for external in external_ids():
            copy.write_row([external])


def write_rows(conn, ingredient_id, values: dict, source_id: str, note: str | None) -> int:
    """Insert the given nutrients, skipping any this source already has.

    ON CONFLICT DO NOTHING against uq_in_ing_nut, so re-running is free and a
    value already recorded under this source is never quietly changed.
    """
    written = 0
    for nutrient_id, (value, unit) in sorted(values.items()):
        result = conn.execute(
            """INSERT INTO ingredient_nutrition
                   (nutrition_id, ingredient_id, nutrient_id, value_per_100g, unit,
                    usda_nutrient_code, data_quality_flag, source_id, bioavailability_notes)
               VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, 'standard', %s, %s)
            ON CONFLICT (ingredient_id, nutrient_id, source_id) DO NOTHING
            RETURNING 1""",
            (
                ingredient_id,
                nutrient_id,
                value,
                unit,
                NUTRIENTS[nutrient_id][0],
                source_id,
                note,
            ),
        ).fetchone()
        written += 1 if result else 0
    return written


# -------------------------------------------------------------------- actions
def report(items: list[dict]) -> None:
    print("%-34s %8s %7s  %s" % ("ingredient", "grams", "recipes", "missing"))
    for item in items:
        rule = [n for n in RULE_NUTRIENTS if n in item["missing"]]
        mark = "  <- rule nutrients: %s" % ", ".join(rule) if rule else ""
        print(
            "%-34s %8.0f %7d  %d of 28%s"
            % (item["name"][:34], item["grams"], item["recipes"], len(item["missing"]), mark)
        )
    print("\n%d ingredients with at least one gap" % len(items))
    print("%d of them have no usda_fdc_id" % sum(1 for i in items if not i["fdc_id"]))


def suggest(name: str) -> None:
    """Print fully-profiled USDA candidates for an ingredient, and write nothing.

    Ranked by how many of our 28 nutrients each candidate reports, because the
    whole reason to pick a substitute is that the recorded food reports too few.
    """
    doc = search(name)
    hits = doc.get("foods", [])
    if not hits:
        print("no USDA match for %r" % name)
        return
    print("candidates for %r, by how many of our 28 nutrients they report:\n" % name)
    scored = []
    for hit in hits:
        numbers = {
            str(n.get("nutrientNumber") or n.get("nutrient", {}).get("number"))
            for n in hit.get("foodNutrients", [])
        }
        scored.append((len(numbers & set(BY_NUMBER)), hit))
    for count, hit in sorted(scored, key=lambda s: -s[0])[:10]:
        print(
            "  %2d/28  %-9s %-18s %s"
            % (count, hit["fdcId"], hit.get("dataType", ""), hit["description"][:62])
        )
    print(
        "\nAdd the chosen one to SUBSTITUTES in this file:\n"
        '    "%s": (<fdcId>, "why this food"),' % name
    )


def fill(conn, items: list[dict], apply: bool) -> None:
    exact_total = substitute_total = 0
    for item in items:
        name, fdc_id = item["name"], item["fdc_id"]
        missing = set(item["missing"])
        if not fdc_id and name not in SUBSTITUTES:
            print("%-34s no usda_fdc_id and no substitute listed - skipped" % name[:34])
            continue

        print("%-34s %.0f g, missing %d" % (name[:34], item["grams"], len(missing)))

        if fdc_id:
            doc = food(fdc_id)
            available = reported(doc)
            fillable = {k: v for k, v in available.items() if k in missing}
            print("   exact      %s: %s" % (doc.get("description", "")[:46],
                                            ", ".join(sorted(fillable)) or "nothing to add"))
            if fillable and apply:
                exact_total += write_rows(
                    conn, item["ingredient_id"], fillable, "usda_sr_legacy", None
                )
            missing -= set(fillable)

        if missing and name in SUBSTITUTES:
            sub_id, why = SUBSTITUTES[name]
            doc = food(sub_id)
            available = reported(doc)
            fillable = {k: v for k, v in available.items() if k in missing}
            note = "from USDA %s (%s), not this ingredient's own food: %s" % (
                sub_id, doc.get("description", "")[:60], why,
            )
            print("   substitute %s: %s" % (doc.get("description", "")[:46],
                                            ", ".join(sorted(fillable)) or "nothing to add"))
            if fillable and apply:
                substitute_total += write_rows(
                    conn, item["ingredient_id"], fillable, "usda_fdc_substitute", note
                )
            missing -= set(fillable)

        if missing:
            print("   still blank: %s" % ", ".join(sorted(missing)))

    if apply:
        conn.commit()
        print("\nwrote %d exact rows and %d substitute rows" % (exact_total, substitute_total))
    else:
        print("\nnothing written. Re-run with --apply.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="fetch from USDA and write rows")
    parser.add_argument("--plan", action="store_true",
                        help="fetch from USDA and say what would be written, without writing")
    parser.add_argument("--all", action="store_true",
                        help="every ingredient, not just the 50 seed recipes'")
    parser.add_argument("--suggest", metavar="INGREDIENT",
                        help="print USDA candidates for one ingredient and exit")
    args = parser.parse_args(argv)

    if args.suggest:
        suggest(args.suggest)
        return 0

    with connect() as conn:
        if not args.all:
            load_seed(conn)
        items = gaps(conn, seed_only=not args.all)
        report(items)
        if not (args.apply or args.plan):
            # The report comes entirely from the database. Deciding what is
            # fillable needs one USDA request per ingredient, and DEMO_KEY
            # allows a few an hour, so the default must not spend them.
            print("\nAdd --plan to ask USDA what can be filled, or --apply to write it.")
            return 0
        print()
        fill(conn, items, apply=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
