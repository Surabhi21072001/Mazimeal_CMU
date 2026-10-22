#!/usr/bin/env python3
"""Tests for the Phase 2 business-rules layer.

Run with either:
    python3 -m unittest tests.test_rules -v
    pytest tests/test_rules.py -v

Detection and idempotency tests use an in-memory SQLite database that mirrors
the relevant columns of the Postgres schema, so no live database or driver is
needed. The Excel-parsing tests read the real workbook when it is present and
skip cleanly if it is not.
"""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import detect_rules  # noqa: E402
import import_rules  # noqa: E402
import recipe_facts  # noqa: E402
import evaluate_rules  # noqa: E402
from evaluate_rules import ApplicabilityStatus  # noqa: E402

WORKBOOK = REPO / "IN WORK - MaziMeal Recipe Optimization Rules (1).xlsx"


# --------------------------------------------------------------------------
# SQLite fixture mirroring the relevant schema
# --------------------------------------------------------------------------
def build_fixture_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    c = conn.cursor()
    c.executescript(
        """
        CREATE TABLE recipes (
            recipe_id TEXT PRIMARY KEY,
            recipe_name TEXT NOT NULL
        );
        CREATE TABLE ingredients (
            ingredient_id TEXT PRIMARY KEY,
            ingredient_name TEXT NOT NULL
        );
        CREATE TABLE recipe_ingredients (
            recipe_id TEXT NOT NULL,
            ingredient_id TEXT NOT NULL,
            PRIMARY KEY (recipe_id, ingredient_id)
        );
        CREATE TABLE rule_codes (
            code TEXT PRIMARY KEY,
            code_type TEXT NOT NULL,
            display_name TEXT NOT NULL
        );
        CREATE TABLE ingredient_rule_tags (
            ingredient_id TEXT NOT NULL,
            rule_code TEXT NOT NULL,
            PRIMARY KEY (ingredient_id, rule_code)
        );
        CREATE TABLE business_rules (
            rule_id TEXT PRIMARY KEY,
            rule_name TEXT NOT NULL,
            trigger_code TEXT,
            automation_status TEXT,
            is_active INTEGER NOT NULL DEFAULT 1
        );
        """
    )

    recipes = [
        ("r-garlic-tomato", "Garlic Tomato Pasta"),
        ("r-plain", "Plain Boiled Rice"),
        ("r-kale", "Kale Salad"),
    ]
    ingredients = [
        ("i-garlic", "garlic"),
        ("i-tomato", "tomatoes"),
        ("i-rice", "white rice"),
        ("i-kale", "kale"),
    ]
    recipe_ingredients = [
        ("r-garlic-tomato", "i-garlic"),
        ("r-garlic-tomato", "i-tomato"),
        ("r-plain", "i-rice"),
        ("r-kale", "i-kale"),
    ]
    rule_codes = [
        ("ING_GARLIC", "ING", "Garlic"),
        ("ING_TOMATO", "ING", "Tomato"),
        ("ING_CRUCIFER", "ING", "Crucifer"),
    ]
    tags = [
        ("i-garlic", "ING_GARLIC"),
        ("i-tomato", "ING_TOMATO"),
        ("i-kale", "ING_CRUCIFER"),
    ]
    rules = [
        ("BIO-002", "Crush garlic and rest", "ING_GARLIC", "recipe_safe", 1),
        ("BIO-003", "Cook tomatoes with oil", "ING_TOMATO", "recipe_safe", 1),
        # Inactive rule: must never be detected.
        ("BIO-099", "Inactive crucifer rule", "ING_CRUCIFER", "recipe_safe", 0),
    ]
    c.executemany("INSERT INTO recipes VALUES (?,?)", recipes)
    c.executemany("INSERT INTO ingredients VALUES (?,?)", ingredients)
    c.executemany("INSERT INTO recipe_ingredients VALUES (?,?)", recipe_ingredients)
    c.executemany("INSERT INTO rule_codes VALUES (?,?,?)", rule_codes)
    c.executemany("INSERT INTO ingredient_rule_tags VALUES (?,?)", tags)
    c.executemany("INSERT INTO business_rules VALUES (?,?,?,?,?)", rules)
    conn.commit()
    return conn


# --------------------------------------------------------------------------
# Excel parsing
# --------------------------------------------------------------------------
class TestExcelParsing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not WORKBOOK.exists():
            raise unittest.SkipTest(f"workbook not found: {WORKBOOK}")
        cls.rules, cls.problems = import_rules.read_rules(WORKBOOK)

    def test_all_sheets_parsed(self):
        self.assertFalse(self.rules.empty)
        self.assertEqual(len(self.rules), 54)

    def test_categories_present(self):
        cats = set(self.rules["rule_category"])
        self.assertEqual(
            cats, {"bioavailability", "food_synergy", "inhibitor", "glycemic"}
        )

    def test_counts_by_category(self):
        counts = self.rules["rule_category"].value_counts().to_dict()
        self.assertEqual(counts["bioavailability"], 15)
        self.assertEqual(counts["food_synergy"], 12)
        self.assertEqual(counts["inhibitor"], 12)
        self.assertEqual(counts["glycemic"], 15)

    def test_no_duplicate_rule_ids(self):
        ids = list(self.rules["rule_id"])
        self.assertEqual(len(ids), len(set(ids)))
        # And the validator reported no duplicate problems.
        self.assertFalse([p for p in self.problems if "duplicate rule_id" in p])

    def test_every_rule_has_trigger_and_action(self):
        bad_trigger = [p for p in self.problems if "missing trigger_code" in p]
        bad_action = [p for p in self.problems if "missing both action" in p]
        self.assertEqual(bad_trigger, [])
        self.assertEqual(bad_action, [])

    def test_enumerated_values_valid(self):
        auto = set(self.rules["automation_status"].dropna())
        self.assertTrue(auto.issubset(import_rules.VALID_AUTOMATION))
        tiers = set(self.rules["evidence_tier"].dropna())
        self.assertTrue(tiers.issubset(import_rules.VALID_TIER))


class TestCodeExtraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not WORKBOOK.exists():
            raise unittest.SkipTest(f"workbook not found: {WORKBOOK}")
        rules, _ = import_rules.read_rules(WORKBOOK)
        cls.codes = import_rules.collect_codes(rules)

    def test_expected_count(self):
        self.assertEqual(len(self.codes), 121)

    def test_known_codes_present(self):
        for code in ("ING_GARLIC", "ING_TOMATO", "NUT_IRON", "PROC_CRUSH_REST"):
            self.assertIn(code, self.codes)

    def test_code_type_is_prefix(self):
        self.assertEqual(self.codes["ING_GARLIC"], "ING")
        self.assertEqual(self.codes["NUT_IRON"], "NUT")

    def test_humanize_code(self):
        self.assertEqual(import_rules.humanize_code("ING_GARLIC"), "Garlic")
        self.assertEqual(
            import_rules.humanize_code("PROC_CRUSH_REST"), "Crush Rest"
        )


class TestNormalization(unittest.TestCase):
    def test_blank_to_null(self):
        for blank in (None, "", "   ", "nan", "NaT", float("nan")):
            self.assertEqual(import_rules.sql_str(blank), "NULL")

    def test_quote_escaping(self):
        self.assertEqual(import_rules.sql_str("al dente"), "'al dente'")
        self.assertEqual(import_rules.sql_str("it's"), "'it''s'")

    def test_date_normalization(self):
        self.assertEqual(import_rules.norm_date("2026-09-17"), "'2026-09-17'")
        self.assertEqual(import_rules.norm_date(""), "NULL")
        self.assertEqual(import_rules.norm_date(None), "NULL")


class TestIngredientMatching(unittest.TestCase):
    def test_confident_and_review_split(self):
        names = [
            "garlic", "garlic powder", "garlic cloves",
            "corn", "corn syrup", "cornstarch",
            "eggplant", "eggs",
            "broccoli", "kale",
        ]
        valid = set(import_rules.INGREDIENT_CODE_MAP)
        confident, review = import_rules.match_ingredients(names, valid)
        conf_pairs = set(confident)
        # confident
        self.assertIn(("garlic", "ING_GARLIC"), conf_pairs)
        self.assertIn(("garlic cloves", "ING_GARLIC"), conf_pairs)
        self.assertIn(("corn", "ING_CORN"), conf_pairs)
        self.assertIn(("broccoli", "ING_CRUCIFER"), conf_pairs)
        self.assertIn(("kale", "ING_CRUCIFER"), conf_pairs)
        # false positives routed to review, never confident
        review_names = {r[0] for r in review}
        for bad in ("garlic powder", "corn syrup", "cornstarch", "eggplant"):
            self.assertIn(bad, review_names)
            self.assertNotIn(bad, {c[0] for c in confident})


# --------------------------------------------------------------------------
# Detection + idempotency against the SQLite fixture
# --------------------------------------------------------------------------
class TestDetection(unittest.TestCase):
    def setUp(self):
        self.conn = build_fixture_db()

    def tearDown(self):
        self.conn.close()

    def test_detects_garlic_and_tomato(self):
        rules = detect_rules.detect_rules(self.conn, "r-garlic-tomato")
        ids = sorted(r.rule_id for r in rules)
        self.assertEqual(ids, ["BIO-002", "BIO-003"])

    def test_reason_names_the_ingredient(self):
        rules = detect_rules.detect_rules(self.conn, "r-garlic-tomato")
        by_id = {r.rule_id: r for r in rules}
        self.assertIn("ING_GARLIC", by_id["BIO-002"].reason)
        self.assertIn("garlic", by_id["BIO-002"].reason)

    def test_automation_status_returned(self):
        rules = detect_rules.detect_rules(self.conn, "r-garlic-tomato")
        self.assertTrue(all(r.automation_status == "recipe_safe" for r in rules))

    def test_recipe_with_no_applicable_rules(self):
        rules = detect_rules.detect_rules(self.conn, "r-plain")
        self.assertEqual(rules, [])

    def test_inactive_rule_not_returned(self):
        # r-kale carries ING_CRUCIFER, whose only rule BIO-099 is inactive.
        rules = detect_rules.detect_rules(self.conn, "r-kale")
        self.assertEqual(rules, [])

    def test_unknown_recipe_returns_empty(self):
        self.assertEqual(detect_rules.detect_rules(self.conn, "does-not-exist"), [])

    def test_tag_uniqueness_enforced(self):
        # Composite PK must reject a duplicate (ingredient_id, rule_code).
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO ingredient_rule_tags VALUES (?,?)",
                ("i-garlic", "ING_GARLIC"),
            )

    def test_detection_is_idempotent_after_reinsert_attempt(self):
        # Re-running tag inserts with OR IGNORE should not change detection.
        self.conn.execute(
            "INSERT OR IGNORE INTO ingredient_rule_tags VALUES (?,?)",
            ("i-garlic", "ING_GARLIC"),
        )
        self.conn.commit()
        rules = detect_rules.detect_rules(self.conn, "r-garlic-tomato")
        self.assertEqual(sorted(r.rule_id for r in rules), ["BIO-002", "BIO-003"])

    def test_detect_rules_from_facts_matches_recipe_id_path(self):
        # The two entry points must agree.
        facts = recipe_facts.build_recipe_facts(self.conn, "r-garlic-tomato")
        from_facts = detect_rules.detect_rules_from_facts(self.conn, facts)
        from_id = detect_rules.detect_rules(self.conn, "r-garlic-tomato")
        self.assertEqual(
            [r.rule_id for r in from_facts], [r.rule_id for r in from_id]
        )


# --------------------------------------------------------------------------
# A richer fixture for RecipeFacts: quantity/unit, nutrition, steps, metadata.
# --------------------------------------------------------------------------
def build_facts_fixture_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    c = conn.cursor()
    c.executescript(
        """
        CREATE TABLE recipes (
            recipe_id TEXT PRIMARY KEY,
            recipe_name TEXT NOT NULL,
            meal_category TEXT,
            servings INTEGER,
            calories_per_serving REAL,
            data_source TEXT,
            recipe_description TEXT
        );
        CREATE TABLE ingredients (
            ingredient_id TEXT PRIMARY KEY,
            ingredient_name TEXT NOT NULL
        );
        CREATE TABLE recipe_ingredients (
            recipe_id TEXT NOT NULL,
            ingredient_id TEXT NOT NULL,
            quantity REAL,
            unit TEXT,
            PRIMARY KEY (recipe_id, ingredient_id)
        );
        CREATE TABLE ingredient_rule_tags (
            ingredient_id TEXT NOT NULL,
            rule_code TEXT NOT NULL,
            PRIMARY KEY (ingredient_id, rule_code)
        );
        CREATE TABLE business_rules (
            rule_id TEXT PRIMARY KEY,
            rule_name TEXT NOT NULL,
            trigger_code TEXT,
            automation_status TEXT,
            is_active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE recipe_nutrition (
            recipe_id TEXT NOT NULL,
            nutrient_id TEXT NOT NULL,
            per_serving REAL NOT NULL,
            unit TEXT,
            PRIMARY KEY (recipe_id, nutrient_id)
        );
        CREATE TABLE recipe_steps (
            recipe_id TEXT NOT NULL,
            step_number INTEGER NOT NULL,
            instruction TEXT NOT NULL,
            PRIMARY KEY (recipe_id, step_number)
        );
        """
    )
    c.executemany(
        "INSERT INTO recipes VALUES (?,?,?,?,?,?,?)",
        [
            ("r-pasta", "Garlic Tomato Pasta", "Dinner", 4, 520.0, "Food.com", "A simple pasta."),
            ("r-bare", "Bare Recipe", "Lunch", 2, None, "Manual", None),
        ],
    )
    c.executemany(
        "INSERT INTO ingredients VALUES (?,?)",
        [("i-garlic", "garlic"), ("i-tomato", "tomatoes"),
         ("i-pasta", "fettuccine"), ("i-salt", "salt")],
    )
    c.executemany(
        "INSERT INTO recipe_ingredients VALUES (?,?,?,?)",
        [
            ("r-pasta", "i-garlic", 3, "cloves"),
            ("r-pasta", "i-tomato", 2, "whole"),
            ("r-pasta", "i-pasta", 200, "g"),
            # r-bare: one ingredient, no tags, no nutrition, no steps.
            ("r-bare", "i-salt", 1, "tsp"),
        ],
    )
    c.executemany(
        "INSERT INTO ingredient_rule_tags VALUES (?,?)",
        [
            ("i-garlic", "ING_GARLIC"),
            ("i-tomato", "ING_TOMATO"),
            ("i-pasta", "ING_PASTA"),
            # garlic also carries a second code to test multi-tag grouping.
            ("i-garlic", "CMP_ALLICIN"),
        ],
    )
    c.executemany(
        "INSERT INTO business_rules VALUES (?,?,?,?,?)",
        [
            ("BIO-002", "Crush garlic and rest", "ING_GARLIC", "recipe_safe", 1),
            ("BIO-003", "Cook tomatoes with oil", "ING_TOMATO", "recipe_safe", 1),
        ],
    )
    c.executemany(
        "INSERT INTO recipe_nutrition VALUES (?,?,?,?)",
        [
            ("r-pasta", "Energy", 520.0, "kcal"),
            ("r-pasta", "Macro_Protein", 18.0, "g"),
            ("r-pasta", "Macro_Carbohydrate", 72.0, "g"),
        ],
    )
    c.executemany(
        "INSERT INTO recipe_steps VALUES (?,?,?)",
        [
            ("r-pasta", 1, "Crush the garlic and rest 10 minutes."),
            ("r-pasta", 2, "Cook tomatoes in oil."),
            ("r-pasta", 3, "Toss with pasta."),
        ],
    )
    conn.commit()
    return conn


class TestRecipeFacts(unittest.TestCase):
    def setUp(self):
        self.conn = build_facts_fixture_db()

    def tearDown(self):
        self.conn.close()

    def test_recipe_with_several_ingredients(self):
        facts = recipe_facts.build_recipe_facts(self.conn, "r-pasta")
        self.assertEqual(facts.recipe_name, "Garlic Tomato Pasta")
        names = [i.ingredient_name for i in facts.ingredients]
        self.assertEqual(names, ["fettuccine", "garlic", "tomatoes"])  # ordered by name

    def test_quantity_and_unit_populated(self):
        facts = recipe_facts.build_recipe_facts(self.conn, "r-pasta")
        garlic = next(i for i in facts.ingredients if i.ingredient_name == "garlic")
        self.assertEqual(garlic.quantity, 3.0)
        self.assertEqual(garlic.unit, "cloves")

    def test_ingredient_with_multiple_rule_tags(self):
        facts = recipe_facts.build_recipe_facts(self.conn, "r-pasta")
        garlic = next(i for i in facts.ingredients if i.ingredient_name == "garlic")
        self.assertEqual(garlic.rule_codes, ("CMP_ALLICIN", "ING_GARLIC"))

    def test_ingredient_codes_union(self):
        facts = recipe_facts.build_recipe_facts(self.conn, "r-pasta")
        self.assertEqual(
            facts.ingredient_codes,
            frozenset({"ING_GARLIC", "ING_TOMATO", "ING_PASTA", "CMP_ALLICIN"}),
        )

    def test_recipe_with_no_rule_tags(self):
        facts = recipe_facts.build_recipe_facts(self.conn, "r-bare")
        self.assertEqual(facts.ingredient_codes, frozenset())
        salt = facts.ingredients[0]
        self.assertEqual(salt.rule_codes, ())

    def test_nutrition_native_ids_present(self):
        facts = recipe_facts.build_recipe_facts(self.conn, "r-pasta")
        # Native recipe_nutrition ids, NOT NUT_* codes.
        self.assertEqual(facts.nutrients["Energy"], 520.0)
        self.assertEqual(facts.nutrients["Macro_Protein"], 18.0)
        self.assertNotIn("NUT_IRON", facts.nutrients)
        self.assertEqual(facts.metadata["nutrient_id_scheme"], "native_recipe_nutrition")
        self.assertEqual(facts.metadata["nutrient_units"]["Energy"], "kcal")

    def test_missing_nutrition_is_empty_not_fabricated(self):
        facts = recipe_facts.build_recipe_facts(self.conn, "r-bare")
        self.assertEqual(facts.nutrients, {})

    def test_recipe_with_instructions(self):
        facts = recipe_facts.build_recipe_facts(self.conn, "r-pasta")
        self.assertIsNotNone(facts.instructions)
        self.assertIn("Crush the garlic", facts.instructions)
        self.assertTrue(facts.instructions.startswith("1. "))

    def test_recipe_without_instructions(self):
        facts = recipe_facts.build_recipe_facts(self.conn, "r-bare")
        self.assertIsNone(facts.instructions)

    def test_as_dict_serializable(self):
        import json
        facts = recipe_facts.build_recipe_facts(self.conn, "r-pasta")
        d = facts.as_dict()
        # ingredient_codes serialized as a sorted list; round-trips through json.
        self.assertEqual(d["ingredient_codes"],
                         sorted(["ING_GARLIC", "ING_TOMATO", "ING_PASTA", "CMP_ALLICIN"]))
        self.assertIsInstance(d["ingredients"], list)
        json.dumps(d, default=str)  # must not raise

    def test_unknown_recipe_raises(self):
        with self.assertRaises(recipe_facts.RecipeNotFound):
            recipe_facts.build_recipe_facts(self.conn, "nope")

    def test_detection_from_rich_facts(self):
        facts = recipe_facts.build_recipe_facts(self.conn, "r-pasta")
        rules = detect_rules.detect_rules_from_facts(self.conn, facts)
        self.assertEqual(sorted(r.rule_id for r in rules), ["BIO-002", "BIO-003"])


# --------------------------------------------------------------------------
# Condition evaluation
# --------------------------------------------------------------------------
def make_facts(instructions, codes=(), ingredient_names=None):
    """Build a RecipeFacts directly (no DB) for evaluator unit tests."""
    ingredient_names = ingredient_names or []
    ings = tuple(
        recipe_facts.RecipeIngredientFact(
            ingredient_id=f"i-{i}", ingredient_name=n, quantity=None, unit=None,
            rule_codes=(),
        )
        for i, n in enumerate(ingredient_names)
    )
    return recipe_facts.RecipeFacts(
        recipe_id="r-x", recipe_name="Test Recipe", ingredients=ings,
        ingredient_codes=frozenset(codes), nutrients={},
        instructions=instructions, metadata={},
    )


def candidate(rule_id, trigger_code, name="Rule", auto="recipe_safe"):
    return detect_rules.DetectedRule(
        rule_id=rule_id, rule_name=name, automation_status=auto,
        trigger_code=trigger_code, reason="candidate",
    )


class TestProcessFacts(unittest.TestCase):
    def test_garlic_chopped_detected_with_evidence(self):
        facts = make_facts("1. Mince the garlic and sauté immediately.",
                           codes={"ING_GARLIC"})
        pf = evaluate_rules.extract_process_facts(facts)
        self.assertTrue(pf["garlic_chopped"].value)
        self.assertIn("Mince the garlic", pf["garlic_chopped"].evidence)
        self.assertTrue(pf["garlic_heated"].value)
        self.assertFalse(pf["garlic_rest_period_detected"].value)

    def test_rest_period_detected(self):
        facts = make_facts("1. Mince garlic and let it rest for 10 minutes before sautéing.",
                           codes={"ING_GARLIC"})
        pf = evaluate_rules.extract_process_facts(facts)
        self.assertTrue(pf["garlic_rest_period_detected"].value)

    def test_no_instructions_marks_unavailable(self):
        facts = make_facts(None, codes={"ING_GARLIC"})
        pf = evaluate_rules.extract_process_facts(facts)
        self.assertFalse(pf["instructions_available"].value)

    def test_saute_spellings(self):
        for verb in ("saute", "sauté", "sautee"):
            facts = make_facts(f"1. {verb} the onion.", codes={"ING_GARLIC"})
            pf = evaluate_rules.extract_process_facts(facts)
            self.assertTrue(pf["garlic_heated"].value, verb)

    def test_fat_present_from_ingredient(self):
        facts = make_facts("1. Cook tomatoes.", codes={"ING_TOMATO"},
                           ingredient_names=["tomatoes", "olive oil"])
        pf = evaluate_rules.extract_process_facts(facts)
        self.assertTrue(pf["fat_present"].value)
        self.assertIn("olive oil", pf["fat_present"].evidence)


class TestEvaluation(unittest.TestCase):
    def _eval(self, rule_id, trigger, instructions, codes, names=None):
        facts = make_facts(instructions, codes=codes, ingredient_names=names)
        pf = evaluate_rules.extract_process_facts(facts)
        return evaluate_rules.evaluate_rule(candidate(rule_id, trigger), facts, pf)

    # BIO-002 garlic
    def test_bio002_applicable(self):
        r = self._eval("BIO-002", "ING_GARLIC",
                       "1. Mince garlic and sauté immediately.", {"ING_GARLIC"})
        self.assertEqual(r.applicability_status, ApplicabilityStatus.APPLICABLE)
        self.assertIn("no rest period detected", r.conditions_passed)

    def test_bio002_not_applicable_rest_present(self):
        r = self._eval("BIO-002", "ING_GARLIC",
                       "1. Mince garlic and allow it to rest for 10 minutes before sautéing.",
                       {"ING_GARLIC"})
        self.assertEqual(r.applicability_status, ApplicabilityStatus.NOT_APPLICABLE)

    def test_bio002_needs_context_no_instructions(self):
        r = self._eval("BIO-002", "ING_GARLIC", None, {"ING_GARLIC"})
        self.assertEqual(r.applicability_status, ApplicabilityStatus.NEEDS_CONTEXT)
        self.assertIn("unavailable", r.reason)

    def test_bio002_verbs_chop_crush_mince(self):
        for verb in ("chop garlic", "crush garlic", "mince garlic"):
            r = self._eval("BIO-002", "ING_GARLIC", f"1. {verb} and fry.", {"ING_GARLIC"})
            self.assertEqual(r.applicability_status, ApplicabilityStatus.APPLICABLE, verb)

    # BIO-003 tomato
    def test_bio003_applicable_cooked_no_fat(self):
        r = self._eval("BIO-003", "ING_TOMATO", "1. Simmer the tomatoes.",
                       {"ING_TOMATO"}, names=["tomatoes"])
        self.assertEqual(r.applicability_status, ApplicabilityStatus.APPLICABLE)

    def test_bio003_not_applicable_cooked_with_fat(self):
        r = self._eval("BIO-003", "ING_TOMATO", "1. Simmer tomatoes in olive oil.",
                       {"ING_TOMATO"}, names=["tomatoes", "olive oil"])
        self.assertEqual(r.applicability_status, ApplicabilityStatus.NOT_APPLICABLE)

    # GLY-007 pasta
    def test_gly007_not_applicable_al_dente(self):
        r = self._eval("GLY-007", "ING_PASTA", "1. Cook pasta until al dente.",
                       {"ING_PASTA"})
        self.assertEqual(r.applicability_status, ApplicabilityStatus.NOT_APPLICABLE)

    def test_gly007_applicable_no_al_dente(self):
        r = self._eval("GLY-007", "ING_PASTA", "1. Boil the pasta 12 minutes.",
                       {"ING_PASTA"})
        self.assertEqual(r.applicability_status, ApplicabilityStatus.APPLICABLE)

    # BIO-011 egg
    def test_bio011_not_applicable_egg_cooked(self):
        r = self._eval("BIO-011", "ING_EGG", "1. Fry the eggs.", {"ING_EGG"})
        self.assertEqual(r.applicability_status, ApplicabilityStatus.NOT_APPLICABLE)

    # Unimplemented evaluator
    def test_unimplemented_rule_needs_context(self):
        r = self._eval("BIO-005", "ING_LEAFY_GREEN", "1. Cook the greens.",
                       {"ING_LEAFY_GREEN"})
        self.assertEqual(r.applicability_status, ApplicabilityStatus.NEEDS_CONTEXT)
        self.assertEqual(r.reason, "condition evaluator not implemented")

    def test_evaluated_rule_serializable(self):
        import json
        r = self._eval("BIO-002", "ING_GARLIC", "1. Mince garlic and fry.", {"ING_GARLIC"})
        json.dumps(r.as_dict(), default=str)
        self.assertEqual(r.as_dict()["applicability_status"], "APPLICABLE")


class TestEvaluationEndToEnd(unittest.TestCase):
    """Full evaluate_recipe_rules flow against the rich SQLite fixture."""
    def setUp(self):
        self.conn = build_facts_fixture_db()
        # Add instructions-backed rules + pasta so multiple candidates evaluate.
        cur = self.conn.cursor()
        cur.execute("INSERT INTO business_rules VALUES ('GLY-007','Use al dente pasta','ING_PASTA','recipe_safe',1)")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_multiple_candidates_evaluated(self):
        evaluated = evaluate_rules.evaluate_recipe_rules(self.conn, "r-pasta")
        ids = {e.rule_id for e in evaluated}
        self.assertIn("BIO-002", ids)
        self.assertIn("BIO-003", ids)
        # Every result carries a status and the candidate flag.
        self.assertTrue(all(e.candidate for e in evaluated))
        self.assertTrue(all(isinstance(e.applicability_status, ApplicabilityStatus)
                            for e in evaluated))

    def test_candidate_detection_parity_unchanged(self):
        # evaluate_recipe_rules candidates == detect_rules_from_facts output.
        facts = recipe_facts.build_recipe_facts(self.conn, "r-pasta")
        detected = {d.rule_id for d in detect_rules.detect_rules_from_facts(self.conn, facts)}
        evaluated = {e.rule_id for e in evaluate_rules.evaluate_recipe_rules(self.conn, "r-pasta")}
        self.assertEqual(detected, evaluated)


if __name__ == "__main__":
    unittest.main(verbosity=2)
