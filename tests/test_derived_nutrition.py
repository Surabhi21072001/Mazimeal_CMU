#!/usr/bin/env python3
"""Phase 2 (no database): nutrition-derived triggers and the rules GLY-002, 003, 004, 009, INH-011.

    python3 -m unittest tests.test_derived_nutrition -v
"""
from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests"))

import derived_facts as DF  # noqa: E402
import detect_rules  # noqa: E402
import evaluate_rules as ev  # noqa: E402
import nutrition_facts as NF  # noqa: E402
from evaluate_rules import ApplicabilityStatus as S  # noqa: E402
from evaluation_context import EvaluationContext  # noqa: E402
from derived_fixtures import build_db, facts_for  # noqa: E402

A, N, X = S.APPLICABLE, S.NOT_APPLICABLE, S.NEEDS_CONTEXT


def nutr(carb=40.0, protein=10.0, fat=5.0, fiber=3.0, unit_carb="g"):
    return {"Macro_Carbohydrate": (carb, unit_carb), "Macro_Protein": (protein, "g"),
            "Macro_Fat": (fat, "g"), "Fiber": (fiber, "g"), "Energy": (300.0, "kcal")}


def run(rule_id, trigger, facts, ctx=None):
    cand = detect_rules.DetectedRule(rule_id=rule_id, rule_name=rule_id, automation_status="recipe_safe",
                                     trigger_code=trigger, reason="candidate")
    return ev.evaluate_rule(cand, facts, ev.extract_process_facts(facts), ctx)


def reviewed(key, field, op, threshold, unit):
    return NF.NutritionCriterion(key, field, op, threshold, unit, "per_serving", "reviewed", "test", "test")


# ======================================================================================
# Configuration is exactly what the rules say
# ======================================================================================
class TestConfiguration(unittest.TestCase):
    def test_candidate_thresholds_are_the_rule_wording_and_nothing_more(self):
        carb = NF.NUTRITION_RULE_CONFIG["MACRO_CARB"]
        self.assertEqual((carb.field, carb.operator, carb.threshold, carb.unit, carb.basis, carb.review_status),
                         ("Macro_Carbohydrate", ">", 0.0, "g", "per_serving", "wording"))
        fat = NF.NUTRITION_RULE_CONFIG["MACRO_FAT_LOW"]
        self.assertEqual((fat.field, fat.operator, fat.threshold, fat.unit, fat.review_status),
                         ("Macro_Fat", "<=", 0.0, "g", "wording"))
        self.assertIn("carbohydrate-containing", carb.source)
        self.assertIn("fat-free", fat.source)

    def test_no_number_is_invented_for_dominant_rich_or_high(self):
        for rule in ("GLY-003", "GLY-004", "GLY-009", "GLY-011"):
            crit = NF.APPLICABILITY_CRITERIA[rule]
            self.assertIsNone(crit.threshold, rule)
            self.assertEqual(crit.review_status, "unreviewed", rule)
            self.assertFalse(crit.usable(), rule)

    def test_every_criterion_names_its_source_and_basis(self):
        for crit in [*NF.NUTRITION_RULE_CONFIG.values(), *NF.APPLICABILITY_CRITERIA.values()]:
            self.assertTrue(crit.source and crit.reason and crit.basis == "per_serving", crit.key)
            self.assertIn(crit.operator, NF.OPERATORS)


# ======================================================================================
# Normalisation: basis, units, availability, verification
# ======================================================================================
class TestNormalisation(unittest.TestCase):
    def test_per_serving_is_used_as_published(self):
        r = NF.read_nutrient(facts_for(nutrition=nutr(carb=45)), "Macro_Carbohydrate", "g")
        self.assertEqual((r.value, r.unit, r.basis), (45.0, "g", "per_serving"))

    def test_per_recipe_values_are_divided_by_servings(self):
        f = facts_for(nutrition=nutr(carb=200), servings=4, metadata={"nutrition_basis": "per_recipe"})
        r = NF.read_nutrient(f, "Macro_Carbohydrate", "g")
        self.assertEqual(r.value, 50.0)
        self.assertIn("per recipe / 4 servings", r.normalization)

    def test_per_recipe_without_servings_is_refused(self):
        f = facts_for(nutrition=nutr(carb=200), metadata={"nutrition_basis": "per_recipe"})
        r = NF.read_nutrient(f, "Macro_Carbohydrate", "g")
        self.assertFalse(r.ok)
        self.assertEqual(r.missing_field, "recipe.servings")

    def test_a_basis_that_cannot_become_per_serving_is_refused(self):
        for basis in ("per_100g", None, "mystery"):
            f = facts_for(nutrition=nutr(), metadata={"nutrition_basis": basis})
            self.assertFalse(NF.read_nutrient(f, "Macro_Carbohydrate", "g").ok, basis)

    def test_milligrams_are_converted_to_grams_and_unknown_units_are_refused(self):
        r = NF.read_nutrient(facts_for(nutrition=nutr(carb=45000, unit_carb="mg")), "Macro_Carbohydrate", "g")
        self.assertEqual(r.value, 45.0)
        r = NF.read_nutrient(facts_for(nutrition=nutr(carb=45, unit_carb="oz")), "Macro_Carbohydrate", "g")
        self.assertFalse(r.ok)

    def test_missing_nutrient_is_unavailable_and_named(self):
        r = NF.read_nutrient(facts_for(nutrition={}), "Macro_Carbohydrate", "g")
        self.assertEqual((r.ok, r.missing_field), (False, "recipe_nutrition.Macro_Carbohydrate"))

    def test_adverse_review_makes_nutrition_unusable(self):
        for verdict in ("implausible", "needs_data"):
            f = facts_for(nutrition=nutr(), metadata={"nutrition_review": {"verdict": verdict}})
            r = NF.read_nutrient(f, "Macro_Carbohydrate", "g")
            self.assertFalse(r.ok, verdict)
            self.assertEqual(r.missing_field, "recipe_nutrition.Macro_Carbohydrate.verification")

    def test_plausible_and_unreviewed_are_usable_and_labelled(self):
        f = facts_for(nutrition=nutr(), metadata={"nutrition_review": {"verdict": "plausible"}})
        self.assertEqual(NF.read_nutrient(f, "Macro_Carbohydrate", "g").verification, "plausible")
        self.assertEqual(NF.read_nutrient(facts_for(nutrition=nutr()), "Macro_Carbohydrate", "g").verification,
                         "unreviewed")

    def test_requiring_review_blocks_an_unreviewed_recipe(self):
        with mock.patch.object(NF, "REQUIRE_PLAUSIBILITY_REVIEW", True):
            self.assertFalse(NF.read_nutrient(facts_for(nutrition=nutr()), "Macro_Carbohydrate", "g").ok)

    def test_available_carbohydrate_is_carb_minus_fibre_floored_at_zero(self):
        self.assertEqual(NF.compute_field(facts_for(nutrition=nutr(carb=40, fiber=8)), "available_carbohydrate", "g").value, 32.0)
        self.assertEqual(NF.compute_field(facts_for(nutrition=nutr(carb=2, fiber=8)), "available_carbohydrate", "g").value, 0.0)
        self.assertFalse(NF.compute_field(facts_for(nutrition={"Macro_Carbohydrate": (40, "g")}),
                                          "available_carbohydrate", "g").ok)


# ======================================================================================
# Threshold boundaries: immediately below, at and above
# ======================================================================================
class TestBoundaries(unittest.TestCase):
    def met(self, criterion, **n):
        return NF.check(facts_for(nutrition=nutr(**n)), criterion)["state"]

    def test_carbohydrate_containing_is_strictly_greater_than_zero(self):
        crit = NF.NUTRITION_RULE_CONFIG["MACRO_CARB"]
        self.assertEqual(self.met(crit, carb=0.0), "not_met")          # at the threshold
        self.assertEqual(self.met(crit, carb=0.1), "met")              # immediately above
        # nothing can be below 0 g; the table has CHECK (per_serving >= 0)

    def test_fat_free_is_at_or_below_zero(self):
        crit = NF.NUTRITION_RULE_CONFIG["MACRO_FAT_LOW"]
        self.assertEqual(self.met(crit, fat=0.0), "met")               # at
        self.assertEqual(self.met(crit, fat=0.1), "not_met")           # immediately above
        self.assertEqual(self.met(crit, fat=0.49), "not_met")          # a labelling '<0.5 g' is NOT applied

    def test_a_reviewed_greater_equal_threshold_on_grams(self):
        crit = reviewed("rich", "Macro_Carbohydrate", ">=", 60.0, "g")
        self.assertEqual(self.met(crit, carb=59.9), "not_met")
        self.assertEqual(self.met(crit, carb=60.0), "met")
        self.assertEqual(self.met(crit, carb=60.1), "met")

    def test_a_reviewed_energy_share_threshold(self):
        crit = reviewed("dominant", "carb_energy_share", ">=", 0.5, "fraction")
        for protein, expect in ((51, "not_met"), (50, "met"), (49, "met")):        # share .495 / .500 / .505
            self.assertEqual(self.met(crit, carb=50, protein=protein, fat=0), expect, protein)

    def test_effective_portions_scale_the_value_before_comparing(self):
        crit = reviewed("high", "available_carbohydrate", ">=", 60.0, "g")
        f = facts_for(nutrition=nutr(carb=33, fiber=3))                 # 30 g per serving
        self.assertEqual(NF.check(f, crit, scale=1.9)["state"], "not_met")   # 57
        self.assertEqual(NF.check(f, crit, scale=2.0)["state"], "met")       # 60
        self.assertEqual(NF.check(f, crit, scale=2.1)["state"], "met")       # 63

    def test_an_unreviewed_criterion_never_compares(self):
        res = NF.check(facts_for(nutrition=nutr()), NF.APPLICABILITY_CRITERIA["GLY-003"])
        self.assertEqual(res["state"], "undefined")


# ======================================================================================
# Candidate facts
# ======================================================================================
class TestCandidateFacts(unittest.TestCase):
    def codes(self, **kw):
        return {f.code: f for f in NF.nutrition_candidate_facts(facts_for(nutrition=kw["n"]) if "n" in kw else kw["f"])}

    def test_carbohydrate_calls_macro_carb_with_value_unit_and_threshold_in_the_evidence(self):
        fact = self.codes(n=nutr(carb=45))["MACRO_CARB"]
        self.assertEqual((fact.source, fact.value, fact.unit, fact.confidence), ("recipe_nutrition", 45.0, "g", "medium"))
        for part in ("Macro_Carbohydrate", "45", "per serving", "> 0", "carbohydrate-containing"):
            self.assertIn(part, fact.evidence)

    def test_no_carbohydrate_does_not_call_the_rule(self):
        self.assertNotIn("MACRO_CARB", self.codes(n=nutr(carb=0.0)))

    def test_fat_free_calls_macro_fat_low_only_at_zero(self):
        self.assertIn("MACRO_FAT_LOW", self.codes(n=nutr(fat=0.0)))
        self.assertNotIn("MACRO_FAT_LOW", self.codes(n=nutr(fat=0.1)))

    def test_missing_nutrition_still_calls_the_rule_as_unknown(self):
        facts = self.codes(f=facts_for(nutrition={}))
        for code in ("MACRO_CARB", "MACRO_FAT_LOW"):
            self.assertIsNone(facts[code].value)
            self.assertEqual(facts[code].confidence, "unknown")

    def test_unverified_nutrition_calls_the_rule_as_unknown(self):
        f = facts_for(nutrition=nutr(), metadata={"nutrition_review": {"verdict": "implausible"}})
        self.assertEqual(self.codes(f=f)["MACRO_CARB"].confidence, "unknown")

    def test_a_plausible_review_raises_confidence(self):
        f = facts_for(nutrition=nutr(), metadata={"nutrition_review": {"verdict": "plausible"}})
        self.assertEqual(self.codes(f=f)["MACRO_CARB"].confidence, "high")


# ======================================================================================
# The rules
# ======================================================================================
class TestGly002(unittest.TestCase):
    def go(self, ingredients=(), ctx=None, codes=(), **n):
        f = facts_for(ingredients=ingredients, nutrition=nutr(**n), codes=codes)
        return run("GLY-002", "MACRO_CARB", f, ctx)

    def test_carbohydrate_with_no_viscous_fibre_is_applicable(self):
        r = self.go(["white rice", "chicken"])
        self.assertEqual(r.applicability_status, A)
        self.assertEqual(r.evidence["personalization"], "not evaluated: no member context supplied")
        self.assertEqual(r.evidence["carbohydrate"]["reading"]["value"], 40.0)

    def test_viscous_fibre_already_present_is_not_applicable(self):
        for name in ("rolled oats", "pearl barley", "okra", "chia seeds", "ground flaxseed", "psyllium husk"):
            r = self.go([name])
            self.assertEqual(r.applicability_status, N, name)
            self.assertEqual(r.conditions_failed, ("viscous fibre source not already present",))

    def test_a_legume_tag_counts(self):
        f = facts_for(ingredients=["black beans"], nutrition=nutr())
        f = replace(f, ingredients=(replace(f.ingredients[0], rule_codes=("ING_LEGUME",)),))
        self.assertEqual(run("GLY-002", "MACRO_CARB", f).applicability_status, N)

    def test_no_carbohydrate_is_not_applicable(self):
        self.assertEqual(self.go(["egg"], carb=0.0).applicability_status, N)

    def test_missing_carbohydrate_needs_context(self):
        r = run("GLY-002", "MACRO_CARB", facts_for(ingredients=["rice"], nutrition={}))
        self.assertEqual(r.applicability_status, X)
        self.assertEqual(r.missing_context[0]["field"], "recipe_nutrition.Macro_Carbohydrate")

    def test_unverified_nutrition_needs_context(self):
        f = facts_for(ingredients=["rice"], nutrition=nutr(), metadata={"nutrition_review": {"verdict": "needs_data"}})
        r = run("GLY-002", "MACRO_CARB", f)
        self.assertEqual(r.applicability_status, X)
        self.assertTrue(r.missing_context[0]["field"].endswith(".verification"))

    def test_gi_condition_requires_review(self):
        r = self.go(["rice"], ctx=EvaluationContext(member_id="m1", conditions=("IBS",)))
        self.assertEqual(r.applicability_status, X)
        self.assertEqual(r.missing_context[0]["field"], "clinical_review.gi_condition")
        self.assertNotIn("ibs", str(r.as_dict()).lower())           # the member's own text is not echoed

    def test_a_member_with_conditions_omitted_is_unknown_not_clear(self):
        r = self.go(["rice"], ctx=EvaluationContext(member_id="m1"))
        self.assertEqual(r.applicability_status, X)
        self.assertEqual(r.missing_context[0]["field"], "user_context.conditions")

    def test_explicitly_no_conditions_is_clear(self):
        r = self.go(["rice"], ctx=EvaluationContext(member_id="m1", conditions=()))
        self.assertEqual(r.applicability_status, A)
        self.assertEqual(r.evidence["personalization"], "evaluated against the member's declared conditions")


class TestGly003And004And009(unittest.TestCase):
    """Dominant / rich have no numeric definition: NEEDS_CONTEXT, unless the recipe already
    does what the rule recommends."""

    def test_gly_003_without_a_definition_needs_context_and_names_it(self):
        r = run("GLY-003", "MACRO_CARB", facts_for(ingredients=["spaghetti"], nutrition=nutr()))
        self.assertEqual(r.applicability_status, X)
        m = r.missing_context[0]
        self.assertEqual(m["field"], "reviewed_definition.carbohydrate_dominant")
        self.assertIn("carb_energy_share", m["reason"])
        self.assertEqual(r.evidence["nutrition"]["criterion"]["review_status"], "unreviewed")
        self.assertIn("energy_share", r.evidence["macros_per_serving"])       # shown to the reviewer

    def test_gly_003_protein_already_present_is_not_applicable_without_needing_a_definition(self):
        for name in ("grilled chicken", "firm tofu", "salmon fish fillet"):
            r = run("GLY-003", "MACRO_CARB", facts_for(ingredients=["pasta", name], nutrition=nutr()))
            self.assertEqual(r.applicability_status, N, name)

    def test_flavourings_are_not_a_protein_source(self):
        """Found on the 400 seed recipes: chicken broth, bouillon, stuffing mix, poultry
        seasoning and fish sauce were counted as 'protein already present'."""
        for name in ("chicken broth", "chicken bouillon cubes", "chicken stove top stuffing mix",
                     "poultry seasoning", "fish sauce", "condensed chicken soup"):
            r = run("GLY-003", "MACRO_CARB", facts_for(ingredients=["pasta", name], nutrition=nutr()))
            self.assertEqual(r.applicability_status, X, name)         # not NOT_APPLICABLE

    def test_spice_seeds_are_not_an_unsaturated_fat_source(self):
        for name in ("celery seed", "mustard seeds", "cumin seed", "caraway seeds", "fish sauce"):
            r = run("GLY-004", "MACRO_CARB", facts_for(ingredients=["rice", name], nutrition=nutr()))
            self.assertEqual(r.applicability_status, X, name)
        r = run("GLY-004", "MACRO_CARB", facts_for(ingredients=["rice", "sesame seeds"], nutrition=nutr()))
        self.assertEqual(r.applicability_status, N)                   # a real seed still counts

    def test_gly_003_with_a_reviewed_threshold_decides_at_the_boundary(self):
        crit = reviewed("carbohydrate_dominant", "carb_energy_share", ">=", 0.5, "fraction")
        with mock.patch.dict(NF.APPLICABILITY_CRITERIA, {"GLY-003": crit}):
            below = run("GLY-003", "MACRO_CARB", facts_for(ingredients=["pasta"], nutrition=nutr(carb=50, protein=51, fat=0)))
            at = run("GLY-003", "MACRO_CARB", facts_for(ingredients=["pasta"], nutrition=nutr(carb=50, protein=50, fat=0)))
            above = run("GLY-003", "MACRO_CARB", facts_for(ingredients=["pasta"], nutrition=nutr(carb=50, protein=49, fat=0)))
        self.assertEqual(below.applicability_status, N)
        self.assertEqual(at.applicability_status, A)
        self.assertEqual(above.applicability_status, A)
        self.assertEqual(at.evidence["classification"]["criterion"]["threshold"], 0.5)
        self.assertEqual(at.evidence["classification"]["reading"]["unit"], "fraction")

    def test_gly_003_kidney_limit_applies_after_the_meal_qualifies(self):
        crit = reviewed("carbohydrate_dominant", "carb_energy_share", ">=", 0.5, "fraction")
        with mock.patch.dict(NF.APPLICABILITY_CRITERIA, {"GLY-003": crit}):
            r = run("GLY-003", "MACRO_CARB", facts_for(ingredients=["pasta"], nutrition=nutr(carb=50, protein=10, fat=0)),
                    EvaluationContext(member_id="m", conditions=("chronic kidney disease",)))
        self.assertEqual(r.applicability_status, X)
        self.assertEqual(r.missing_context[0]["field"], "clinical_review.kidney_disease")

    def test_gly_004_unsaturated_fat_already_present_is_not_applicable(self):
        for name in ("extra virgin olive oil", "walnuts", "sunflower seeds", "avocado", "salmon"):
            r = run("GLY-004", "MACRO_CARB", facts_for(ingredients=["rice", name], nutrition=nutr()))
            self.assertEqual(r.applicability_status, N, name)

    def test_gly_004_otherwise_needs_a_definition_of_dominant(self):
        r = run("GLY-004", "MACRO_CARB", facts_for(ingredients=["rice"], nutrition=nutr()))
        self.assertEqual(r.applicability_status, X)
        self.assertEqual(r.missing_context[0]["field"], "reviewed_definition.carbohydrate_dominant")

    def test_gly_004_names_no_member_limit_so_a_member_is_not_blocked_for_it(self):
        crit = reviewed("carbohydrate_dominant", "carb_energy_share", ">=", 0.5, "fraction")
        with mock.patch.dict(NF.APPLICABILITY_CRITERIA, {"GLY-004": crit}):
            r = run("GLY-004", "MACRO_CARB", facts_for(ingredients=["rice"], nutrition=nutr(carb=50, protein=10, fat=0)),
                    EvaluationContext(member_id="m"))
        self.assertEqual(r.applicability_status, A)

    def test_gly_009_vinegar_already_present_is_not_applicable(self):
        r = run("GLY-009", "MACRO_CARB", facts_for(ingredients=["rice", "rice vinegar"], nutrition=nutr()))
        self.assertEqual(r.applicability_status, N)

    def test_gly_009_otherwise_needs_a_definition_of_rich(self):
        r = run("GLY-009", "MACRO_CARB", facts_for(ingredients=["rice"], nutrition=nutr()))
        self.assertEqual(r.applicability_status, X)
        self.assertEqual(r.missing_context[0]["field"], "reviewed_definition.carbohydrate_rich")

    def test_gly_009_reviewed_boundary_and_reflux_limit(self):
        crit = reviewed("carbohydrate_rich", "Macro_Carbohydrate", ">=", 60.0, "g")
        with mock.patch.dict(NF.APPLICABILITY_CRITERIA, {"GLY-009": crit}):
            self.assertEqual(run("GLY-009", "MACRO_CARB", facts_for(ingredients=["rice"], nutrition=nutr(carb=59.9))).applicability_status, N)
            at = run("GLY-009", "MACRO_CARB", facts_for(ingredients=["rice"], nutrition=nutr(carb=60.0)))
            self.assertEqual(at.applicability_status, A)
            gerd = run("GLY-009", "MACRO_CARB", facts_for(ingredients=["rice"], nutrition=nutr(carb=61)),
                       EvaluationContext(member_id="m", conditions=("GERD",)))
            self.assertEqual(gerd.missing_context[0]["field"], "clinical_review.reflux")

    def test_missing_macros_for_the_share_need_context_naming_them(self):
        crit = reviewed("carbohydrate_dominant", "carb_energy_share", ">=", 0.5, "fraction")
        with mock.patch.dict(NF.APPLICABILITY_CRITERIA, {"GLY-003": crit}):
            r = run("GLY-003", "MACRO_CARB",
                    facts_for(ingredients=["pasta"], nutrition={"Macro_Carbohydrate": (50, "g")}))
        self.assertEqual(r.applicability_status, X)
        self.assertTrue(r.missing_context[0]["field"].startswith("recipe_nutrition."))


class TestInh011(unittest.TestCase):
    CAROTENE = ("NUT_CAROTENOIDS",)

    def facts(self, fat=0.0, tagged=True):
        f = facts_for(ingredients=["steamed carrots", "plain water"], nutrition=nutr(fat=fat))
        if tagged:
            f = replace(f, ingredients=(replace(f.ingredients[0], rule_codes=self.CAROTENE), f.ingredients[1]))
        return f

    def test_fat_free_meal_with_a_carotenoid_source_is_applicable(self):
        r = run("INH-011", "MACRO_FAT_LOW", self.facts())
        self.assertEqual(r.applicability_status, A)
        self.assertEqual(r.evidence["fat"]["reading"]["value"], 0.0)
        self.assertEqual(r.evidence["fat"]["criterion"]["threshold"], 0.0)
        self.assertEqual(r.evidence["fat_soluble_sources"][0]["name"], "steamed carrots")

    def test_any_fat_means_not_fat_free(self):
        r = run("INH-011", "MACRO_FAT_LOW", self.facts(fat=0.1))
        self.assertEqual(r.applicability_status, N)
        self.assertIn("0.1", r.reason)

    def test_fat_free_without_a_fat_soluble_source_is_not_applicable(self):
        self.assertEqual(run("INH-011", "MACRO_FAT_LOW", self.facts(tagged=False)).applicability_status, N)

    def test_missing_fat_needs_context(self):
        r = run("INH-011", "MACRO_FAT_LOW", facts_for(ingredients=["carrots"], nutrition={}))
        self.assertEqual((r.applicability_status, r.missing_context[0]["field"]), (X, "recipe_nutrition.Macro_Fat"))

    def test_gallbladder_condition_requires_review(self):
        r = run("INH-011", "MACRO_FAT_LOW", self.facts(),
                EvaluationContext(member_id="m", conditions=("gallstones",)))
        self.assertEqual((r.applicability_status, r.missing_context[0]["field"]),
                         (X, "clinical_review.fat_handling_condition"))


# ======================================================================================
# Through detection
# ======================================================================================
class TestPipeline(unittest.TestCase):
    def setUp(self):
        n = {k: v for k, v in nutr(carb=60, fat=4).items()}
        self.conn = build_db(recipes={
            "r1": {"name": "Rice Bowl", "ingredients": [("white rice", ()), ("chicken", ())],
                   "steps": ["Boil the rice."], "nutrition": n},
            "r2": {"name": "Egg", "ingredients": [("egg", ())], "steps": ["Fry the egg."],
                   "nutrition": nutr(carb=0.0, fat=7)},
            "r3": {"name": "Unknown", "ingredients": [("lettuce", ())], "steps": ["Wash."], "nutrition": None},
        })

    def tearDown(self):
        self.conn.close()

    def ids(self, rid, **kw):
        return {c.rule_id: c for c in detect_rules.detect_rules(self.conn, rid, **kw)}

    def test_carbohydrate_calls_exactly_the_four_macro_carb_rules_with_no_tags(self):
        got = self.ids("r1")
        macro_carb = {k: v for k, v in got.items() if v.trigger_code == "MACRO_CARB"}
        self.assertEqual(set(macro_carb), {"GLY-002", "GLY-003", "GLY-004", "GLY-009"})
        for cand in macro_carb.values():
            self.assertEqual(cand.trigger_source, "recipe_nutrition")
            self.assertEqual(cand.matched_facts[0].code, "MACRO_CARB")
            self.assertIn("Macro_Carbohydrate", cand.reason)
        # Other derived triggers fire on the same recipe for their own reasons (rice is a starch).
        self.assertEqual(set(got) - set(macro_carb), {"GLY-011", "GLY-005"})
        self.assertEqual(self.conn.execute("SELECT count(*) FROM ingredient_rule_tags").fetchone()[0], 0)

    def test_no_carbohydrate_calls_nothing(self):
        self.assertEqual(self.ids("r2"), {})

    def test_unknown_nutrition_calls_the_rules_so_they_can_say_what_is_missing(self):
        got = self.ids("r3")
        self.assertEqual(set(got), {"GLY-002", "GLY-003", "GLY-004", "GLY-009", "GLY-011", "INH-011"})
        results = {e.rule_id: e for e in ev.evaluate_recipe_rules(self.conn, "r3")}
        for rid in got:
            self.assertEqual(results[rid].applicability_status, X, rid)
            self.assertTrue(results[rid].missing_context, rid)

    def test_ingredient_only_detection_is_unchanged(self):
        facts = ev.build_recipe_facts(self.conn, "r1")
        self.assertEqual(detect_rules.detect_rules_from_facts(self.conn, facts, include_derived=False), [])

    def test_result_exposes_trigger_source_value_unit_and_threshold(self):
        r = {e.rule_id: e for e in ev.evaluate_recipe_rules(self.conn, "r1")}["GLY-002"]
        d = r.as_dict()
        self.assertEqual((d["trigger_source"], d["applicability_status"]), ("recipe_nutrition", "APPLICABLE"))
        fact = d["matched_on"]["facts"][0]
        self.assertEqual((fact["code"], fact["source"], fact["value"], fact["unit"]),
                         ("MACRO_CARB", "recipe_nutrition", 60.0, "g"))
        self.assertEqual(d["evidence"]["carbohydrate"]["criterion"]["threshold"], 0.0)

    def test_conditions_lists_are_consistent_with_the_verdict(self):
        for e in ev.evaluate_recipe_rules(self.conn, "r1"):
            self.assertTrue(set(e.conditions_passed) | set(e.conditions_failed) <= set(e.conditions_checked), e.rule_id)


if __name__ == "__main__":
    unittest.main()
