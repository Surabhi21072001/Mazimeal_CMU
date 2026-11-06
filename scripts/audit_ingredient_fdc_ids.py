#!/usr/bin/env python3
"""Check that each ingredient's usda_fdc_id points at the food it is named for.

Found while filling nutrition gaps: `sesame seeds` carries fdcId 167557, which
USDA calls "Snacks, rice cakes, brown rice, sesame seed". Its 24 nutrients are
therefore rice cakes, not sesame seeds - which is worse than the gaps the fill
script was looking for, because a wrong value looks exactly like a right one
and a missing value at least announces itself.

The check is crude on purpose: does a content word of the ingredient's name
appear anywhere in the USDA description? That cannot confirm a mapping is
right - "Snacks, rice cakes, brown rice, sesame seed" does contain "sesame" -
so the output is a list to read, not a verdict. It is sorted by grams, because
a wrong mapping on 90 g of a recipe matters and one on a bay leaf does not.

What it reports per ingredient:

  ok        a content word of the name appears in the description
  SUSPECT   none does, so the two are probably different foods

Nothing is written. Correcting a mapping means changing usda_fdc_id and
re-importing that ingredient's nutrition, which is a separate decision per
ingredient.

Usage
    python3 scripts/audit_ingredient_fdc_ids.py            # the 50 recipes'
    python3 scripts/audit_ingredient_fdc_ids.py --all      # every ingredient

Environment
    SUPABASE_DB_URL / MAZIMEAL_DSN, FDC_API_KEY, optional FDC_CACHE
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fill_ingredient_nutrition import connect, food, load_seed  # noqa: E402

# Words that say how a food is prepared or packaged rather than what it is, so
# their presence on both sides is not evidence of anything.
NOISE = {
    "of", "the", "and", "or", "a", "an", "in", "with", "to", "for",
    "fresh", "dried", "ground", "raw", "cooked", "canned", "frozen", "chopped",
    "sliced", "minced", "whole", "large", "small", "medium", "firm", "soft",
    "boneless", "skinless", "extra", "virgin", "light", "dark", "low", "fat",
    "free", "unsalted", "salted", "sweet", "hot", "mix", "sauce", "powder",
    "thread", "threads", "leaf", "leaves", "seed", "seeds", "zest",
}


def stem(word: str) -> str:
    """Enough of a stem to match a recipe's singular against USDA's plural.

    USDA names the food, recipes name the thing you buy: "carrot" against
    "Carrots, raw", "lemon" against "Lemons, raw, without peel". Without this
    every such pair reads as a mismatch, and a check that cries wolf forty
    times is one nobody reads.
    """
    for suffix in ("ies", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return word


def words(text: str) -> set[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    return {stem(w) for w in cleaned.split() if len(w) > 2 and w not in NOISE}


def verdict(name: str, description: str) -> str:
    """ok or SUSPECT.

    Only "no word in common at all" is reported. An earlier version also
    flagged a match that fell after the first comma, on the theory that USDA
    puts the food first and qualifications after. That theory is wrong: USDA
    writes "Category, specific, qualifier", so "Peppers, jalapeno, raw" has
    the category first and matching on the tail is the normal case. That rule
    produced thirty-six flags, every one of them correct data.

    What it therefore cannot catch is the case that prompted the script:
    sesame seeds mapped to "Snacks, rice cakes, brown rice, sesame seed" does
    share the word "sesame". No cheap text rule separates that from a real
    match, so the mapping list needs a human pass; this only removes the
    ingredients where nothing lines up at all.
    """
    ours = words(name)
    if not ours:
        return "ok"  # nothing but noise words to go on; not a finding
    return "ok" if ours & words(description) else "SUSPECT"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", action="store_true",
                        help="every ingredient, not just the 50 seed recipes'")
    args = parser.parse_args(argv)

    scope = "" if args.all else """
        JOIN recipes r USING (recipe_id)
        JOIN seed s ON s.ext = r.external_source_id
    """

    with connect() as conn:
        if not args.all:
            load_seed(conn)
        rows = conn.execute(
            f"""
            WITH used AS (
              SELECT ri.ingredient_id, sum(coalesce(ri.quantity_g, 0)) AS grams,
                     count(DISTINCT ri.recipe_id) AS recipes
                FROM recipe_ingredients ri {scope}
               GROUP BY 1)
            SELECT i.ingredient_name, i.usda_fdc_id, u.grams, u.recipes,
                   (SELECT count(*) FROM v_ingredient_nutrition v
                     WHERE v.ingredient_id = i.ingredient_id) AS nutrients
              FROM used u JOIN ingredients i USING (ingredient_id)
             WHERE i.usda_fdc_id IS NOT NULL
             ORDER BY u.grams DESC NULLS LAST
            """
        ).fetchall()

    print("%d ingredients have a usda_fdc_id\n" % len(rows))
    counts = {"ok": 0, "SUSPECT": 0}
    findings = []
    for name, fdc_id, grams, recipes, nutrients in rows:
        doc = food(fdc_id)
        description = doc.get("description", "")
        call = verdict(name, description)
        counts[call] += 1
        if call != "ok":
            findings.append((call, name, fdc_id, float(grams or 0), nutrients, description))

    print("%-8s %-26s %9s %8s %6s  %s"
          % ("verdict", "ingredient", "fdcId", "grams", "nutr", "what USDA calls it"))
    for call, name, fdc_id, grams, nutrients, description in sorted(
        findings, key=lambda f: (-f[3], f[1])
    ):
        print("%-8s %-26s %9s %8.0f %4d/28  %s"
              % (call, name[:26], fdc_id, grams, nutrients, description[:58]))

    print("\nok %d, SUSPECT %d" % (counts["ok"], counts["SUSPECT"]))
    print("Nothing written. A wrong mapping needs usda_fdc_id changed and that "
          "ingredient's nutrition re-imported.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
