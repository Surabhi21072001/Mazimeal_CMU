#!/usr/bin/env python3
"""Tag ingredients so the idle rules can fire.

A rule reaches a recipe only through ingredient_rule_tags: the engine joins
recipe_ingredients to that table and matches the tag against
business_rules.trigger_code. Nothing else selects a rule - not the nutrient a
rule targets, not the recipe's own nutrition.

On this database 44 trigger codes are needed and 11 were tagged, so 41 of 54
rules fired on nothing. The 11 are exactly the 11 in INGREDIENT_CODE_MAP in
scripts/import_rules.py: the gap is not a failed algorithm, it is a keyword
table that was written for eleven codes.

This adds two more ways to produce a tag, and refuses the cases where neither
is honest.

  by name      a food class the ingredient's name identifies: legumes, seeds,
               tea and coffee, the high-oxalate greens. Include and exclude
               substrings, in the same shape as the existing table, because
               "green bean" is not a legume and "coffee bean" is not either.

  by nutrient  a food class defined by how much of a nutrient the ingredient
               carries: "vitamin C-rich produce", "calcium-rich dairy". The
               threshold is the FDA's own: 20% of the Daily Value in 21 CFR
               101.9 is what lets a label say "excellent source"
               (21 CFR 101.54). Measured per typical serving, which is both
               the FDA's basis and the only one that works here - per 100 g,
               dried thyme is the richest source of iron in the database and
               basil the richest source of vitamin K, and you use a gram of
               either.

               typical_serving_g is upstream data of varying realism, and that
               shows at the margin: parsley is recorded as a 60 g serving, a
               full cup, which puts it at 3.7 mg of iron against a 3.6 mg
               threshold. It is a genuine plant iron source, so the tag is not
               wrong, but a rule firing on a garnish is weak. Raising the
               threshold would fix it and make the definition no longer
               citable, which is the worse trade.

Refused, with the reason in REFUSED below: rules that must not be automated,
rules about supplements, and rules whose trigger is a property of the meal
rather than of an ingredient. A tag cannot say "this meal is
carbohydrate-dominant", and pretending otherwise would make a rule fire on
every recipe containing rice.

Two codes in that list are composites rather than refusals.
ING_LEGUME_GRAIN and ING_ALLIUM_GRAIN_LEGUME need two classes present
together, which rule_code_components now expresses and detect_rules.py
evaluates. They are never tagged directly; their components - ING_LEGUME,
ING_GRAIN, ING_ALLIUM, ING_GRAIN_LEGUME - are tagged here as usual.

A code is skipped entirely when every rule on it is do_not_automate. Where a
code carries both kinds - NUT_CALCIUM has one of each - it is still tagged,
because evaluate_rules.py "does not route by automation_status; it is carried
through on each result". Detection and action are separate there, which is the
right split: a do_not_automate rule becomes visible to a person without
becoming something the engine does.

Usage
    python3 scripts/tag_ingredients.py            # what it would tag
    python3 scripts/tag_ingredients.py --apply    # write the tags
    python3 scripts/tag_ingredients.py --show NUT_VITC   # list one code's matches

Environment
    SUPABASE_DB_URL / MAZIMEAL_DSN
"""
from __future__ import annotations

import argparse
import os

# --------------------------------------------------------------------------
# FDA Daily Values, 21 CFR 101.9(c)(8)(iv), adults and children 4+.
# --------------------------------------------------------------------------
DAILY_VALUE = {
    "Vitamin_C": 90.0,     # mg
    "Vitamin_K": 120.0,    # mcg
    "Vitamin_D": 20.0,     # mcg
    "Vitamin_A": 900.0,    # mcg RAE
    "Calcium": 1300.0,     # mg
    "Iron": 18.0,          # mg
    "Zinc": 11.0,          # mg
    "Folate": 400.0,       # mcg
}

# 21 CFR 101.54: "high", "rich in" and "excellent source of" all mean 20% or
# more of the DV per serving. "Good source" is 10%. The rules say "rich" and
# "-rich", so 20% is the matching definition rather than a chosen number.
EXCELLENT_SOURCE = 0.20

PLANT = (
    "Vegetables and Vegetable Products",
    "Fruits and Fruit Juices",
    "Legumes and Legume Products",
    "Cereal Grains and Pasta",
    "Nut and Seed Products",
    "Breakfast Cereals",
)
PRODUCE = ("Vegetables and Vegetable Products", "Fruits and Fruit Juices")
DAIRY = ("Dairy and Egg Products",)

# --------------------------------------------------------------------------
# By nutrient. Each entry says which nutrients must reach the threshold and,
# where the rule distinguishes them, which food categories qualify.
# --------------------------------------------------------------------------
BY_NUTRIENT: dict[str, dict] = {
    "NUT_VITC": {
        "nutrients": ["Vitamin_C"],
        "categories": PRODUCE,
        "why": 'SYN-001 and INH-006 say "vitamin C-rich produce". Produce only: '
               "fortified drinks and supplements are a different question.",
    },
    "NUT_VITK": {
        "nutrients": ["Vitamin_K"],
        "categories": PRODUCE + ("Fats and Oils",),
        "why": 'SYN-005 says "leafy greens or other vitamin K foods". Oils are '
               "included because several are among the richest sources.",
    },
    "NUT_VITD": {
        "nutrients": ["Vitamin_D"],
        "categories": None,
        "why": 'SYN-004 says "vitamin D-containing food". No category filter, '
               "because the few foods that have it are fish, eggs and fortified "
               "products and there is no reason to prefer one.",
    },
    "NUT_CALCIUM": {
        "nutrients": ["Calcium"],
        "categories": DAIRY,
        "why": 'SYN-010 says "calcium-rich dairy or fortified alternative". '
               "Restricted to dairy: without it, baking powder is the richest "
               "calcium source in the database.",
    },
    "NUT_NONHEME_IRON": {
        "nutrients": ["Iron"],
        "categories": PLANT,
        "why": 'SYN-001 and SYN-008 say "plant iron source", and SYN-001 adds '
               '"do not apply to heme iron as if equivalent". Plant categories '
               "only, so liver and beef are excluded by construction.",
    },
    "NUT_CAROTENOIDS": {
        "nutrients": ["Vitamin_A"],
        "categories": PRODUCE,
        "why": 'SYN-002 says "carotenoid-rich vegetables". Carotenoids are the '
               "plant form of vitamin A; liver carries preformed retinol, which "
               "is why this is produce only.",
    },
    "NUT_PROVITAMIN_A": {
        "nutrients": ["Vitamin_A"],
        "categories": PRODUCE,
        "why": 'SYN-006 says "orange or dark-green vegetables". Provitamin A is '
               "carotenoid by definition, so the same filter applies.",
    },
    "ING_VITC_FOLATE_VEG": {
        "nutrients": ["Vitamin_C", "Folate"],
        "categories": PRODUCE,
        "why": "The code names both nutrients, so both have to reach the "
               "threshold rather than either.",
    },
}

# --------------------------------------------------------------------------
# By name. Same include/exclude shape as INGREDIENT_CODE_MAP in
# scripts/import_rules.py; the exclusions are the false positives that table's
# comment warns about, checked against the 559 ingredient names in this
# database rather than imagined.
# --------------------------------------------------------------------------
LEGUMES = [
    "lentil", "chickpea", "garbanzo", "black bean", "kidney bean", "pinto bean",
    "navy bean", "cannellini", "lima bean", "fava bean", "butter bean",
    "soybean", "soy bean", "edamame", "tofu", "tempeh", "split pea",
    "black-eyed pea", "blackeyed pea", "mung bean", "refried bean",
    "white bean", "red bean", "adzuki", "miso",
    # Found by --candidates, not by writing the list from memory: USDA files
    # both of these under Legumes and the keyword list had missed them.
    "chili bean", "baked bean",
]
NOT_LEGUMES = [
    "green bean", "string bean", "wax bean", "vanilla bean", "coffee bean",
    "cocoa bean", "bean sprout", "bean thread", "jelly bean",
]
GRAINS = [
    "rice", "wheat", "oat", "barley", "rye", "quinoa", "millet", "bulgur",
    "farro", "couscous", "cornmeal", "polenta", "grits", "semolina",
    "bran", "flour", "pasta", "spaghetti", "macaroni", "noodle", "bread",
    "tortilla", "cracker", "matzo",
]
NOT_GRAINS = [
    "rice vinegar", "rice wine", "wild rice soup", "flour tortilla chip",
    "almond flour", "coconut flour", "rice paper", "breadfruit",
]
SEEDS = [
    "sesame seed", "sunflower seed", "pumpkin seed", "flaxseed", "flax seed",
    "chia seed", "poppy seed", "hemp seed", "tahini", "sesame",
]
NOT_SEEDS = ["sesame oil", "sesame dressing", "rice cake"]
ALLIUM = ["garlic", "onion", "shallot", "leek", "scallion", "chive"]
NOT_ALLIUM = ["powder", "salt", "onion soup mix"]

BY_NAME: dict[str, dict] = {
    "ING_LEGUME": {
        "include": LEGUMES, "exclude": NOT_LEGUMES,
        "why": "BIO-008 and BIO-013 are about soaking, sprouting and cooking "
               "legumes. The exclusions are real names in this database: a green "
               "bean is a pod vegetable and a vanilla bean is not a bean.",
    },
    "ING_GRAIN_LEGUME": {
        "include": LEGUMES + GRAINS, "exclude": NOT_LEGUMES + NOT_GRAINS,
        "why": "BIO-009 says \"whole grains or legumes\", BIO-010 \"whole-grain "
               "or legume batter\", GLY-008 \"grain or legume\" - all three read "
               "as either, so the union is what they mean.",
    },
    "ING_ALLIUM": {
        "include": ALLIUM, "exclude": NOT_ALLIUM,
        "why": "A component of the composite ING_ALLIUM_GRAIN_LEGUME, not a "
               "trigger of its own. Broader than the existing ING_GARLIC, "
               "which is garlic only, because SYN-009 says garlic or onion. "
               "Powders and salts are excluded for the same reason the "
               "existing ING_GARLIC excludes them: the rule is about the "
               "fresh matrix.",
    },
    "ING_GRAIN": {
        "include": GRAINS, "exclude": NOT_GRAINS,
        "why": "A component of the composite ING_LEGUME_GRAIN. Grains alone - "
               "ING_GRAIN_LEGUME is the union with legumes and so cannot be "
               'used to express "legume and grain".',
    },
    "ING_SEED": {
        "include": SEEDS, "exclude": NOT_SEEDS,
        "why": "BIO-014 is about seeds. Sesame oil is excluded because pressing "
               "removes the matrix the rule is about, and rice cake because that "
               "is how sesame seeds came to be mapped to a snack.",
    },
    "CMP_PHYTATE": {
        "include": ["bran", "whole wheat", "whole grain", "oat", "brown rice"]
                   + LEGUMES + SEEDS,
        "exclude": NOT_LEGUMES + NOT_SEEDS,
        "why": 'INH-002 names its own trigger: "unprocessed bran, grains, '
               'legumes, seeds". Phytate is not one of the 28 nutrients stored, '
               "so the food class is the only available handle.",
    },
    "CMP_OXALATE": {
        "include": ["spinach", "swiss chard", "beet green", "rhubarb", "sorrel",
                    "purslane", "amaranth leaf"],
        "exclude": [],
        "why": 'INH-004 says "high-oxalate food such as spinach". Oxalate is not '
               "stored either, and the high-oxalate foods are a short, settled "
               "list rather than a threshold.",
    },
    "BEV_TEA_COFFEE": {
        "include": ["tea", "coffee", "espresso"],
        "exclude": ["tea towel", "steak", "teaspoon", "butter", "creamer"],
        "why": "INH-001 is about tannins with iron. The exclusions are substring "
               'accidents - "steak" and "teaspoon" both contain "tea".',
    },
    "BEV_SSB": {
        "include": ["soda", "cola", "soft drink", "sweetened beverage",
                    "fruit punch", "lemonade", "sports drink", "energy drink"],
        "exclude": ["baking soda", "soda water", "club soda", "soda bread"],
        "why": "GLY-010 is about sugar-sweetened beverages. Baking soda and soda "
               "bread are the substring accidents here.",
    },
}

# --------------------------------------------------------------------------
# Not tagged, and why. Printed by the script so the list is visible rather
# than implied by absence.
# --------------------------------------------------------------------------
REFUSED: dict[str, str] = {
    "CALC_NET_CARB": "GLY-014 is do_not_automate.",
    "CMP_FIBER_PHYTATE": "INH-010 is do_not_automate, and is about supplements.",
    "NUT_ZINC": "INH-009 is do_not_automate, and is about high-dose zinc "
                "supplements. Its own limits note says food-level zinc is not "
                "the issue.",
    "MACRO_CARB": "GLY-002, 003, 004 and 009 trigger on a "
                  '"carbohydrate-dominant meal" - a property of the recipe, not '
                  "of an ingredient. A tag would make them fire on anything "
                  "containing rice.",
    "MACRO_AVAIL_CARB": "GLY-011 triggers on a high-carbohydrate serving, which "
                        "is again the recipe rather than an ingredient.",
    "MACRO_FAT_LOW": "INH-011 triggers on a fat-free meal, which no single "
                     "ingredient can establish.",
    "CARB_REFINED": "GLY-001 needs a glycaemic index, and its own limits say not "
                    "to use a single database value as universal. Nothing in the "
                    "database carries GI.",
    "BEH_POSTMEAL": "BEH-001 is about what the user does after eating.",
    "MED_ACID_SUPPRESS": "INH-008 is about medication.",
    "MEAL_MIXED": "An engine concept, not a food.",
    "RULE_CONFLICT": "An engine concept, not a food.",
    "ING_RIPE_FRUIT": "GLY-008 distinguishes ripe from unripe, which is a state "
                      "the ingredient name does not carry and the recipe does "
                      "not record.",
    "ING_COOKED_STARCH": "GLY-007 is about starch that has been cooked and "
                         "cooled. Tagging potato would claim every raw potato is "
                         "cooked starch; this needs recipe_steps.",
    "ING_RAW_EGG_WHITE": "BIO-015 is about raw egg white specifically, and "
                         '"egg white" in a recipe is usually about to be cooked.',
    "ING_ALLIUM_GRAIN_LEGUME":
        "A composite, since migration 009. Never tagged directly: it fires "
        "when ING_ALLIUM and ING_GRAIN_LEGUME are both present, which is what "
        'SYN-009\'s "garlic/onion plus grain or legume" means. Tagging it as a '
        "union would fire on 46 of the 50 recipes while only 17 contain both.",
    "ING_LEGUME_GRAIN":
        "A composite, since migration 009. Fires when ING_LEGUME and ING_GRAIN "
        'are both present - SYN-007\'s "legumes and grains". As a union tag it '
        "would fire on 25 recipes of which 5 contain both.",
}


# --------------------------------------------------------------------------
# USDA's own food_category, used to propose names a keyword list has missed.
#
# It is not a replacement for the lists. The categories are botanical and the
# rules are about food as it is prepared, so the two disagree in both
# directions: USDA files soy sauce and peanut butter under Legumes, and
# BIO-008 ("soak and cook legumes") applies to neither, while "Nut and Seed
# Products" contains walnuts and pecans, which are nuts. But it is a good
# candidate generator, and it found two legumes this list had missed.
# --------------------------------------------------------------------------
CATEGORY_HINT = {
    "ING_LEGUME": "Legumes and Legume Products",
    "ING_SEED": "Nut and Seed Products",
    "ING_GRAIN": "Cereal Grains and Pasta",
    "ING_ALLIUM": "Vegetables and Vegetable Products",
    "CMP_OXALATE": "Vegetables and Vegetable Products",
    "BEV_SSB": "Beverages",
    "BEV_TEA_COFFEE": "Beverages",
}


def connect():
    dsn = os.environ.get("SUPABASE_DB_URL") or os.environ.get("MAZIMEAL_DSN")
    if not dsn:
        raise SystemExit("set SUPABASE_DB_URL (or MAZIMEAL_DSN)")
    import psycopg

    return psycopg.connect(dsn)


def name_matches(conn, spec: dict) -> list[tuple]:
    """Ingredients whose name contains an include and no exclude."""
    rows = conn.execute(
        """SELECT ingredient_id, ingredient_name, food_category
             FROM ingredients ORDER BY ingredient_name"""
    ).fetchall()
    out = []
    for ingredient_id, name, category in rows:
        low = name.lower()
        if not any(word in low for word in spec["include"]):
            continue
        if any(word in low for word in spec["exclude"]):
            continue
        out.append((ingredient_id, name, category))
    return out


def nutrient_matches(conn, spec: dict) -> list[tuple]:
    """Ingredients reaching the threshold for every nutrient in the spec.

    Per typical serving. An ingredient with no typical_serving_g cannot be
    judged and is left out rather than measured on a different basis.
    """
    conditions, args = [], []
    for nutrient in spec["nutrients"]:
        threshold = DAILY_VALUE[nutrient] * EXCELLENT_SOURCE
        conditions.append(
            """EXISTS (SELECT 1 FROM v_ingredient_nutrition v
                        WHERE v.ingredient_id = i.ingredient_id
                          AND v.nutrient_id = %s
                          AND v.value_per_100g * i.typical_serving_g / 100.0 >= %s)"""
        )
        args += [nutrient, threshold]

    category_clause = ""
    if spec["categories"]:
        category_clause = " AND i.food_category = ANY(%s)"
        args.append(list(spec["categories"]))

    return conn.execute(
        f"""SELECT i.ingredient_id, i.ingredient_name, i.food_category
              FROM ingredients i
             WHERE i.typical_serving_g IS NOT NULL
               AND {' AND '.join(conditions)}
               {category_clause}
             ORDER BY i.ingredient_name""",
        args,
    ).fetchall()


def rules_for(conn, code: str) -> list[tuple]:
    return conn.execute(
        """SELECT rule_id, rule_name, automation_status FROM business_rules
            WHERE is_active AND trigger_code = %s ORDER BY rule_id""",
        (code,),
    ).fetchall()


def seed_reach(conn, ingredient_ids: list) -> int:
    """How many of the 50 seed recipes contain one of these ingredients."""
    if not ingredient_ids:
        return 0
    return conn.execute(
        """SELECT count(DISTINCT r.recipe_id)
             FROM recipe_ingredients ri
             JOIN recipes r USING (recipe_id)
             JOIN seed s ON s.ext = r.external_source_id
            WHERE ri.ingredient_id = ANY(%s)""",
        (ingredient_ids,),
    ).fetchone()[0]


def load_seed(conn) -> None:
    import pathlib
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "api"))
    from app.seed_list import external_ids  # noqa: E402

    conn.execute("CREATE TEMP TABLE seed(ext text PRIMARY KEY)")
    with conn.cursor().copy("COPY seed (ext) FROM STDIN") as copy:
        for external in external_ids():
            copy.write_row([external])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--apply", action="store_true", help="write the tags")
    parser.add_argument("--show", metavar="CODE", help="list one code's matches and exit")
    parser.add_argument("--candidates", metavar="CODE",
                        help="names in the code's USDA food_category that the keyword list "
                             "does not match, and vice versa. A review list; writes nothing.")
    args = parser.parse_args(argv)

    plans = [(code, spec, "nutrient") for code, spec in BY_NUTRIENT.items()]
    plans += [(code, spec, "name") for code, spec in BY_NAME.items()]

    with connect() as conn:
        load_seed(conn)

        if args.candidates:
            code = args.candidates
            if code not in BY_NAME:
                raise SystemExit("%s is not tagged by name, so there is no list to compare." % code)
            category = CATEGORY_HINT.get(code)
            if not category:
                raise SystemExit("No CATEGORY_HINT for %s. Add one to compare against." % code)
            matched = {m[1] for m in name_matches(conn, BY_NAME[code])}
            in_category = {
                row[0] for row in conn.execute(
                    "SELECT ingredient_name FROM ingredients WHERE food_category = %s",
                    (category,),
                ).fetchall()
            }
            print("%s against USDA category %r\n" % (code, category))
            print("in the category, NOT matched by the keywords - review these:")
            for name in sorted(in_category - matched) or ["   (none)"]:
                print("   %s" % name)
            print("\nmatched by the keywords, NOT in the category - usually fine, "
                  "the category may be missing or coarser:")
            for name in sorted(matched - in_category) or ["   (none)"]:
                print("   %s" % name)
            print("\nNothing written. A name worth keeping goes into the include list by hand.")
            return 0

        if args.show:
            found = [p for p in plans if p[0] == args.show]
            if not found:
                raise SystemExit("%s is not tagged by this script. %s"
                                 % (args.show, REFUSED.get(args.show, "")))
            code, spec, how = found[0]
            matches = (nutrient_matches if how == "nutrient" else name_matches)(conn, spec)
            print("%s, by %s - %d ingredients\n" % (code, how, len(matches)))
            for _, name, category in matches:
                print("   %-40s %s" % (name[:40], category or "-"))
            return 0

        total_tags = 0
        total_rules = 0
        print("%-24s %-9s %7s %8s %7s  %s"
              % ("code", "by", "matches", "recipes", "rules", "automation"))
        for code, spec, how in sorted(plans):
            matches = (nutrient_matches if how == "nutrient" else name_matches)(conn, spec)
            ids = [m[0] for m in matches]
            rules = rules_for(conn, code)
            statuses = sorted({r[2] for r in rules})
            if rules and all(s == "do_not_automate" for s in statuses):
                print("%-24s SKIPPED - every rule on it is do_not_automate" % code)
                continue
            print("%-24s %-9s %7d %8d %7d  %s"
                  % (code, how, len(matches), seed_reach(conn, ids), len(rules),
                     ",".join(statuses) or "-"))
            total_rules += len(rules)

            if args.apply and ids:
                written = conn.execute(
                    """INSERT INTO ingredient_rule_tags (ingredient_id, rule_code)
                       SELECT unnest(%s::uuid[]), %s
                    ON CONFLICT (ingredient_id, rule_code) DO NOTHING""",
                    (ids, code),
                ).rowcount
                total_tags += written

        print("\n%d codes, %d rules they belong to" % (len(plans), total_rules))
        if args.apply:
            conn.commit()
            print("wrote %d tags" % total_tags)
        else:
            print("nothing written. Re-run with --apply.")

        print("\nnot tagged, on purpose:")
        for code, reason in sorted(REFUSED.items()):
            print("  %-22s %s" % (code, reason))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
