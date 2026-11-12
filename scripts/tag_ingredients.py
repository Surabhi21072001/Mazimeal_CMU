#!/usr/bin/env python3
"""Propose ingredient tags so the idle rules can fire.

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
               WORDS (not substrings), because "green bean" is not a legume,
               "coffee bean" is not either, and "cola" is not in "chocolate"
               nor "rye" in "fryer".

  by nutrient  a food class defined by how much of a nutrient the ingredient
               carries: "vitamin C-rich produce", "calcium-rich dairy". The
               levels are the FDA's (21 CFR 101.54): 20% of the Daily Value is
               "high / rich in", 10% is "good source / contains". Both are
               defined PER REFERENCE AMOUNT CUSTOMARILY CONSUMED
               (21 CFR 101.12(b)), so that is the basis used, from
               scripts/tag_config.py. ingredients.typical_serving_g is a
               household measure, often a cup, and is NOT that amount: it
               records an avocado as 230 g (reference amount 50 g), parsley as
               60 g (4 g) and dry rice as 185 g (45 g). Measured on it, a
               garnish passes as a rich source. An ingredient whose food has no
               clear class in 101.12(b) is reported as "unjudged", not guessed.

Which level, basis and nutrients apply to which code is configuration, in
scripts/tag_config.py, with the wording of the rule it came from next to it.
Every code there is approved=False until someone signs it off.

Every proposal belongs to one of three evidence categories (tag_config.CODE_CATEGORY),
kept apart in the output because different people review them:
  identity          what the food IS (a legume, a grain, an allium); the risk is a wrong name match
  nutrient          a measured value at the FDA reference amount; the risk is a wrong USDA record or basis
  curated_compound  phytate, oxalate, tannin: a compound the database does not measure. Held at
                    tier 2 until the code has a citation in tag_config.COMPOUND_SOURCES.

Every proposal is given a tier:
  1  nothing found against it; still needs a person's approval
  2  review: close to its threshold, a weak or fortified USDA match, or the
     food class is debatable (refined flour for a "whole grain" rule)
  3  blocked: the USDA record behind the numbers is wrong or not equivalent,
     or the name matched by accident. Shown so the exclusion is visible.

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
    python3 scripts/tag_ingredients.py                  # what it would tag
    python3 scripts/tag_ingredients.py --export out.csv # every proposal, with its evidence
    python3 scripts/tag_ingredients.py --export-dir d   # identity.csv, nutrient.csv, curated_compound.csv
    python3 scripts/tag_ingredients.py --category nutrient   # one evidence category only
    python3 scripts/tag_ingredients.py --show NUT_VITC  # one code's proposals and tiers
    python3 scripts/tag_ingredients.py --emit-migration schema/migrations/012_apply_tier1_ingredient_tags.sql
                                                        # the reproducible way to persist tier 1
    python3 scripts/tag_ingredients.py --apply          # write the TIER 1 tags only (direct, not reproducible)

Environment
    SUPABASE_DB_URL / MAZIMEAL_DSN
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import statistics
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tag_config import (  # noqa: E402
    CATEGORIES, CATEGORY_REVIEWER, COMPOUND, COMPOUND_SOURCES, DAILY_VALUE, EVIDENCE_EXCLUDED, IDENTITY as C_IDENTITY,
    LEVELS, NUTRIENT as C_NUTRIENT, NUTRIENT_CODES, PAIR_EXCLUSIONS, REVIEW_MARGIN, WEAK_MATCH_SCORE, category_of,
    reference_amount,
)

# --------------------------------------------------------------------------
# By name. Same include/exclude shape as INGREDIENT_CODE_MAP in
# scripts/import_rules.py, but matched on whole words (a plural s/es is
# allowed), and with a `review` list for names that ARE the class but not what
# the rule is about. Exclusions are real names in this database, checked
# against the 559 ingredient names rather than imagined.
# --------------------------------------------------------------------------
LEGUMES = [
    "lentil", "chickpea", "garbanzo", "black bean", "kidney bean", "pinto bean",
    "navy bean", "cannellini", "lima bean", "fava bean", "butter bean",
    "soybean", "soy bean", "edamame", "split pea", "black-eyed pea",
    "blackeyed pea", "mung bean", "refried bean", "white bean", "red bean",
    "adzuki", "chili bean", "baked bean", "great northern bean",
]
# Tofu, tempeh and miso are legume products but not what BIO-008/012 (soak and
# cook dry beans), BIO-009/010 and GLY-008 (whole or intact grains and
# legumes) or INH-002 ("unprocessed") describe, so they are not tagged by name.
NOT_LEGUMES = [
    "green bean", "string bean", "wax bean", "vanilla bean", "coffee bean",
    "cocoa bean", "bean sprout", "bean thread", "jelly bean",
]
GRAINS = [
    "rice", "wheat", "oat", "oatmeal", "barley", "rye", "quinoa", "millet",
    "bulgur", "farro", "couscous", "cornmeal", "polenta", "grits", "semolina",
    "bran", "flour", "pasta", "spaghetti", "macaroni", "noodle", "fettuccine",
    "linguine", "orzo", "rotini", "penne", "sorghum", "bread", "tortilla", "matzo",
]
NOT_GRAINS = [
    "rice vinegar", "rice wine", "rice paper", "breadfruit", "almond flour",
    "coconut flour", "chip", "squash", "cellophane", "graham", "crumb",
    "wild rice soup",
]
SEEDS = [
    "sesame seed", "sunflower seed", "pumpkin seed", "flaxseed", "flax seed",
    "chia seed", "poppy seed", "hemp seed", "tahini", "sesame",
]
NOT_SEEDS = ["sesame oil", "sesame dressing", "rice cake"]
ALLIUM = ["garlic", "onion", "shallot", "leek", "scallion", "chive"]
NOT_ALLIUM = ["powder", "salt", "onion soup mix", "cream cheese"]

# (regex, reason, field to test: "name" or "desc"). A hit makes the proposal tier 2.
GRAIN_REVIEW = [
    (r"^(?!.*whole).*\bflour\b", "refined flour; BIO-009/GLY-008 ask for whole or intact grains", "name"),
    (r"flour tortilla", "refined flour product", "name"),
    (r"couscous|matzo", "refined semolina/wheat product", "name"),
    (r"wheat germ", "isolated germ fraction, not a grain", "name"),
]
PHYTATE_REVIEW = [
    (r"canned", "canned: processed, and INH-002 says 'unprocessed'", "desc"),
    (r"baked bean|chili bean|refried", "cooked in sauce: INH-002 says 'unprocessed'", "name"),
]

BY_NAME: dict[str, dict] = {
    "ING_LEGUME": {
        "include": LEGUMES, "exclude": NOT_LEGUMES, "review": [],
        "why": "BIO-008 and BIO-012 are about soaking and cooking legumes. The class "
               "is tagged; whether a given line is DRY or canned is the evaluator's "
               "question (the USDA record of most of these is canned).",
    },
    "ING_GRAIN_LEGUME": {
        "include": LEGUMES + GRAINS, "exclude": NOT_LEGUMES + NOT_GRAINS, "review": GRAIN_REVIEW,
        "why": "BIO-009 says \"whole grains or legumes\", BIO-010 \"whole-grain "
               "or legume batter\", GLY-008 \"grain or legume\" - all three read "
               "as either, so the union is what they mean.",
    },
    "ING_ALLIUM": {
        "include": ALLIUM, "exclude": NOT_ALLIUM, "review": [],
        "why": "A component of the composite ING_ALLIUM_GRAIN_LEGUME, not a "
               "trigger of its own. Broader than ING_GARLIC because SYN-009 says "
               "garlic or onion. Powders, salts and cheeses flavoured with them "
               "are excluded.",
    },
    "ING_GRAIN": {
        "include": GRAINS, "exclude": NOT_GRAINS, "review": GRAIN_REVIEW,
        "why": "A component of the composite ING_LEGUME_GRAIN. Grains alone - "
               "ING_GRAIN_LEGUME is the union with legumes and so cannot be "
               'used to express "legume and grain".',
    },
    "ING_SEED": {
        "include": SEEDS, "exclude": NOT_SEEDS,
        "review": [(r"tahini", "already ground; BIO-014 says to grind seeds", "name")],
        "why": "BIO-014 is about seeds. Sesame oil is excluded because pressing "
               "removes the matrix the rule is about, and rice cake because that "
               "is how sesame seeds came to be mapped to a snack.",
    },
    "CMP_PHYTATE": {
        "include": ["bran", "whole wheat", "whole grain", "oat", "oatmeal", "brown rice"] + LEGUMES + SEEDS,
        "exclude": NOT_LEGUMES + NOT_SEEDS, "review": PHYTATE_REVIEW,
        "why": 'INH-002 names its own trigger: "unprocessed bran, grains, '
               'legumes, seeds". Phytate is not one of the 28 nutrients stored, '
               "so the food class is the only available handle.",
    },
    "CMP_OXALATE": {
        "include": ["spinach", "swiss chard", "beet green", "rhubarb", "sorrel",
                    "purslane", "amaranth leaf"],
        "exclude": [], "review": [],
        "why": 'INH-004 says "high-oxalate food such as spinach". Oxalate is not '
               "stored either, and the high-oxalate foods are a short, settled "
               "list rather than a threshold.",
    },
    "BEV_TEA_COFFEE": {
        "include": ["tea", "coffee", "espresso"],
        "exclude": ["tea towel", "butter", "creamer"],
        "review": [(r"instant|granules|powder", "likely flavouring; INH-001 is about the meal beverage", "name")],
        "why": "INH-001 is about tannins with iron.",
    },
    "BEV_SSB": {
        "include": ["soda", "cola", "soft drink", "sweetened beverage",
                    "fruit punch", "lemonade", "sports drink", "energy drink"],
        "exclude": ["baking soda", "soda water", "club soda", "soda bread"],
        "review": [],
        "why": "GLY-010 is about sugar-sweetened beverages. Baking soda and soda "
               "bread are the accidents here.",
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
    "PROC_COOKWARE": "SYN-012 is about the cookware used (cast iron) for an acidic dish, "
                     "a cooking step rather than a property of any ingredient.",
    "PROC_COOL_REHEAT": "GLY-015 is about cooling and reheating cooked rice, pasta or "
                        "potato, which is read from recipe_steps, not from an ingredient.",
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
        'SYN-009\'s "garlic/onion plus grain or legume" means.',
    "ING_LEGUME_GRAIN":
        "A composite, since migration 009. Fires when ING_LEGUME and ING_GRAIN "
        'are both present - SYN-007\'s "legumes and grains".',
}

# USDA's own food_category, used by --candidates to propose names a keyword
# list has missed. A review aid, not a replacement for the lists.
CATEGORY_HINT = {
    "ING_LEGUME": "Legumes and Legume Products",
    "ING_SEED": "Nut and Seed Products",
    "ING_GRAIN": "Cereal Grains and Pasta",
    "ING_ALLIUM": "Vegetables and Vegetable Products",
    "CMP_OXALATE": "Vegetables and Vegetable Products",
    "BEV_SSB": "Beverages",
    "BEV_TEA_COFFEE": "Beverages",
}


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------
@dataclass
class Ingredient:
    ingredient_id: str
    name: str
    category: str | None
    serving_g: float | None
    desc: str | None
    matched_by: str | None
    score: int | None
    nutrients: dict[str, float] = field(default_factory=dict)
    recipes: set = field(default_factory=set)
    seed_recipes: set = field(default_factory=set)
    grams_per_recipe_serving: list = field(default_factory=list)


@dataclass
class Proposal:
    ingredient: Ingredient
    code: str
    tier: int | None            # 1, 2, 3, or None for "unjudged"
    how: str
    evidence: str
    level: str = ""
    threshold_pct: float | None = None
    basis_label: str = ""
    basis_g: float | None = None
    pct_at_basis: float | None = None
    reasons: list = field(default_factory=list)
    median_recipe_pct: float | None = None
    category: str = ""          # identity | nutrient | curated_compound (tag_config.CODE_CATEGORY)


def connect():
    dsn = os.environ.get("SUPABASE_DB_URL") or os.environ.get("MAZIMEAL_DSN")
    if not dsn:
        raise SystemExit("set SUPABASE_DB_URL (or MAZIMEAL_DSN)")
    import psycopg

    return psycopg.connect(dsn)


def load(conn) -> dict[str, Ingredient]:
    """Every ingredient once, with its USDA match, nutrients and recipe use.

    Classification happens once per unique ingredient, never per recipe line.
    """
    ing: dict[str, Ingredient] = {}
    for iid, name, cat, serving, desc, by, score in conn.execute(
        """SELECT i.ingredient_id::text, i.ingredient_name, i.food_category, i.typical_serving_g,
                  m.source_description, m.matched_by, m.match_score
             FROM ingredients i
             LEFT JOIN ingredient_source_map m
                    ON m.ingredient_id = i.ingredient_id AND m.source_id = 'usda_sr_legacy'"""
    ).fetchall():
        ing[iid] = Ingredient(iid, name, cat, float(serving) if serving else None, desc, by, score)

    for iid, nutrient, value in conn.execute(
        "SELECT ingredient_id::text, nutrient_id, value_per_100g FROM v_ingredient_nutrition WHERE nutrient_id = ANY(%s)",
        (list(DAILY_VALUE),),
    ).fetchall():
        if value is not None:
            ing[iid].nutrients[nutrient] = float(value)

    seed = set(_seed_ids())
    for iid, rid, ext, grams, servings in conn.execute(
        """SELECT ri.ingredient_id::text, ri.recipe_id::text, r.external_source_id, ri.quantity_g, r.servings
             FROM recipe_ingredients ri JOIN recipes r USING (recipe_id)
            WHERE r.deleted_at IS NULL"""
    ).fetchall():
        i = ing[iid]
        i.recipes.add(rid)
        if ext in seed:
            i.seed_recipes.add(rid)
        if grams is not None and servings:
            i.grams_per_recipe_serving.append(float(grams) / max(servings, 1))
    return ing


def _seed_ids() -> list[str]:
    import pathlib

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "api"))
    from app.seed_list import external_ids  # noqa: E402

    return list(external_ids())


# --------------------------------------------------------------------------
# By name
# --------------------------------------------------------------------------
def _word(kw: str) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])" + re.escape(kw) + r"(?:s|es)?(?![a-z0-9])")


def name_proposals(ings, code: str, spec: dict) -> list[Proposal]:
    inc = [_word(w) for w in spec["include"]]
    exc = [_word(w) for w in spec["exclude"]]
    out = []
    for i in sorted(ings.values(), key=lambda x: x.name):
        low = i.name.lower()
        hits = [w for w, rx in zip(spec["include"], inc) if rx.search(low)]
        if not hits or any(rx.search(low) for rx in exc):
            continue
        p = Proposal(i, code, 1, "name", "name contains: " + ", ".join(hits), category=category_of(code))
        for rx, reason, where in spec["review"]:
            target = low if where == "name" else (i.desc or "").lower()
            if re.search(rx, target):
                p.tier = 2
                p.reasons.append(reason)
        out.append(p)
    return out


# --------------------------------------------------------------------------
# By nutrient
# --------------------------------------------------------------------------
_FORTIFIED = re.compile(r"\benriched\b|\bfortified\b|with added (ascorbic|vitamin|calcium|iron|folic)")


def _fortified(desc: str | None) -> bool:
    d = (desc or "").lower().replace("unenriched", "").replace("not fortified", "")
    return bool(_FORTIFIED.search(d))


def nutrient_proposals(ings, code: str):
    """(proposals, unjudged) for one nutrient code, per its config."""
    cfg = NUTRIENT_CODES[code]
    threshold = LEVELS[cfg.level]
    proposals, unjudged = [], []
    for i in sorted(ings.values(), key=lambda x: x.name):
        if cfg.categories and i.category not in cfg.categories:
            continue
        have = [n for n in cfg.nutrients if n in i.nutrients]
        if (cfg.combine == "all" and len(have) < len(cfg.nutrients)) or not have:
            continue  # no data for this nutrient: not a candidate, and not a guess

        if cfg.basis == "typical_serving":
            grams, label = i.serving_g, "ingredients.typical_serving_g (household measure)"
        else:
            ref = reference_amount(i.name, i.category, i.desc)
            grams, label = (ref if ref else (None, ""))
        if not grams:
            # Only worth listing if the old household-measure basis WOULD have proposed it: that is
            # the set of tags this change declines to make, and a reviewer should be able to see it.
            if i.serving_g:
                legacy = {n: i.nutrients[n] / 100.0 * i.serving_g / DAILY_VALUE[n] for n in have}
                legacy_ok = (all(v >= threshold for v in legacy.values()) and len(have) == len(cfg.nutrients)) \
                    if cfg.combine == "all" else any(v >= threshold for v in legacy.values())
                if legacy_ok:
                    unjudged.append(Proposal(i, code, None, "nutrient",
                                             "would qualify on typical_serving_g (%g g) but 101.12(b) gives this food no reference amount" % i.serving_g,
                                             cfg.level, threshold * 100, reasons=["unjudged: no reference amount for this food"],
                                             category=category_of(code)))
            continue

        pct = {n: i.nutrients[n] / 100.0 * grams / DAILY_VALUE[n] for n in have}
        passed = [n for n in have if pct[n] >= threshold]
        ok = (len(passed) == len(cfg.nutrients)) if cfg.combine == "all" else bool(passed)
        if not ok:
            continue
        best = min(pct.values()) if cfg.combine == "all" else max(pct[n] for n in passed)
        evidence = "; ".join("%s %.2f/100g x %g g = %.0f%% DV" % (n, i.nutrients[n], grams, pct[n] * 100) for n in have)
        p = Proposal(i, code, 1, "nutrient", evidence, cfg.level, threshold * 100, label, grams, best * 100,
                     category=category_of(code))

        if i.name in EVIDENCE_EXCLUDED:
            p.tier = 3
            p.reasons.append("blocked: " + EVIDENCE_EXCLUDED[i.name])
        elif (code, i.name) in PAIR_EXCLUSIONS:
            p.tier = 3
            p.reasons.append("blocked: " + PAIR_EXCLUSIONS[(code, i.name)])
        else:
            if best / threshold < REVIEW_MARGIN:
                p.tier = 2
                p.reasons.append("%.0f%% DV is within %.0f%% of the %.0f%% line" % (best * 100, (REVIEW_MARGIN - 1) * 100, threshold * 100))
            if i.matched_by in ("fuzzy", "alias") and i.score is not None and i.score < WEAK_MATCH_SCORE:
                p.tier = 2
                p.reasons.append("weak USDA match (%s, score %s): %s" % (i.matched_by, i.score, (i.desc or "")[:50]))
            if _fortified(i.desc):
                p.tier = 2
                p.reasons.append("USDA food is enriched/fortified: " + (i.desc or "")[:50])
        first = cfg.nutrients[0]
        if i.grams_per_recipe_serving and first in i.nutrients:
            p.median_recipe_pct = 100 * statistics.median(
                i.nutrients[first] / 100.0 * g / DAILY_VALUE[first] for g in i.grams_per_recipe_serving)
        proposals.append(p)
    return proposals, unjudged


def build_all(ings):
    """{code: [Proposal]} and {code: [unjudged Proposal]}, one pass per unique ingredient.

    A curated-compound proposal is held at tier 2 until its code has a citation in
    tag_config.COMPOUND_SOURCES: membership of a food in "high-phytate" or
    "high-oxalate" is knowledge, not something the database measures, so the
    script will not call it safe on its own say-so.
    """
    props, unjudged = {}, {}
    for code, cfg in NUTRIENT_CODES.items():
        props[code], unjudged[code] = nutrient_proposals(ings, code)
    for code, spec in BY_NAME.items():
        props[code], unjudged[code] = name_proposals(ings, code, spec), []
    for code, rows in props.items():
        if category_of(code) == COMPOUND and code not in COMPOUND_SOURCES:
            for p in rows:
                if p.tier == 1:
                    p.tier = 2
                    p.reasons.append("curated compound: no source citation recorded in tag_config.COMPOUND_SOURCES")
    return props, unjudged


def by_category(props, unjudged=None):
    """Split {code: [...]} into {category: {code: [...]}}, every category present."""
    out = {c: {} for c in CATEGORIES}
    for code, rows in props.items():
        out[category_of(code)][code] = rows
    return out


def rules_for(conn, code: str) -> list[tuple]:
    return conn.execute(
        """SELECT rule_id, rule_name, automation_status FROM business_rules
            WHERE is_active AND trigger_code = %s ORDER BY rule_id""",
        (code,),
    ).fetchall()


CONF = {1: "High (needs approval)", 2: "Medium (review)", 3: "Blocked", None: "Unjudged"}
CSV_HEADER = ["category", "ingredient", "ingredient_id", "code", "tier", "confidence", "how", "evidence", "level",
              "threshold_pct_dv", "basis", "basis_g", "pct_dv_at_basis", "usda_description", "match_by",
              "match_score", "recipes", "median_recipe_pct_dv", "review_reasons"]


def _csv_row(code, p):
    i = p.ingredient
    return [p.category, i.name, i.ingredient_id, code, p.tier if p.tier else "", CONF[p.tier], p.how, p.evidence,
            p.level, "" if p.threshold_pct is None else "%g" % p.threshold_pct, p.basis_label,
            "" if p.basis_g is None else "%g" % p.basis_g,
            "" if p.pct_at_basis is None else "%.1f" % p.pct_at_basis,
            i.desc or "", i.matched_by or "", "" if i.score is None else i.score, len(i.recipes),
            "" if p.median_recipe_pct is None else "%.1f" % p.median_recipe_pct,
            "; ".join(p.reasons)]


def export_csv(path, props, unjudged, category=None):
    """Every proposal (optionally one category) with its evidence. Writes a file, never a database row."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_HEADER)
        for code in sorted(props):
            if category and category_of(code) != category:
                continue
            for p in props[code] + unjudged.get(code, []):
                w.writerow(_csv_row(code, p))


def export_by_category(directory, props, unjudged):
    """identity.csv, nutrient.csv, curated_compound.csv: one file per reviewer."""
    os.makedirs(directory, exist_ok=True)
    paths = []
    for cat in CATEGORIES:
        path = os.path.join(directory, cat + ".csv")
        export_csv(path, props, unjudged, category=cat)
        paths.append(path)
    return paths


def tier1_by_code(props, category=None):
    """{code: [ingredient_id]} of tier-1 proposals, optionally one category."""
    return {code: [p.ingredient.ingredient_id for p in rows if p.tier == 1]
            for code, rows in props.items() if not category or category_of(code) == category}


def apply_tier1(conn, ids_by_code):
    """Insert tier-1 tags and commit. Returns the number of NEW rows.

    Takes the connection as an argument so a test can hand it a recording fake.
    Nothing here knows about tiers 2 and 3: callers pass only what was approved.
    """
    written = 0
    for code, ids in ids_by_code.items():
        if ids:
            written += conn.execute(
                """INSERT INTO ingredient_rule_tags (ingredient_id, rule_code)
                   SELECT unnest(%s::uuid[]), %s
                ON CONFLICT (ingredient_id, rule_code) DO NOTHING""",
                (ids, code),
            ).rowcount
    conn.commit()
    return written

# --------------------------------------------------------------------------
# Reproducible output: the tier-1 set as a migration
# --------------------------------------------------------------------------
MIGRATION_NAME = "012_apply_tier1_ingredient_tags.sql"


def tier1_rows(props):
    """[(category, code, ingredient name)] for every tier-1 proposal, in a fixed order.

    Raises if a curated-compound row is tier 1: that can only happen if a citation was
    recorded in tag_config.COMPOUND_SOURCES, and a separately approved migration should
    carry it, not this one.
    """
    rows = []
    for code, plist in props.items():
        for p in plist:
            if p.tier != 1:
                continue
            if p.category not in (C_IDENTITY, C_NUTRIENT):
                raise ValueError("%s/%s is %s; only identity and nutrient tags belong in the tier-1 migration"
                                 % (code, p.ingredient.name, p.category))
            rows.append((p.category, code, p.ingredient.name))
    order = {c: n for n, c in enumerate(CATEGORIES)}
    rows.sort(key=lambda r: (order[r[0]], r[1], r[2].lower(), r[2]))
    if len(set((c, n.lower().strip()) for _, c, n in rows)) != len(rows):
        raise ValueError("duplicate (code, ingredient) in the tier-1 set")
    return rows


def _sql(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def render_migration(rows) -> str:
    """The text of migration 012 for these rows. Pure and deterministic: same rows, same bytes."""
    by_cat = {}
    by_code = {}
    for cat, code, _ in rows:
        by_cat[cat] = by_cat.get(cat, 0) + 1
        by_code[(cat, code)] = by_code.get((cat, code), 0) + 1
    values = ",\n".join("    (%s, %s, %s)" % (_sql(n), _sql(c), _sql(cat)) for cat, c, n in rows)
    summary = "\n".join("--   %-9s %-22s %3d" % (cat, code, n) for (cat, code), n in sorted(
        by_code.items(), key=lambda kv: (CATEGORIES.index(kv[0][0]), kv[0][1])))
    return f"""-- {MIGRATION_NAME}
-- GENERATED by scripts/tag_ingredients.py --emit-migration. Do not edit by hand:
-- regenerate it, and tests/test_tag_db.py checks that the result is byte-identical.
--
-- Apply the reviewed tier-1 ingredient tags: {len(rows)} (ingredient, rule code) pairs.
--   identity  {by_cat.get("identity", 0):>3}   what the food IS (a legume, a grain, an allium, a seed)
--   nutrient  {by_cat.get("nutrient", 0):>3}   a measured value at the FDA reference amount (21 CFR 101.12(b))
--   curated_compound   0   none: phytate, oxalate and tannin need a recorded citation first
--
-- By code:
{summary}
--
-- Why this is a migration and not just `tag_ingredients.py --apply`: --apply writes straight to
-- one database and leaves no record, so a fresh environment would not have the tags. This file is
-- the record. It selects ingredients by NAME (ingredient_id is generated per database), exactly as
-- schema/seed/ingredient_rule_tags.sql does.
--
-- What is NOT here, on purpose (each is tier 2, tier 3, blocked or unjudged in the review):
--   * CMP_PHYTATE, CMP_OXALATE, BEV_TEA_COFFEE (curated compounds, no citation yet)
--   * ingredients awaiting USDA values (orange, sweet potatoes, sun-dried tomatoes, tomato paste,
--     sesame seeds) as nutrient evidence; see migration 010
--   * milk and its variants (mapped to buttermilk), generic cheese, unsweetened applesauce and
--     ground coriander; see tag_config.EVIDENCE_EXCLUDED
--   * buttermilk and low-fat buttermilk for NUT_VITD (unconfirmed fortification);
--     see tag_config.PAIR_EXCLUSIONS
--   * foods with no clear 21 CFR 101.12(b) reference amount (oats, garlic, couscous, zest) as
--     nutrient evidence, and every tier-2 pair (near its threshold, weak or fortified USDA match,
--     refined flour, canned beans for phytate, instant coffee, tahini)
--   * PROC_COOKWARE and PROC_COOL_REHEAT (process steps, not ingredients) and every composite
--     (ING_LEGUME_GRAIN, ING_ALLIUM_GRAIN_LEGUME), which are never tagged directly
--
-- ING_GRAIN_LEGUME is the OR code ("grain or legume"): BIO-009, BIO-010 and GLY-008 are all worded
-- with "or". The AND meaning is ING_LEGUME_GRAIN, a composite (migration 009), so tagging the
-- individual ingredients here is correct.
--
-- Safe to run twice. It stops, changing nothing, if an ingredient is missing or ambiguous, a rule
-- code is unknown or is a composite, or the list repeats a pair. Existing tags are never changed or
-- deleted. When it finishes it reports: listed = already present + newly inserted (nothing skipped).
BEGIN;

CREATE TEMP TABLE _tier1_tags (
    ingredient_name TEXT NOT NULL,
    rule_code       TEXT NOT NULL,
    category        TEXT NOT NULL
) ON COMMIT DROP;

INSERT INTO _tier1_tags (ingredient_name, rule_code, category) VALUES
{values};

DO $$
DECLARE
    r          RECORD;
    v_n        INT;
    v_listed   INT;
    v_present  INT;
    v_inserted INT;
BEGIN
    SELECT count(*) INTO v_listed FROM _tier1_tags;

    -- 1. The list itself.
    IF EXISTS (SELECT 1 FROM _tier1_tags WHERE category NOT IN ('identity', 'nutrient')) THEN
        RAISE EXCEPTION 'only identity and nutrient tags may be listed here; curated-compound tags need a recorded citation first';
    END IF;
    IF EXISTS (SELECT 1 FROM _tier1_tags GROUP BY lower(btrim(ingredient_name)), rule_code HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'the list repeats an (ingredient, rule code) pair';
    END IF;

    -- 2. Every rule code exists, and none is a composite (those fire from their components).
    FOR r IN SELECT DISTINCT rule_code FROM _tier1_tags LOOP
        IF NOT EXISTS (SELECT 1 FROM rule_codes WHERE code = r.rule_code) THEN
            RAISE EXCEPTION 'unknown rule code %', r.rule_code;
        END IF;
        IF EXISTS (SELECT 1 FROM rule_code_components WHERE composite_code = r.rule_code) THEN
            RAISE EXCEPTION 'rule code % is a composite and must never be tagged directly', r.rule_code;
        END IF;
    END LOOP;

    -- 3. Every ingredient exists exactly once.
    FOR r IN SELECT DISTINCT lower(btrim(ingredient_name)) AS name FROM _tier1_tags LOOP
        SELECT count(*) INTO v_n FROM ingredients WHERE lower(btrim(ingredient_name)) = r.name;
        IF v_n = 0 THEN
            RAISE EXCEPTION 'no ingredient named "%"', r.name;
        ELSIF v_n > 1 THEN
            RAISE EXCEPTION 'ingredient name "%" is ambiguous (% rows)', r.name, v_n;
        END IF;
    END LOOP;

    -- 4. Insert, counting what was already there so the numbers reconcile.
    SELECT count(*) INTO v_present
      FROM _tier1_tags t
      JOIN ingredients i ON lower(btrim(i.ingredient_name)) = lower(btrim(t.ingredient_name))
      JOIN ingredient_rule_tags x ON x.ingredient_id = i.ingredient_id AND x.rule_code = t.rule_code;

    INSERT INTO ingredient_rule_tags (ingredient_id, rule_code)
    SELECT i.ingredient_id, t.rule_code
      FROM _tier1_tags t
      JOIN ingredients i ON lower(btrim(i.ingredient_name)) = lower(btrim(t.ingredient_name))
    ON CONFLICT (ingredient_id, rule_code) DO NOTHING;
    GET DIAGNOSTICS v_inserted = ROW_COUNT;

    IF v_present + v_inserted <> v_listed THEN
        RAISE EXCEPTION 'reconciliation failed: % listed, % already present, % inserted', v_listed, v_present, v_inserted;
    END IF;
    RAISE NOTICE 'tier-1 ingredient tags: % listed = % already present + % newly inserted; 0 skipped; 0 failed validation',
                 v_listed, v_present, v_inserted;
END;
$$;

COMMIT;
"""


def emit_migration(path, props):
    """Write migration 012 for the current tier-1 set. Writes a file; touches no database."""
    rows = tier1_rows(props)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_migration(rows))
    return len(rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--apply", action="store_true", help="write the TIER 1 tags only")
    parser.add_argument("--show", metavar="CODE", help="list one code's proposals and tiers, then exit")
    parser.add_argument("--category", choices=CATEGORIES, help="limit the summary, export and --apply to one evidence category")
    parser.add_argument("--export", metavar="CSV", help="write every proposal, with evidence, to a CSV (writes no database rows)")
    parser.add_argument("--emit-migration", metavar="SQL", help="write the tier-1 set as an idempotent, validated migration "
                        "(the reproducible way to persist it; writes a file, never a database row)")
    parser.add_argument("--export-dir", metavar="DIR", help="write identity.csv, nutrient.csv and curated_compound.csv, one per reviewer")
    parser.add_argument("--candidates", metavar="CODE",
                        help="names in the code's USDA food_category that the keyword list "
                             "does not match, and vice versa. A review list; writes nothing.")
    args = parser.parse_args(argv)

    with connect() as conn:
        ings = load(conn)
        props, unjudged = build_all(ings)

        if args.candidates:
            code = args.candidates
            if code not in BY_NAME:
                raise SystemExit("%s is not tagged by name, so there is no list to compare." % code)
            category = CATEGORY_HINT.get(code)
            if not category:
                raise SystemExit("No CATEGORY_HINT for %s. Add one to compare against." % code)
            matched = {p.ingredient.name for p in props[code]}
            in_category = {i.name for i in ings.values() if i.category == category}
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
            if args.show not in props:
                raise SystemExit("%s is not tagged by this script. %s" % (args.show, REFUSED.get(args.show, "")))
            rows = props[args.show]
            print("%s [%s] - %d proposals, %d unjudged\n" % (args.show, category_of(args.show), len(rows), len(unjudged[args.show])))
            for p in rows:
                print("  T%s %-34s %s%s" % (p.tier, p.ingredient.name[:34], p.evidence[:80],
                                           ("  <- " + "; ".join(p.reasons)[:90]) if p.reasons else ""))
            for p in unjudged[args.show]:
                print("  -- %-34s %s" % (p.ingredient.name[:34], p.evidence))
            return 0

        if args.export:
            export_csv(args.export, props, unjudged, category=args.category)
            print("wrote %s" % args.export)
        if args.export_dir:
            for path in export_by_category(args.export_dir, props, unjudged):
                print("wrote %s" % path)
        if args.emit_migration:
            print("wrote %s (%d tier-1 pairs)" % (args.emit_migration, emit_migration(args.emit_migration, props)))

        total_rules = 0
        skipped = set()
        n_all = n1 = 0
        for cat in CATEGORIES:
            if args.category and cat != args.category:
                continue
            print("\n== %s  (reviewed by: %s)" % (cat.upper(), CATEGORY_REVIEWER[cat]))
            print("%-22s %5s %4s %4s %4s %9s %6s  %s" % ("code", "total", "T1", "T2", "T3", "unjudged", "rules", "automation"))
            for code in sorted(c for c in props if category_of(c) == cat):
                rows = props[code]
                rules = rules_for(conn, code)
                statuses = sorted({r[2] for r in rules})
                if rules and all(s == "do_not_automate" for s in statuses):
                    print("%-22s SKIPPED - every rule on it is do_not_automate" % code)
                    skipped.add(code)
                    continue
                t = {n: sum(1 for p in rows if p.tier == n) for n in (1, 2, 3)}
                print("%-22s %5d %4d %4d %4d %9d %6d  %s"
                      % (code, len(rows), t[1], t[2], t[3], len(unjudged[code]), len(rules), ",".join(statuses) or "-"))
                total_rules += len(rules)
                n_all += len(rows)
                n1 += t[1]

        print("\n%d rules they belong to; %d proposals, %d at tier 1" % (total_rules, n_all, n1))
        if COMPOUND not in (args.category,) and not COMPOUND_SOURCES:
            print("curated_compound proposals are held at tier 2: tag_config.COMPOUND_SOURCES has no citation.")

        if args.apply:
            ids = {c: v for c, v in tier1_by_code(props, args.category).items() if c not in skipped}
            written = apply_tier1(conn, ids)
            print("wrote %d tier-1 tags; held back %d for review or blocked" % (written, n_all - n1))
        else:
            print("nothing written. --apply writes tier 1 only; tiers 2 and 3 are never applied by this script.")

        print("\nnot tagged, on purpose:")
        for code, reason in sorted(REFUSED.items()):
            print("  %-22s %s" % (code, reason))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
