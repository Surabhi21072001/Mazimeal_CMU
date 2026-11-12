#!/usr/bin/env python3
"""Tests for scripts/tag_ingredients.py: proposals, tiers, categories, export, apply.

Pure Python. Ingredients are built in memory, so there is no database and no
network. The one function that writes (apply_tier1) is exercised with a
recording fake connection and is never given a real one.

    python3 -m unittest tests.test_tag_ingredients -v
"""
from __future__ import annotations

import csv
import dataclasses
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import tag_config as C  # noqa: E402
import tag_ingredients as T  # noqa: E402

VEG, FRUIT, DAIRY = "Vegetables and Vegetable Products", "Fruits and Fruit Juices", "Dairy and Egg Products"
LEG, GRAIN, SEEDS = "Legumes and Legume Products", "Cereal Grains and Pasta", "Nut and Seed Products"

_counter = [0]


def ing(name, category=VEG, nutrients=None, desc=None, by="alias", score=105, serving=None, grams=None):
    """An in-memory ingredient. `grams` is a list of grams-per-recipe-serving observations."""
    _counter[0] += 1
    i = T.Ingredient("00000000-0000-0000-0000-%012d" % _counter[0], name, category, serving, desc, by, score)
    i.nutrients = dict(nutrients or {})
    i.grams_per_recipe_serving = list(grams or [])
    i.recipes = {"r%d" % _counter[0]}
    return i


def table(*items):
    return {i.ingredient_id: i for i in items}


def names(proposals):
    return sorted(p.ingredient.name for p in proposals)


def value_for(code, grams, pct):
    """The per-100 g value that gives exactly `pct` of the Daily Value at `grams`."""
    cfg = C.NUTRIENT_CODES[code]
    n = cfg.nutrients[0]
    return pct * C.DAILY_VALUE[n] * 100.0 / grams


class WordMatching(unittest.TestCase):
    def match(self, keyword, text):
        return bool(T._word(keyword).search(text.lower()))

    def test_whole_words_and_plurals_match(self):
        self.assertTrue(self.match("bean", "black beans"))
        self.assertTrue(self.match("oat", "rolled oats"))
        self.assertTrue(self.match("tomato", "tomatoes"))
        self.assertTrue(self.match("garlic", "garlic cloves"))

    def test_hyphen_and_punctuation_are_boundaries(self):
        self.assertTrue(self.match("oat", "quick-cooking oatmeal".replace("oatmeal", "oats")))
        self.assertTrue(self.match("onion", "onion, chopped"))

    def test_keyword_inside_a_longer_word_does_not_match(self):
        # The four substring accidents found in the audit, plus two more of the same kind.
        self.assertFalse(self.match("cola", "chocolate chips"))
        self.assertFalse(self.match("rye", "fryer chickens"))
        self.assertFalse(self.match("oat", "goat cheese"))
        self.assertFalse(self.match("bran", "brandy"))
        self.assertFalse(self.match("tea", "steak"))
        self.assertFalse(self.match("tea", "teaspoon"))

    def test_digits_count_as_word_characters(self):
        self.assertFalse(self.match("oat", "oat2"))

    def test_regex_metacharacters_in_a_keyword_are_literal(self):
        self.assertTrue(self.match("c.l", "c.l"))
        self.assertFalse(self.match("c.l", "cal"))


class IdentityLegumes(unittest.TestCase):
    def run_code(self, *items, code="ING_LEGUME"):
        return T.name_proposals(table(*items), code, T.BY_NAME[code])

    def test_real_legumes_are_tagged(self):
        got = names(self.run_code(*[ing(n, LEG) for n in (
            "black beans", "brown lentils", "chickpeas", "garbanzo beans", "kidney beans", "pinto beans",
            "navy beans", "cannellini beans", "great northern beans", "vegetarian baked beans", "chili beans")]))
        self.assertEqual(len(got), 11)

    def test_pod_vegetables_and_non_beans_are_not_legumes(self):
        got = self.run_code(*[ing(n) for n in ("green beans", "string beans", "vanilla bean", "coffee bean",
                                               "cocoa bean", "bean sprouts", "jelly beans")])
        self.assertEqual(got, [])

    def test_tofu_tempeh_and_miso_are_not_tagged_by_name(self):
        # BIO-008/012 are about soaking and cooking dry legumes; tofu is processed soy.
        for code in ("ING_LEGUME", "ING_GRAIN_LEGUME", "CMP_PHYTATE"):
            got = self.run_code(ing("firm tofu", LEG), ing("tempeh", LEG), ing("miso", LEG), code=code)
            self.assertEqual(got, [], code)

    def test_identity_proposals_have_no_numeric_threshold(self):
        p = self.run_code(ing("black beans", LEG))[0]
        self.assertEqual(p.how, "name")
        self.assertIsNone(p.threshold_pct)
        self.assertEqual(p.category, "identity")
        self.assertEqual(p.tier, 1)


class IdentityGrains(unittest.TestCase):
    def run_code(self, *items, code="ING_GRAIN"):
        return T.name_proposals(table(*items), code, T.BY_NAME[code])

    def test_intact_grains_and_pasta_are_tagged(self):
        got = names(self.run_code(*[ing(n, GRAIN) for n in (
            "rice", "cooked brown rice", "oatmeal", "oats", "spaghetti", "fettuccine", "linguine", "orzo pasta",
            "sorghum", "quick-cooking grits", "corn tortillas", "other pastas")]))
        self.assertEqual(len(got), 12)

    def test_substring_and_snack_accidents_are_not_grains(self):
        got = self.run_code(*[ing(n) for n in (
            "fryer chickens", "spaghetti squash", "tortilla chips", "corn tortilla chips", "non-fat tortilla chips",
            "graham cracker", "panko breadcrumbs", "cellophane noodle", "rice vinegar", "rice paper", "breadfruit",
            "almond flour", "coconut flour")])
        self.assertEqual(got, [])

    def test_oatmeal_is_a_word_of_its_own(self):
        # Word matching would otherwise lose it, because "oat" is not a word inside "oatmeal".
        self.assertEqual(names(self.run_code(ing("oatmeal", GRAIN))), ["oatmeal"])

    def test_refined_flour_is_tier_2_whole_wheat_flour_is_tier_1(self):
        flour = self.run_code(ing("all-purpose flour", GRAIN), ing("whole wheat flour", GRAIN), ing("flour", GRAIN))
        tiers = {p.ingredient.name: p.tier for p in flour}
        self.assertEqual(tiers, {"all-purpose flour": 2, "whole wheat flour": 1, "flour": 2})
        self.assertIn("refined", [p for p in flour if p.ingredient.name == "flour"][0].reasons[0])

    def test_semolina_and_germ_products_are_reviewed(self):
        tiers = {p.ingredient.name: p.tier for p in self.run_code(
            ing("couscous", GRAIN), ing("matzo meal", GRAIN), ing("wheat germ", GRAIN), ing("flour tortillas", GRAIN))}
        self.assertEqual(set(tiers.values()), {2})

    def test_union_code_contains_both_families(self):
        got = names(T.name_proposals(table(ing("black beans", LEG), ing("rice", GRAIN), ing("celery")),
                                     "ING_GRAIN_LEGUME", T.BY_NAME["ING_GRAIN_LEGUME"]))
        self.assertEqual(got, ["black beans", "rice"])


class IdentityAlliumAndSeeds(unittest.TestCase):
    def test_allium_variants_tagged_powders_salts_and_cheeses_not(self):
        spec = T.BY_NAME["ING_ALLIUM"]
        got = names(T.name_proposals(table(*[ing(n) for n in (
            "garlic", "garlic cloves", "minced garlic clove", "onions", "green onions", "scallions", "chives", "red onion",
            "garlic powder", "onion powder", "garlic salt", "onion soup mix", "chive & onion cream cheese")]),
            "ING_ALLIUM", spec))
        self.assertEqual(got, ["chives", "garlic", "garlic cloves", "green onions", "minced garlic clove", "onions", "red onion", "scallions"])

    def test_seeds_and_their_exclusions(self):
        spec = T.BY_NAME["ING_SEED"]
        got = {p.ingredient.name: p.tier for p in T.name_proposals(table(*[ing(n, SEEDS) for n in (
            "sesame seeds", "toasted sesame seeds", "flax seed", "ground flax seeds", "tahini", "sesame oil", "rice cakes")]),
            "ING_SEED", spec)}
        self.assertEqual(got, {"sesame seeds": 1, "toasted sesame seeds": 1, "flax seed": 1, "ground flax seeds": 1, "tahini": 2})


class CuratedCompounds(unittest.TestCase):
    def test_compound_proposals_are_held_at_tier_2_without_a_citation(self):
        ings = table(ing("spinach"), ing("swiss chard"), ing("brown lentils", LEG, desc="Lentils, raw"), ing("oats", GRAIN))
        props, _ = T.build_all(ings)
        for code in ("CMP_OXALATE", "CMP_PHYTATE"):
            self.assertTrue(props[code], code)
            for p in props[code]:
                self.assertEqual(p.category, "curated_compound")
                self.assertEqual(p.tier, 2, p.ingredient.name)
                self.assertTrue(any("citation" in r for r in p.reasons))

    def test_a_citation_releases_the_cap_for_that_code_only(self):
        ings = table(ing("spinach"), ing("brown lentils", LEG, desc="Lentils, raw"))
        with mock.patch.dict(C.COMPOUND_SOURCES, {"CMP_OXALATE": "a real reference"}):
            props, _ = T.build_all(ings)
        self.assertEqual([p.tier for p in props["CMP_OXALATE"]], [1])
        self.assertEqual({p.tier for p in props["CMP_PHYTATE"]}, {2})

    def test_citation_does_not_rescue_a_proposal_that_was_already_tier_2(self):
        ings = table(ing("black beans", LEG, desc="Beans, black turtle, mature seeds, canned"))
        with mock.patch.dict(C.COMPOUND_SOURCES, {"CMP_PHYTATE": "a real reference"}):
            props, _ = T.build_all(ings)
        self.assertEqual(props["CMP_PHYTATE"][0].tier, 2)

    def test_canned_legumes_are_processed_for_the_unprocessed_rule(self):
        p = T.name_proposals(table(ing("black beans", LEG, desc="Beans, black turtle, mature seeds, canned")),
                             "CMP_PHYTATE", T.BY_NAME["CMP_PHYTATE"])[0]
        self.assertEqual(p.tier, 2)
        self.assertIn("unprocessed", p.reasons[0])

    def test_instant_coffee_is_probably_flavouring(self):
        spec = T.BY_NAME["BEV_TEA_COFFEE"]
        got = {p.ingredient.name: p.tier for p in T.name_proposals(table(
            ing("instant coffee granules", "Beverages"), ing("brewed coffee", "Beverages"), ing("steak"), ing("coffee creamer")),
            "BEV_TEA_COFFEE", spec)}
        self.assertEqual(got, {"instant coffee granules": 2, "brewed coffee": 1})

    def test_chocolate_chips_are_not_a_sugar_sweetened_beverage(self):
        spec = T.BY_NAME["BEV_SSB"]
        self.assertEqual(T.name_proposals(table(ing("chocolate chips"), ing("baking soda"), ing("soda bread")), "BEV_SSB", spec), [])
        self.assertEqual(names(T.name_proposals(table(ing("cola"), ing("lemonade")), "BEV_SSB", spec)), ["cola", "lemonade"])


class NutrientBoundaries(unittest.TestCase):
    """NUT_VITC: 'high' (20% of 90 mg) at the 85 g vegetable reference amount."""

    def one(self, value, code="NUT_VITC", category=VEG, desc="Broccoli, raw", name="broccoli", extra=None, **kw):
        nutrients = {C.NUTRIENT_CODES[code].nutrients[0]: value}
        nutrients.update(extra or {})
        props, unj = T.nutrient_proposals(table(ing(name, category, nutrients, desc, **kw)), code)
        return props, unj

    def test_exactly_on_the_line_passes_just_below_fails(self):
        line = value_for("NUT_VITC", 85, 0.20)
        self.assertEqual(len(self.one(line * (1 + 1e-9))[0]), 1)
        self.assertEqual(self.one(line * (1 - 1e-9))[0], [])

    def test_near_the_line_is_tier_2_clear_of_it_is_tier_1(self):
        line = value_for("NUT_VITC", 85, 0.20)
        near = self.one(line * 1.10)[0][0]
        clear = self.one(line * (C.REVIEW_MARGIN + 0.05))[0][0]
        self.assertEqual((near.tier, clear.tier), (2, 1))
        self.assertIn("within", near.reasons[0])

    def test_margin_boundary(self):
        line = value_for("NUT_VITC", 85, 0.20)
        self.assertEqual(self.one(line * C.REVIEW_MARGIN * (1 + 1e-9))[0][0].tier, 1)
        self.assertEqual(self.one(line * C.REVIEW_MARGIN * (1 - 1e-9))[0][0].tier, 2)

    def test_margin_is_configurable(self):
        line = value_for("NUT_VITC", 85, 0.20)
        with mock.patch.object(T, "REVIEW_MARGIN", 1.0):
            self.assertEqual(self.one(line * 1.05)[0][0].tier, 1)

    def test_evidence_states_the_arithmetic(self):
        p = self.one(value_for("NUT_VITC", 85, 0.50))[0][0]
        self.assertAlmostEqual(p.pct_at_basis, 50.0, places=3)
        self.assertEqual(p.basis_g, 85)
        self.assertIn("85 g", p.evidence)
        self.assertIn("vegetables", p.basis_label.lower())
        self.assertEqual(p.threshold_pct, 20.0)

    def test_source_level_is_half_the_high_level_for_iron(self):
        # 15% of the iron DV in 130 g of canned beans: a "source" (10%), not "high" (20%).
        v = value_for("NUT_NONHEME_IRON", 130, 0.15)
        props, _ = self.one(v, "NUT_NONHEME_IRON", LEG, "Beans, black turtle, mature seeds, canned", "black beans")
        self.assertEqual(len(props), 1)
        high = dataclasses.replace(C.NUTRIENT_CODES["NUT_NONHEME_IRON"], level="high")
        with mock.patch.dict(C.NUTRIENT_CODES, {"NUT_NONHEME_IRON": high}):
            props, _ = self.one(v, "NUT_NONHEME_IRON", LEG, "Beans, black turtle, mature seeds, canned", "black beans")
        self.assertEqual(props, [])

    def test_ten_percent_boundary_for_source_codes(self):
        line = value_for("NUT_VITD", 110, 0.10)
        ok, _ = self.one(line * 1.3, "NUT_VITD", "Finfish and Shellfish Products", "Fish, salmon, raw", "salmon")
        no, _ = self.one(line * 0.99, "NUT_VITD", "Finfish and Shellfish Products", "Fish, salmon, raw", "salmon")
        self.assertEqual((len(ok), len(no)), (1, 0))

    def test_zero_is_never_a_source(self):
        self.assertEqual(self.one(0.0)[0], [])

    def test_missing_nutrient_row_is_not_a_candidate_and_not_a_guess(self):
        props, unj = T.nutrient_proposals(table(ing("broccoli", VEG, {}, "Broccoli, raw")), "NUT_VITC")
        self.assertEqual((props, unj), ([], []))

    def test_category_filter(self):
        v = value_for("NUT_VITC", 85, 1.0)
        self.assertEqual(self.one(v, category="Beef Products")[0], [])

    def test_unknown_reference_amount_is_unjudged_only_if_the_old_basis_would_have_tagged_it(self):
        v = value_for("NUT_VITC", 100, 0.5)
        props, unj = self.one(v, name="garlic", desc="Garlic, raw", serving=100)
        self.assertEqual(props, [])
        self.assertEqual(len(unj), 1)
        self.assertIsNone(unj[0].tier)
        self.assertIn("typical_serving_g", unj[0].evidence)
        # a food the old basis would not have tagged is simply not reported
        props, unj = self.one(0.01, name="garlic", desc="Garlic, raw", serving=100)
        self.assertEqual((props, unj), ([], []))
        # no serving at all: nothing to compare
        props, unj = self.one(v, name="garlic", desc="Garlic, raw", serving=None)
        self.assertEqual((props, unj), ([], []))

    def test_legacy_typical_serving_basis_is_still_available(self):
        v = value_for("NUT_VITC", 230, 0.30)  # passes only at a 230 g household 'serving'
        legacy = dataclasses.replace(C.NUTRIENT_CODES["NUT_VITC"], basis="typical_serving")
        with mock.patch.dict(C.NUTRIENT_CODES, {"NUT_VITC": legacy}):
            props, _ = self.one(v, category=FRUIT, name="avocado", desc="Avocados, raw", serving=230)
        self.assertEqual(len(props), 1)
        self.assertEqual(props[0].basis_g, 230)
        # at the FDA reference amount (avocado = 50 g) the same food is nowhere near
        self.assertEqual(self.one(v, category=FRUIT, name="avocado", desc="Avocados, raw", serving=230)[0], [])


class OrVersusAnd(unittest.TestCase):
    CODE = "ING_VITC_FOLATE_VEG"

    def props(self, nutrients, category=VEG):
        return T.nutrient_proposals(table(ing("artichoke hearts", category, nutrients, "Artichokes, frozen, unprepared")), self.CODE)[0]

    def test_or_one_nutrient_is_enough(self):
        folate_only = {"Vitamin_C": 1.0, "Folate": value_for_folate(0.30, 85)}
        self.assertEqual(len(self.props(folate_only)), 1)

    def test_or_neither_nutrient_is_not_enough(self):
        self.assertEqual(self.props({"Vitamin_C": 1.0, "Folate": 1.0}), [])

    def test_all_requires_both(self):
        both = dataclasses.replace(C.NUTRIENT_CODES[self.CODE], combine="all")
        with mock.patch.dict(C.NUTRIENT_CODES, {self.CODE: both}):
            self.assertEqual(self.props({"Vitamin_C": 1.0, "Folate": value_for_folate(0.30, 85)}), [])
            self.assertEqual(len(self.props({"Vitamin_C": 80.0, "Folate": value_for_folate(0.30, 85)})), 1)

    def test_all_needs_both_values_present(self):
        both = dataclasses.replace(C.NUTRIENT_CODES[self.CODE], combine="all")
        with mock.patch.dict(C.NUTRIENT_CODES, {self.CODE: both}):
            self.assertEqual(self.props({"Folate": value_for_folate(0.5, 85)}), [])

    def test_fruit_is_not_a_vegetable(self):
        self.assertEqual(self.props({"Vitamin_C": 200.0, "Folate": 200.0}, category=FRUIT), [])


def value_for_folate(pct, grams):
    return pct * C.DAILY_VALUE["Folate"] * 100.0 / grams


class UsdaEvidenceFlags(unittest.TestCase):
    V = value_for("NUT_VITC", 85, 1.0)

    def tier(self, **kw):
        props, _ = T.nutrient_proposals(table(ing(kw.pop("name", "broccoli"), VEG, {"Vitamin_C": self.V}, **kw)), "NUT_VITC")
        return props[0]

    def test_clean_alias_match_is_tier_1(self):
        p = self.tier(desc="Broccoli, raw")
        self.assertEqual((p.tier, p.reasons), (1, []))

    def test_weak_fuzzy_or_alias_match_is_tier_2(self):
        for by in ("fuzzy", "alias"):
            p = self.tier(desc="Broccoli, raw", by=by, score=C.WEAK_MATCH_SCORE - 1)
            self.assertEqual(p.tier, 2, by)
            self.assertIn("weak USDA match", p.reasons[0])

    def test_score_at_the_cutoff_is_not_weak_and_manual_has_no_score(self):
        self.assertEqual(self.tier(desc="Broccoli, raw", by="fuzzy", score=C.WEAK_MATCH_SCORE).tier, 1)
        self.assertEqual(self.tier(desc="Broccoli, raw", by="manual", score=None).tier, 1)

    def test_enriched_and_fortified_foods_are_reviewed(self):
        for d in ("Rice, white, long-grain, enriched, cooked", "Cereal, fortified with iron",
                  "Applesauce, canned, unsweetened, with added ascorbic acid"):
            self.assertEqual(self.tier(desc=d).tier, 2, d)

    def test_unenriched_and_not_fortified_are_not_flagged(self):
        for d in ("Pasta, dry, unenriched", "Cereals, oats, regular and quick, not fortified, dry"):
            self.assertEqual(self.tier(desc=d).tier, 1, d)

    def test_excluded_evidence_is_blocked_tier_3_and_says_why(self):
        huge = 1e6  # large enough to qualify even at a 0.5 g spice reference amount, so the exclusion is what is tested
        for name in ("cheese", "milk", "ground coriander", "unsweetened applesauce"):
            props, _ = T.nutrient_proposals(table(ing(name, VEG, {"Vitamin_C": huge}, "Anything")), "NUT_VITC")
            self.assertEqual(props[0].tier, 3, name)
            self.assertTrue(props[0].reasons[0].startswith("blocked:"), name)

    def test_missing_description_does_not_crash(self):
        self.assertEqual(self.tier(desc=None).tier, 1)


class PairExclusionBehaviour(unittest.TestCase):
    def props(self, code, name, nutrients, category="Dairy and Egg Products", desc="Milk, buttermilk, fluid, whole"):
        return T.nutrient_proposals(table(ing(name, category, nutrients, desc)), code)[0]

    def test_buttermilk_vitamin_d_is_blocked_tier_3(self):
        for name in ("buttermilk", "low-fat buttermilk"):
            p = self.props("NUT_VITD", name, {"Vitamin_D": 1.3})
            self.assertEqual(len(p), 1, name)
            self.assertEqual(p[0].tier, 3, name)
            self.assertTrue(p[0].reasons[0].startswith("blocked:"))
            self.assertIn("fortification", p[0].reasons[0])

    def test_the_same_food_is_still_judged_for_other_codes(self):
        # Calcium for buttermilk is unaffected by the vitamin D exclusion.
        p = self.props("NUT_CALCIUM", "buttermilk", {"Calcium": 115.0})
        self.assertEqual(len(p), 1)
        self.assertNotEqual(p[0].tier, 3)

    def test_other_vitamin_d_foods_are_unaffected(self):
        fish = "Finfish and Shellfish Products"
        p = self.props("NUT_VITD", "salmon fillets", {"Vitamin_D": 11.0}, fish, "Fish, salmon, Atlantic, farmed, raw")
        self.assertEqual((len(p), p[0].tier), (1, 1))

    def test_a_blocked_pair_never_reaches_the_tier_1_list(self):
        props, _ = T.build_all(table(ing("buttermilk", DAIRY, {"Vitamin_D": 1.3}, "Milk, buttermilk, fluid, whole")))
        self.assertEqual(T.tier1_by_code(props)["NUT_VITD"], [])


class EmitMigration(unittest.TestCase):
    def setUp(self):
        self.ings = table(
            ing("black beans", LEG, {"Iron": 1.9}, "Beans, black turtle, mature seeds, canned"),
            ing("Hellmann's mayonnaise", "Fats and Oils", {"Vitamin_K": 163.0}, "Mayonnaise"),
            ing("spinach", VEG, {"Vitamin_C": 28.1, "Vitamin_K": 482.9}, "Spinach, raw"),
            ing("garlic", VEG, {}, "Garlic, raw"),
            ing("Rice", GRAIN, {}, "Rice, white, raw"),
        )
        self.props, _ = T.build_all(self.ings)

    def test_rows_are_tier_1_identity_or_nutrient_only(self):
        rows = T.tier1_rows(self.props)
        self.assertTrue(rows)
        self.assertTrue({c for c, _, _ in rows} <= {"identity", "nutrient"})
        flat = {(code, p.ingredient.name): p.tier for code, ps in self.props.items() for p in ps}
        for cat, code, name in rows:
            self.assertEqual(flat[(code, name)], 1)
        tier1 = sum(1 for t in flat.values() if t == 1)
        self.assertEqual(len(rows), tier1)

    def test_order_is_fixed_category_then_code_then_name(self):
        rows = T.tier1_rows(self.props)
        order = {c: n for n, c in enumerate(C.CATEGORIES)}
        keys = [(order[c], code, n.lower(), n) for c, code, n in rows]
        self.assertEqual(keys, sorted(keys))

    def test_render_is_deterministic_and_contains_every_row_once(self):
        rows = T.tier1_rows(self.props)
        text = T.render_migration(rows)
        self.assertEqual(text, T.render_migration(list(rows)))
        for cat, code, name in rows:
            self.assertEqual(text.count("(%s, '%s', '%s')" % (T._sql(name), code, cat)), 1, (code, name))

    def test_header_counts_match_the_rows(self):
        rows = T.tier1_rows(self.props)
        text = T.render_migration(rows)
        self.assertIn("%d (ingredient, rule code) pairs" % len(rows), text)
        self.assertIn("identity  %3d" % sum(1 for r in rows if r[0] == "identity"), text)
        self.assertIn("nutrient  %3d" % sum(1 for r in rows if r[0] == "nutrient"), text)

    def test_apostrophes_are_escaped(self):
        self.assertEqual(T._sql("Hellmann's mayonnaise"), "'Hellmann''s mayonnaise'")
        text = T.render_migration([("nutrient", "NUT_VITK", "Hellmann's mayonnaise")])
        self.assertIn("('Hellmann''s mayonnaise', 'NUT_VITK', 'nutrient')", text)

    def test_the_migration_is_transactional_idempotent_and_never_deletes(self):
        text = T.render_migration(T.tier1_rows(self.props))
        self.assertIn("BEGIN;", text)
        self.assertTrue(text.rstrip().endswith("COMMIT;"))
        self.assertIn("ON CONFLICT (ingredient_id, rule_code) DO NOTHING", text)
        # "ON COMMIT DROP" is the temp table cleaning itself up; no real table may be deleted from or altered.
        self.assertNotRegex(text, r"\b(DELETE|UPDATE|TRUNCATE|ALTER)\b")
        self.assertNotRegex(text, r"(?<!COMMIT )\bDROP\b")

    def test_every_validation_the_task_requires_is_in_the_sql(self):
        text = T.render_migration(T.tier1_rows(self.props))
        for needle in ("unknown rule code", "no ingredient named", "is ambiguous", "must never be tagged directly",
                       "repeats an (ingredient, rule code) pair", "only identity and nutrient tags", "reconciliation failed"):
            self.assertIn(needle, text)

    def test_a_curated_compound_row_cannot_be_emitted(self):
        with mock.patch.dict(C.COMPOUND_SOURCES, {"CMP_OXALATE": "a real reference"}):
            props, _ = T.build_all(table(ing("spinach")))
        self.assertEqual([p.tier for p in props["CMP_OXALATE"]], [1])
        with self.assertRaises(ValueError):
            T.tier1_rows(props)

    def test_duplicate_rows_are_refused(self):
        props, _ = T.build_all(table(ing("garlic")))
        dup = props["ING_ALLIUM"][0]
        props["ING_ALLIUM"].append(dup)
        with self.assertRaises(ValueError):
            T.tier1_rows(props)

    def test_emit_writes_a_file_and_returns_the_count(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "m.sql"
            n = T.emit_migration(path, self.props)
            self.assertEqual(n, len(T.tier1_rows(self.props)))
            self.assertEqual(path.read_text(), T.render_migration(T.tier1_rows(self.props)))

    def test_tier_2_and_3_and_unjudged_never_appear(self):
        ings = table(ing("buttermilk", DAIRY, {"Vitamin_D": 1.3}, "Milk, buttermilk, fluid, whole"),     # tier 3
                     ing("potato", VEG, {"Vitamin_C": value_for("NUT_VITC", 110, 0.22)}, "Potatoes, raw"),  # tier 2
                     ing("garlic", VEG, {"Vitamin_C": 31.2}, "Garlic, raw", serving=136))               # unjudged for vitamin C
        props, _ = T.build_all(ings)
        text = T.render_migration(T.tier1_rows(props))
        self.assertNotIn("'buttermilk', 'NUT_VITD'", text)
        self.assertNotIn("'potato', 'NUT_VITC'", text)
        self.assertNotIn("'garlic', 'NUT_VITC'", text)
        self.assertIn("'garlic', 'ING_ALLIUM', 'identity'", text)   # identity does not need a reference amount


class ReferenceAmountRealism(unittest.TestCase):
    """The reason the basis changed: a household measure lets a garnish pass as a rich source."""

    def test_parsley_is_judged_on_4_g_not_a_cup(self):
        parsley = ing("parsley", VEG, {"Iron": 6.2}, "Parsley, fresh", serving=60)
        props, _ = T.nutrient_proposals(table(parsley), "NUT_NONHEME_IRON")
        self.assertEqual(props, [])  # 6.2 mg/100 g x 4 g is ~1% of the iron DV
        legacy = dataclasses.replace(C.NUTRIENT_CODES["NUT_NONHEME_IRON"], basis="typical_serving")
        with mock.patch.dict(C.NUTRIENT_CODES, {"NUT_NONHEME_IRON": legacy}):
            props, _ = T.nutrient_proposals(table(parsley), "NUT_NONHEME_IRON")
        self.assertEqual(len(props), 1)  # the old behaviour: 3.7 mg of iron from a 'cup' of parsley

    def test_dry_rice_is_45_g_not_a_185_g_cup(self):
        rice = ing("rice", GRAIN, {"Iron": 4.31}, "Rice, white, long-grain, regular, raw, enriched", serving=185)
        props, _ = T.nutrient_proposals(table(rice), "NUT_NONHEME_IRON")
        self.assertEqual(props[0].basis_g, 45)
        self.assertEqual(props[0].tier, 2)  # 10.8% DV, and fortified

    def test_median_recipe_use_is_informational_only(self):
        broccoli = ing("broccoli", VEG, {"Vitamin_C": value_for("NUT_VITC", 85, 1.0)}, "Broccoli, raw", grams=[10, 20, 30])
        p = T.nutrient_proposals(table(broccoli), "NUT_VITC")[0][0]
        self.assertAlmostEqual(p.median_recipe_pct, 100 * (value_for("NUT_VITC", 85, 1.0) / 100 * 20 / 90), places=6)
        self.assertEqual(p.tier, 1)  # tiny real use does not demote: the reference amount already handles garnishes


class BuildAllAndCategories(unittest.TestCase):
    def setUp(self):
        self.ings = table(
            ing("black beans", LEG, {"Iron": 1.9, "Vitamin_C": 0.0}, "Beans, black turtle, mature seeds, canned"),
            ing("broccoli", VEG, {"Vitamin_C": 89.2, "Vitamin_K": 101.6, "Folate": 63.0}, "Broccoli, raw"),
            ing("rice", GRAIN, {"Iron": 4.31}, "Rice, white, long-grain, raw, enriched"),
            ing("garlic cloves", VEG, {"Vitamin_C": 31.2}, "Garlic, raw", serving=136),
            ing("spinach", VEG, {"Vitamin_C": 28.1, "Vitamin_K": 482.9, "Vitamin_A": 469.0, "Iron": 2.71, "Folate": 194.0}, "Spinach, raw"),
        )
        self.props, self.unj = T.build_all(self.ings)

    def test_every_code_is_present_even_when_empty(self):
        self.assertEqual(set(self.props), set(C.NUTRIENT_CODES) | set(T.BY_NAME))
        self.assertEqual(set(self.unj), set(self.props))

    def test_one_ingredient_can_earn_several_codes(self):
        codes = sorted(c for c, rows in self.props.items() if any(p.ingredient.name == "broccoli" for p in rows))
        self.assertGreaterEqual(len(codes), 3)
        self.assertIn("NUT_VITC", codes)
        self.assertIn("NUT_VITK", codes)
        self.assertIn("ING_VITC_FOLATE_VEG", codes)

    def test_no_duplicate_ingredient_code_pairs(self):
        seen = set()
        for code, rows in self.props.items():
            for p in rows:
                key = (code, p.ingredient.ingredient_id)
                self.assertNotIn(key, seen)
                seen.add(key)

    def test_proposals_know_their_own_code_and_category(self):
        for code, rows in self.props.items():
            for p in rows + self.unj[code]:
                self.assertEqual(p.code, code)
                self.assertEqual(p.category, C.category_of(code))

    def test_by_category_partitions_every_code_exactly_once(self):
        split = T.by_category(self.props)
        self.assertEqual(set(split), set(C.CATEGORIES))
        flat = [c for cat in split.values() for c in cat]
        self.assertEqual(sorted(flat), sorted(self.props))
        self.assertEqual(len(flat), len(set(flat)))

    def test_garlic_is_judged_by_identity_and_unjudged_by_nutrient(self):
        self.assertIn("garlic cloves", names(self.props["ING_ALLIUM"]))
        self.assertEqual(names(self.props["NUT_VITC"]), ["broccoli", "spinach"])
        self.assertIn("garlic cloves", names(self.unj["NUT_VITC"]))

    def test_tier_1_by_code_can_be_limited_to_one_category(self):
        everything = T.tier1_by_code(self.props)
        ident = T.tier1_by_code(self.props, "identity")
        self.assertTrue(set(ident) < set(everything))
        self.assertTrue(all(C.category_of(c) == "identity" for c in ident))
        self.assertEqual(T.tier1_by_code(self.props, "curated_compound")["CMP_OXALATE"], [])

    def test_a_second_run_gives_identical_proposals(self):
        again, _ = T.build_all(self.ings)
        flatten = lambda d: sorted((c, p.ingredient.ingredient_id, p.tier) for c, r in d.items() for p in r)
        self.assertEqual(flatten(self.props), flatten(again))


class Export(unittest.TestCase):
    def setUp(self):
        ings = table(ing("black beans", LEG, {"Iron": 1.9}, "Beans, black turtle, mature seeds, canned"),
                     ing("broccoli", VEG, {"Vitamin_C": 89.2}, "Broccoli, raw", grams=[20]),
                     ing("spinach", VEG, {"Vitamin_C": 28.1}, "Spinach, raw"),
                     ing("garlic", VEG, {"Vitamin_C": 31.2}, "Garlic, raw", serving=136))
        self.props, self.unj = T.build_all(ings)

    def read(self, path):
        with open(path, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def test_single_export_has_the_documented_columns_and_all_categories(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "all.csv"
            T.export_csv(path, self.props, self.unj)
            rows = self.read(path)
        self.assertEqual(list(rows[0]), T.CSV_HEADER)
        self.assertEqual({r["category"] for r in rows}, {"identity", "nutrient", "curated_compound"})

    def test_export_includes_unjudged_rows_with_no_tier(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "all.csv"
            T.export_csv(path, self.props, self.unj)
            rows = self.read(path)
        garlic = [r for r in rows if r["ingredient"] == "garlic" and r["code"] == "NUT_VITC"]
        self.assertEqual(len(garlic), 1)
        self.assertEqual((garlic[0]["tier"], garlic[0]["confidence"]), ("", "Unjudged"))

    def test_category_filter_on_export(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "n.csv"
            T.export_csv(path, self.props, self.unj, category="nutrient")
            self.assertEqual({r["category"] for r in self.read(path)}, {"nutrient"})

    def test_export_by_category_writes_one_file_per_reviewer(self):
        with tempfile.TemporaryDirectory() as d:
            paths = T.export_by_category(Path(d) / "sub", self.props, self.unj)
            self.assertEqual([Path(p).name for p in paths], ["identity.csv", "nutrient.csv", "curated_compound.csv"])
            for p in paths:
                rows = self.read(p)
                self.assertTrue(rows, p)
                self.assertEqual({r["category"] for r in rows}, {Path(p).stem})

    def test_export_row_carries_the_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "all.csv"
            T.export_csv(path, self.props, self.unj)
            r = [x for x in self.read(path) if x["ingredient"] == "broccoli" and x["code"] == "NUT_VITC"][0]
        self.assertEqual((r["level"], r["threshold_pct_dv"], r["basis_g"], r["how"]), ("high", "20", "85", "nutrient"))
        self.assertEqual(r["usda_description"], "Broccoli, raw")
        self.assertNotEqual(r["median_recipe_pct_dv"], "")

    def test_export_writes_a_file_and_nothing_else(self):
        # It takes no connection at all.
        import inspect
        self.assertNotIn("conn", inspect.signature(T.export_csv).parameters)


class FakeResult:
    def __init__(self, n):
        self.rowcount = n


class FakeConn:
    """Records what would be sent to a database. Never connects to anything."""

    def __init__(self, rowcounts=None):
        self.calls, self.commits, self._rowcounts = [], 0, list(rowcounts or [])

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return FakeResult(self._rowcounts.pop(0) if self._rowcounts else len(params[0]))

    def commit(self):
        self.commits += 1


class ApplyTierOne(unittest.TestCase):
    def test_inserts_only_the_ids_it_is_given_one_statement_per_code(self):
        conn = FakeConn()
        written = T.apply_tier1(conn, {"NUT_VITC": ["a", "b"], "ING_ALLIUM": ["c"]})
        self.assertEqual(written, 3)
        self.assertEqual([c[1] for c in conn.calls], [(["a", "b"], "NUT_VITC"), (["c"], "ING_ALLIUM")])

    def test_is_idempotent_by_construction(self):
        conn = FakeConn()
        T.apply_tier1(conn, {"NUT_VITC": ["a"]})
        self.assertIn("ON CONFLICT (ingredient_id, rule_code) DO NOTHING", conn.calls[0][0])

    def test_counts_only_new_rows(self):
        self.assertEqual(T.apply_tier1(FakeConn(rowcounts=[0, 2]), {"A": ["x"], "B": ["y", "z"]}), 2)

    def test_empty_codes_send_nothing_but_still_commit_once(self):
        conn = FakeConn()
        self.assertEqual(T.apply_tier1(conn, {"NUT_VITC": [], "ING_ALLIUM": []}), 0)
        self.assertEqual((conn.calls, conn.commits), ([], 1))

    def test_commits_exactly_once(self):
        conn = FakeConn()
        T.apply_tier1(conn, {"A": ["x"], "B": ["y"]})
        self.assertEqual(conn.commits, 1)

    def test_what_it_is_handed_never_includes_tiers_2_and_3(self):
        ings = table(
            ing("spinach", VEG, {"Vitamin_C": 28.1}, "Spinach, raw"),                                     # tier 1
            ing("potato", VEG, {"Vitamin_C": value_for("NUT_VITC", 110, 0.22)}, "Potatoes, raw"),          # tier 2 (near the line)
            ing("milk", DAIRY, {"Calcium": 115.0}, "Milk, buttermilk, fluid, whole"),                      # tier 3 (excluded)
            ing("chocolate chips"),                                                                        # no proposal
        )
        props, _ = T.build_all(ings)
        tiers = {(code, p.ingredient.name): p.tier for code, rows in props.items() for p in rows}
        self.assertEqual(tiers[("NUT_VITC", "spinach")], 1)
        self.assertEqual(tiers[("NUT_VITC", "potato")], 2)
        self.assertEqual(tiers[("NUT_CALCIUM", "milk")], 3)

        by_id = {i.ingredient_id: i.name for i in ings.values()}
        sent = {(code, by_id[i]) for code, ids in T.tier1_by_code(props).items() for i in ids}
        self.assertIn(("NUT_VITC", "spinach"), sent)
        self.assertNotIn(("NUT_VITC", "potato"), sent)      # tier 2
        self.assertNotIn(("NUT_CALCIUM", "milk"), sent)     # tier 3
        self.assertEqual({n for _, n in sent if n == "chocolate chips"}, set())  # never proposed

    def test_compound_tags_are_not_sent_without_a_citation(self):
        ings = table(ing("spinach"), ing("swiss chard"))
        props, _ = T.build_all(ings)
        self.assertEqual(T.tier1_by_code(props, "curated_compound"), {"CMP_OXALATE": [], "CMP_PHYTATE": [], "BEV_TEA_COFFEE": []})


class Refusals(unittest.TestCase):
    def test_refused_codes_are_never_proposed(self):
        proposed = set(C.NUTRIENT_CODES) | set(T.BY_NAME)
        self.assertEqual(proposed & set(T.REFUSED), set())

    def test_composites_are_refused_not_tagged(self):
        for code in ("ING_LEGUME_GRAIN", "ING_ALLIUM_GRAIN_LEGUME"):
            self.assertIn(code, T.REFUSED)
            self.assertNotIn(code, T.BY_NAME)

    def test_refusal_reasons_are_substantive(self):
        for code, reason in T.REFUSED.items():
            self.assertGreater(len(reason), 20, code)


if __name__ == "__main__":
    unittest.main()
