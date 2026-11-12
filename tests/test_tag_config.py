#!/usr/bin/env python3
"""Tests for scripts/tag_config.py: thresholds, reference amounts, categories.

Pure Python: no database, no network, no third-party packages.

    python3 -m unittest tests.test_tag_config -v
"""
from __future__ import annotations

import dataclasses
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import tag_config as C  # noqa: E402
import tag_ingredients as T  # noqa: E402

VEG, FRUIT, DAIRY = "Vegetables and Vegetable Products", "Fruits and Fruit Juices", "Dairy and Egg Products"
LEG, GRAIN, SEEDS = "Legumes and Legume Products", "Cereal Grains and Pasta", "Nut and Seed Products"
FISH, SPICE, FATS = "Finfish and Shellfish Products", "Spices and Herbs", "Fats and Oils"


class LevelsAndDailyValues(unittest.TestCase):
    def test_levels_are_the_two_fda_definitions(self):
        # 21 CFR 101.54(b)(1) "high" >= 20%; 101.54(c)(1) "good source / contains" from 10%.
        self.assertEqual(C.LEVELS, {"high": 0.20, "source": 0.10})

    def test_daily_values_cover_every_nutrient_a_code_uses(self):
        for code, cfg in C.NUTRIENT_CODES.items():
            for n in cfg.nutrients:
                self.assertIn(n, C.DAILY_VALUE, "%s uses %s which has no Daily Value" % (code, n))

    def test_daily_values_are_positive(self):
        for name, value in C.DAILY_VALUE.items():
            self.assertGreater(value, 0, name)

    def test_review_constants_are_not_regulatory_and_are_sane(self):
        self.assertGreaterEqual(C.REVIEW_MARGIN, 1.0)
        self.assertTrue(0 < C.WEAK_MATCH_SCORE <= 100)


class NutrientCodeConfig(unittest.TestCase):
    def test_every_code_is_well_formed(self):
        for code, cfg in C.NUTRIENT_CODES.items():
            self.assertIn(cfg.level, C.LEVELS, code)
            self.assertIn(cfg.combine, ("all", "any"), code)
            self.assertIn(cfg.basis, ("reference_amount", "typical_serving"), code)
            self.assertTrue(cfg.nutrients, code)
            self.assertTrue(cfg.wording, "%s must quote the rule wording it came from" % code)
            self.assertTrue(cfg.rules, "%s must name the rules it serves" % code)
            self.assertTrue(cfg.approver, code)

    def test_default_basis_is_the_fda_reference_amount(self):
        for code, cfg in C.NUTRIENT_CODES.items():
            self.assertEqual(cfg.basis, "reference_amount", code)

    def test_rule_wording_decides_the_level(self):
        # "source" / "containing" -> 10%; "rich" -> 20%. This is the audit's central finding.
        self.assertEqual(C.NUTRIENT_CODES["NUT_NONHEME_IRON"].level, "source")
        self.assertEqual(C.NUTRIENT_CODES["NUT_VITD"].level, "source")
        for code in ("NUT_VITC", "NUT_CALCIUM", "NUT_CAROTENOIDS"):
            self.assertEqual(C.NUTRIENT_CODES[code].level, "high", code)

    def test_folate_code_is_or_over_vegetables_only(self):
        cfg = C.NUTRIENT_CODES["ING_VITC_FOLATE_VEG"]
        self.assertEqual(cfg.combine, "any")
        self.assertEqual(cfg.categories, (VEG,))
        self.assertEqual(set(cfg.nutrients), {"Vitamin_C", "Folate"})

    def test_plant_iron_excludes_animal_categories_by_construction(self):
        cats = C.NUTRIENT_CODES["NUT_NONHEME_IRON"].categories
        for animal in ("Beef Products", "Finfish and Shellfish Products", "Poultry Products", "Pork Products"):
            self.assertNotIn(animal, cats)

    def test_config_is_immutable(self):
        cfg = C.NUTRIENT_CODES["NUT_VITC"]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            cfg.level = "source"  # type: ignore[misc]


class Categories(unittest.TestCase):
    def test_exactly_three_categories(self):
        self.assertEqual(C.CATEGORIES, ("identity", "nutrient", "curated_compound"))

    def test_every_taggable_code_has_a_category_and_nothing_extra(self):
        taggable = set(C.NUTRIENT_CODES) | set(T.BY_NAME)
        self.assertEqual(set(C.CODE_CATEGORY), taggable)

    def test_every_category_is_valid_and_used(self):
        self.assertTrue(set(C.CODE_CATEGORY.values()) <= set(C.CATEGORIES))
        self.assertEqual(set(C.CODE_CATEGORY.values()), set(C.CATEGORIES))

    def test_nutrient_codes_are_the_nutrient_category(self):
        for code in C.NUTRIENT_CODES:
            self.assertEqual(C.category_of(code), C.NUTRIENT, code)

    def test_name_only_classes_split_into_identity_and_compound(self):
        for code in ("ING_LEGUME", "ING_GRAIN", "ING_GRAIN_LEGUME", "ING_ALLIUM", "ING_SEED", "BEV_SSB"):
            self.assertEqual(C.category_of(code), C.IDENTITY, code)
        # phytate, oxalate and tannin are not measured: curated knowledge.
        for code in ("CMP_PHYTATE", "CMP_OXALATE", "BEV_TEA_COFFEE"):
            self.assertEqual(C.category_of(code), C.COMPOUND, code)

    def test_unknown_code_is_an_error_not_a_default(self):
        with self.assertRaises(KeyError):
            C.category_of("ING_MADE_UP")

    def test_every_category_has_a_named_reviewer(self):
        self.assertEqual(set(C.CATEGORY_REVIEWER), set(C.CATEGORIES))
        for cat, who in C.CATEGORY_REVIEWER.items():
            self.assertTrue(who.strip(), cat)

    def test_no_compound_has_a_citation_yet(self):
        # If this fails someone added a source: good, but then update the tier-cap tests too.
        self.assertEqual(C.COMPOUND_SOURCES, {})


class EvidenceExclusions(unittest.TestCase):
    def test_every_exclusion_gives_a_reason(self):
        for name, reason in C.EVIDENCE_EXCLUDED.items():
            self.assertGreater(len(reason), 20, name)

    def test_known_bad_matches_are_excluded(self):
        for name in ("cheese", "milk", "skim milk", "evaporated milk", "unsweetened applesauce", "ground coriander"):
            self.assertIn(name, C.EVIDENCE_EXCLUDED)


class PairExclusions(unittest.TestCase):
    def test_each_exclusion_names_a_real_code_and_gives_a_reason(self):
        self.assertTrue(C.PAIR_EXCLUSIONS)
        for (code, name), reason in C.PAIR_EXCLUSIONS.items():
            self.assertIn(code, C.NUTRIENT_CODES, code)
            self.assertTrue(name.strip())
            self.assertGreater(len(reason), 40, (code, name))

    def test_buttermilk_vitamin_d_is_excluded_until_fortification_is_confirmed(self):
        self.assertIn(("NUT_VITD", "buttermilk"), C.PAIR_EXCLUSIONS)
        self.assertIn(("NUT_VITD", "low-fat buttermilk"), C.PAIR_EXCLUSIONS)
        self.assertIn("fortification", C.PAIR_EXCLUSIONS[("NUT_VITD", "buttermilk")])

    def test_a_pair_exclusion_is_not_a_whole_ingredient_exclusion(self):
        # buttermilk is still judged for the other codes; only the vitamin D pair is held back.
        self.assertNotIn("buttermilk", C.EVIDENCE_EXCLUDED)


class ReferenceAmounts(unittest.TestCase):
    """21 CFR 101.12(b), as read from eCFR. Each case names the table row it comes from."""

    def grams(self, name, category=None, desc=None):
        r = C.reference_amount(name, category, desc)
        return r[0] if r else None

    def test_table_regexes_all_compile(self):
        for ref in C.REFERENCE_AMOUNTS:
            for rx in (ref.name_rx, ref.desc_rx):
                if rx:
                    re.compile(rx)

    def test_every_row_has_a_label(self):
        for ref in C.REFERENCE_AMOUNTS:
            self.assertTrue(ref.label)

    def test_every_known_amount_is_positive(self):
        for ref in C.REFERENCE_AMOUNTS:
            if ref.grams is not None:
                self.assertGreater(ref.grams, 0, ref.label)

    CASES = [
        # (name, category, USDA description, expected grams, 101.12(b) row)
        ("parsley", VEG, "Parsley, fresh", 4, "garnish or flavor"),
        ("parsley flakes", SPICE, "Spices, parsley, dried", 4, "parsley, fresh or dried"),
        ("fresh coriander", VEG, "Coriander (cilantro) leaves, raw", 4, "garnish"),
        ("chives", VEG, "Chives, raw", 4, "garnish"),
        ("diced pimentos", VEG, "Pimentos, canned", 4, "pimento"),
        ("green onions", VEG, "Onions, spring or scallions", 30, "chili peppers, green onion"),
        ("jalapeno chile", VEG, "Peppers, jalapeno, raw", 30, "hot peppers"),
        ("sun-dried tomatoes", VEG, "Tomatoes, sun-dried", 5, "dried tomatoes"),
        ("tomato paste", VEG, "Tomato products, canned, paste", 30, "vegetable pastes"),
        ("tomato puree", VEG, "Tomato products, canned, puree", 60, "vegetable purees"),
        ("wasabi", VEG, "Wasabi, root, raw", 5, "minor condiments"),
        ("hash brown", VEG, "Potatoes, hash brown", 70, "hash browns"),
        ("sweet potatoes", VEG, "Sweet potato, raw", 110, "potatoes, plain"),
        ("canned pumpkin", VEG, "Pumpkin, canned", 130, "pumpkin"),
        ("diced tomatoes", VEG, "Tomatoes, red, ripe, canned, stewed", 130, "canned or stewed tomatoes"),
        ("broccoli", VEG, "Broccoli, raw", 85, "all other vegetables"),
        ("zucchini", VEG, "Squash, summer, zucchini, raw", 85, "summer squash is NOT winter squash"),
        ("Brussels sprouts", VEG, "Brussels sprouts, raw", 85, "ordinary vegetable, not 'sprouts'"),
        ("lemon juice", FRUIT, "Lemon juice, raw", 5, "juices used as ingredients"),
        ("lemon wedge", FRUIT, "Lemons, raw", 50, "lemon, lime"),
        ("limes", FRUIT, "Limes, raw", 50, "lemon, lime"),
        ("avocado", FRUIT, "Avocados, raw", 50, "avocado"),
        ("raisins", FRUIT, "Raisins, dried", 40, "dried fruit"),
        ("strawberries", FRUIT, "Strawberries, raw", 140, "all other fruits"),
        ("black olives", FRUIT, "Olives, ripe, canned", 15, "olives"),
        ("parmesan cheese", DAIRY, "Cheese, parmesan", 5, "grated hard cheese"),
        ("cottage cheese", DAIRY, "Cheese, cottage", 110, "cottage"),
        ("ricotta cheese", DAIRY, "Cheese, ricotta", 55, "cheese as ingredient"),
        ("swiss cheese", DAIRY, "Cheese, swiss", 30, "cheese, all others"),
        ("plain yogurt", DAIRY, "Yogurt, plain", 170, "yogurt"),
        ("evaporated milk", DAIRY, "Milk, canned, evaporated", 30, "evaporated, 30 mL"),
        ("buttermilk", DAIRY, "Milk, buttermilk", 240, "milk"),
        ("firm tofu", LEG, "Tofu, raw, firm", 85, "tofu"),
        ("black beans", LEG, "Beans, black turtle, mature seeds, canned", 130, "beans canned"),
        ("baked beans", LEG, "Beans, baked", 130, "beans in sauce"),
        ("brown lentils", LEG, "Lentils, raw", 35, "beans, dry"),
        ("lentils, cooked", LEG, "Lentils, mature seeds, cooked, boiled", 90, "beans prepared"),
        ("rice", GRAIN, "Rice, white, long-grain, raw", 45, "grains, dry"),
        ("cooked rice", GRAIN, "Rice, white, long-grain, cooked", 140, "grains, prepared"),
        ("spaghetti", GRAIN, "Pasta, dry, unenriched", 55, "pasta, dry"),
        ("cooked pasta", GRAIN, "Pasta, cooked", 140, "pasta, prepared"),
        ("whole wheat flour", GRAIN, "Wheat flour, whole-grain", 30, "flours"),
        ("wheat germ", GRAIN, "Wheat germ, crude", 15, "bran or wheat germ"),
        ("sesame seeds", SEEDS, "Seeds, sesame seeds, whole, dried", 30, "nuts and seeds"),
        ("salmon fillets", FISH, "Fish, salmon, Atlantic, farmed, raw", 110, "fish, uncooked"),
        ("cooked salmon", FISH, "Fish, salmon, cooked", 85, "fish, cooked"),
        ("olive oil", FATS, "Oil, olive", 15, "1 tbsp"),
        ("dried ancho chile powder", SPICE, "Spices, chili powder", 0.5, "spices and herbs"),
    ]

    def test_reference_amounts_against_the_cfr_table(self):
        for name, category, desc, expected, row in self.CASES:
            with self.subTest(name=name, row=row):
                self.assertEqual(self.grams(name, category, desc), expected)

    def test_the_state_of_the_usda_food_decides_prepared_or_dry(self):
        self.assertEqual(self.grams("rice", GRAIN, "Rice, white, raw"), 45)
        self.assertEqual(self.grams("rice", GRAIN, "Rice, white, cooked"), 140)
        self.assertEqual(self.grams("beans", LEG, "Beans, mature seeds, raw"), 35)
        self.assertEqual(self.grams("beans", LEG, "Beans, mature seeds, canned"), 130)

    def test_deliberately_unjudgeable_foods_return_none(self):
        for name, category in (("garlic", VEG), ("minced garlic cloves", VEG), ("orange zest", FRUIT),
                               ("lemon rind", FRUIT), ("bean sprouts", VEG), ("alfalfa sprouts", VEG),
                               ("tahini", SEEDS), ("peanut butter", LEG), ("pumpkin pie filling", VEG)):
            with self.subTest(name=name):
                self.assertIsNone(C.reference_amount(name, category, "anything"))

    def test_unjudgeable_rows_come_before_the_catch_alls(self):
        # garlic is a vegetable; if the 85 g vegetable row were first it would be judged at 85 g.
        self.assertIsNone(C.reference_amount("garlic", VEG, "Garlic, raw"))
        self.assertEqual(C.reference_amount("broccoli", VEG, "Broccoli, raw")[0], 85)

    def test_no_clear_class_returns_none_not_a_guess(self):
        self.assertIsNone(C.reference_amount("quick oats", "Breakfast Cereals", "Cereals, oats, regular and quick, dry"))
        self.assertIsNone(C.reference_amount("couscous", GRAIN, "Couscous, dry"))
        self.assertIsNone(C.reference_amount("something odd", "Unknown group", "x"))

    def test_none_inputs_do_not_crash(self):
        self.assertIsNone(C.reference_amount("", None, None))
        self.assertIsNone(C.reference_amount(None, None, None))

    def test_dairy_rows_do_not_catch_non_dairy_milk(self):
        # coconut milk is not in the dairy group; it must not be measured as 240 mL of milk.
        self.assertNotEqual(self.grams("coconut milk", SEEDS, "Nuts, coconut milk"), 240)
        self.assertIsNone(C.reference_amount("coconut milk", LEG, "x"))

    def test_chive_cream_cheese_is_not_a_garnish(self):
        self.assertEqual(self.grams("chive & onion cream cheese", DAIRY, "Cheese, cream"), 30)

    def test_label_names_the_table_row(self):
        label = C.reference_amount("parsley", VEG, "x")[1]
        self.assertIn("garnish", label.lower())


if __name__ == "__main__":
    unittest.main()
