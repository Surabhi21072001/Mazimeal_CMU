#!/usr/bin/env python3
"""Phase 3 (no database): meal and user context. GLY-005, GLY-010, GLY-011 and the loader.

    python3 -m unittest tests.test_derived_context -v
"""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests"))

import detect_rules  # noqa: E402
import evaluate_rules as ev  # noqa: E402
import meal_facts as MF  # noqa: E402
import member_context as MC  # noqa: E402
import nutrition_facts as NF  # noqa: E402
from evaluate_rules import ApplicabilityStatus as S  # noqa: E402
from evaluation_context import EvaluationContext, MealContext, matched_cautions  # noqa: E402
from derived_fixtures import build_db, facts_for  # noqa: E402

A, N, X = S.APPLICABLE, S.NOT_APPLICABLE, S.NEEDS_CONTEXT


def nutr(carb=60.0, fiber=3.0):
    return {"Macro_Carbohydrate": (carb, "g"), "Macro_Protein": (10.0, "g"), "Macro_Fat": (5.0, "g"),
            "Fiber": (fiber, "g"), "Energy": (300.0, "kcal")}


def run(rule_id, trigger, facts, ctx=None):
    cand = detect_rules.DetectedRule(rule_id=rule_id, rule_name=rule_id, automation_status="instruction_only",
                                     trigger_code=trigger, reason="candidate")
    return ev.evaluate_rule(cand, facts, ev.extract_process_facts(facts), ctx)


def ctx(seq=(), **kw):
    meal_kw = {k: kw.pop(k) for k in ("intended_portions", "post_meal_activity", "accompanying_foods", "meal_position")
               if k in kw}
    return EvaluationContext(meal_context=MealContext(eating_sequence=tuple(seq), **meal_kw), **kw)


# ======================================================================================
# The context objects
# ======================================================================================
class TestContextObjects(unittest.TestCase):
    def test_omitted_is_not_empty(self):
        omitted = EvaluationContext(member_id="m")
        empty = EvaluationContext(member_id="m", conditions=())
        self.assertIsNone(omitted.conditions)
        self.assertEqual(empty.conditions, ())
        self.assertNotEqual(omitted, empty)

    def test_tokens_are_normalised(self):
        self.assertEqual(EvaluationContext(conditions=("Iron Overload", " IRON-OVERLOAD ")).conditions,
                         ("iron_overload", "iron_overload"))

    def test_a_string_is_one_condition_not_a_list_of_characters(self):
        self.assertEqual(EvaluationContext(conditions="GERD").conditions, ("gerd",))

    def test_meal_only_context_is_not_personal(self):
        self.assertFalse(EvaluationContext(meal_context=MealContext()).is_personal())
        self.assertTrue(EvaluationContext(member_id="m").is_personal())
        self.assertTrue(EvaluationContext(conditions=()).is_personal())

    def test_repr_and_summary_keep_health_data_out(self):
        c = EvaluationContext(member_id="m", conditions=("hemochromatosis",), medications=("warfarin",))
        for text in (repr(c), str(c), str(c.as_dict())):
            self.assertNotIn("hemochromatosis", text)
            self.assertNotIn("warfarin", text)
        self.assertTrue(c.as_dict()["conditions_provided"])
        self.assertIn("hemochromatosis", str(c.as_dict(include_health=True)))

    def test_portions_must_be_positive(self):
        with self.assertRaises(ValueError):
            MealContext(intended_portions=0)

    def test_aliases_match_exactly_or_by_underscore_continuation_never_by_substring(self):
        self.assertTrue(matched_cautions(("pregnancy_wk_12",), ("high_energy_need_or_vulnerable_stage",)))
        self.assertTrue(matched_cautions(("ibs",), ("gi_condition",)))
        self.assertFalse(matched_cautions(("gibson",), ("gi_condition",)))
        self.assertFalse(matched_cautions(("ibsen",), ("gi_condition",)))
        self.assertFalse(matched_cautions(None, ("gi_condition",)))


# ======================================================================================
# Meal facts
# ======================================================================================
class TestMealFacts(unittest.TestCase):
    def codes(self, facts, c=None):
        return {f.code: f for f in MF.meal_candidate_facts(facts, c)}

    def test_starch_in_the_recipe_calls_meal_mixed_without_any_context(self):
        got = self.codes(facts_for(ingredients=["white rice", "peas"]))
        self.assertEqual(got["MEAL_MIXED"].source, "meal_context")
        self.assertNotIn("BEH_POSTMEAL", got)

    def test_starch_eaten_with_the_recipe_also_calls_it(self):
        got = self.codes(facts_for(ingredients=["peas"]), ctx(accompanying_foods=("a slice of potato bread",)))
        self.assertIn("MEAL_MIXED", got)

    def test_no_starch_no_call(self):
        self.assertNotIn("MEAL_MIXED", self.codes(facts_for(ingredients=["spinach", "egg"])))

    def test_post_meal_is_called_only_when_a_meal_context_is_supplied(self):
        f = facts_for(ingredients=["spinach"])
        self.assertNotIn("BEH_POSTMEAL", self.codes(f))
        self.assertNotIn("BEH_POSTMEAL", self.codes(f, EvaluationContext(member_id="m")))
        self.assertIn("BEH_POSTMEAL", self.codes(f, EvaluationContext(meal_context=MealContext())))

    def test_sequence_classification_reports_unknown_words(self):
        seq = MF.classify_sequence(("salad", "chicken", "rice", "dessert"))
        self.assertEqual((seq["vegetables"], seq["protein"], seq["starch"], seq["ignored"]), ([0], [1], [2], ["dessert"]))


# ======================================================================================
# GLY-005
# ======================================================================================
class TestGly005(unittest.TestCase):
    F = facts_for(ingredients=["white rice", "chicken", "broccoli"], nutrition=nutr())

    def go(self, c):
        return run("GLY-005", "MEAL_MIXED", self.F, c)

    def test_no_context_needs_the_eating_sequence(self):
        r = self.go(None)
        self.assertEqual(r.applicability_status, X)
        self.assertEqual(r.missing_context, ({"field": "meal_context.eating_sequence",
                                              "reason": r.missing_context[0]["reason"]},))
        self.assertIn("not inferred", r.missing_context[0]["reason"])

    def test_meal_context_without_a_sequence_still_needs_it(self):
        self.assertEqual(self.go(EvaluationContext(meal_context=MealContext(intended_portions=1))).applicability_status, X)

    def test_vegetables_and_protein_first_is_already_satisfied(self):
        r = self.go(ctx(("vegetables", "protein", "starch")))
        self.assertEqual(r.applicability_status, N)
        self.assertEqual(r.conditions_failed, ())

    def test_starch_first_violates_the_recommendation(self):
        r = self.go(ctx(("starch", "vegetables", "protein")))
        self.assertEqual(r.applicability_status, A)
        self.assertEqual(r.evidence["after_starch"], ["vegetables", "protein"])

    def test_vegetables_first_but_protein_after_still_applies(self):
        r = self.go(ctx(("vegetables", "starch", "protein")))
        self.assertEqual((r.applicability_status, r.evidence["after_starch"]), (A, ["protein"]))

    def test_the_sequence_must_mention_the_starch(self):
        r = self.go(ctx(("vegetables", "protein")))
        self.assertEqual(r.applicability_status, X)

    def test_a_sequence_with_only_starch_is_not_a_mixed_meal(self):
        self.assertEqual(self.go(ctx(("rice",))).applicability_status, N)

    def test_synonyms_and_unrecognised_terms(self):
        r = self.go(ctx(("Salad", "Chicken", "Rice", "wine")))
        self.assertEqual(r.applicability_status, N)
        self.assertEqual(r.evidence["unrecognised_sequence_terms"], ["wine"])

    def test_recipe_composition_is_never_used_as_the_order(self):
        # A recipe listing rice first says nothing about the order it is eaten in.
        self.assertEqual(self.go(None).applicability_status, X)


# ======================================================================================
# GLY-010
# ======================================================================================
class TestGly010(unittest.TestCase):
    F = facts_for(ingredients=["spinach"], nutrition=nutr())

    def go(self, c):
        return run("GLY-010", "BEH_POSTMEAL", self.F, c)

    def test_conditions_not_provided_needs_context(self):
        r = self.go(ctx())
        self.assertEqual(r.applicability_status, X)
        self.assertEqual(r.missing_context[0]["field"], "user_context.conditions")

    def test_explicitly_no_conditions_and_no_walk_is_applicable(self):
        r = self.go(ctx(conditions=()))
        self.assertEqual(r.applicability_status, A)

    def test_declared_mobility_or_cardiac_limit_requires_review(self):
        for cond in ("fall risk", "heart disease", "injury", "exercise restriction"):
            r = self.go(ctx(conditions=(cond,)))
            self.assertEqual(r.applicability_status, X, cond)
            self.assertEqual(r.missing_context[0]["field"], "clinical_review.mobility_or_medical_limit", cond)

    def test_unrelated_conditions_do_not_block(self):
        self.assertEqual(self.go(ctx(conditions=("hay fever",))).applicability_status, A)

    def test_a_planned_walk_already_satisfies_it_without_needing_conditions(self):
        for activity in ("walk", "a short walk", "walking", "Walk_around_the_block"):
            self.assertEqual(self.go(ctx(post_meal_activity=activity)).applicability_status, N, activity)

    def test_negated_walk_is_not_a_plan_to_walk(self):
        r = self.go(ctx(post_meal_activity="no walk, going to bed", conditions=()))
        self.assertEqual(r.applicability_status, A)

    def test_no_meal_context_at_all(self):
        r = self.go(EvaluationContext(member_id="m", conditions=()))
        self.assertEqual((r.applicability_status, r.missing_context[0]["field"]), (X, "meal_context"))


# ======================================================================================
# GLY-011
# ======================================================================================
class TestGly011(unittest.TestCase):
    CRIT = NF.NutritionCriterion("high_carbohydrate_serving", "available_carbohydrate", ">=", 60.0, "g",
                                 "per_serving", "reviewed", "test", "test")
    F = facts_for(ingredients=["white rice"], nutrition=nutr(carb=33.0, fiber=3.0))        # 30 g available

    def go(self, c, facts=None):
        return run("GLY-011", "MACRO_AVAIL_CARB", facts or self.F, c)

    def fields(self, r):
        return [m["field"] for m in r.missing_context]

    def test_without_a_reviewed_definition_everything_missing_is_listed_together(self):
        r = self.go(None)
        self.assertEqual(r.applicability_status, X)
        self.assertEqual(self.fields(r), ["reviewed_definition.high_carbohydrate_serving",
                                          "meal_context.intended_portions", "user_context.goals",
                                          "user_context.conditions"])
        self.assertIn("available_carbohydrate", r.evidence["classification"]["criterion"]["field"])
        self.assertEqual(r.evidence["available_carbohydrate"]["reading"]["value"], 30.0)

    def test_even_with_full_context_an_unreviewed_definition_blocks(self):
        r = self.go(ctx(intended_portions=1, goals=("weight_loss",), conditions=()))
        self.assertEqual(self.fields(r), ["reviewed_definition.high_carbohydrate_serving"])

    def test_portions_goals_and_conditions_are_each_required(self):
        with mock.patch.dict(NF.APPLICABILITY_CRITERIA, {"GLY-011": self.CRIT}):
            r = self.go(ctx(intended_portions=2))
            self.assertEqual(self.fields(r), ["user_context.goals", "user_context.conditions"])
            r = self.go(EvaluationContext(goals=("weight_loss",), conditions=()))
            self.assertEqual(self.fields(r), ["meal_context.intended_portions"])

    def test_intended_portions_are_applied_at_the_boundary(self):
        full = dict(goals=("weight_loss",), conditions=())
        with mock.patch.dict(NF.APPLICABILITY_CRITERIA, {"GLY-011": self.CRIT}):
            below = self.go(ctx(intended_portions=1.9, **full))            # 57 g
            at = self.go(ctx(intended_portions=2.0, **full))               # 60 g
            above = self.go(ctx(intended_portions=2.1, **full))            # 63 g
        self.assertEqual(below.applicability_status, N)
        self.assertEqual((at.applicability_status, above.applicability_status), (A, A))
        self.assertEqual(at.evidence["classification"]["scale"], 2.0)
        self.assertEqual(at.evidence["classification"]["effective_value"], 60.0)

    def test_not_high_needs_neither_goals_nor_conditions(self):
        with mock.patch.dict(NF.APPLICABILITY_CRITERIA, {"GLY-011": self.CRIT}):
            r = self.go(ctx(intended_portions=1))
        self.assertEqual(r.applicability_status, N)

    def test_underfeeding_limits_require_review(self):
        base = dict(intended_portions=3, goals=("weight_loss",))
        with mock.patch.dict(NF.APPLICABILITY_CRITERIA, {"GLY-011": self.CRIT}):
            for kw in (dict(conditions=("pregnancy",)), dict(conditions=(), life_stage="pregnancy_wk_12"),
                       dict(conditions=(), activity_level="athlete"), dict(conditions=("lactating",))):
                r = self.go(ctx(**base, **kw))
                self.assertEqual(r.applicability_status, X, kw)
                self.assertEqual(r.missing_context[0]["field"],
                                 "clinical_review.high_energy_need_or_vulnerable_stage", kw)

    def test_no_available_carbohydrate_is_not_applicable(self):
        f = facts_for(ingredients=["kale"], nutrition=nutr(carb=5.0, fiber=8.0))
        self.assertEqual(self.go(None, f).applicability_status, N)

    def test_missing_fibre_needs_context_naming_it(self):
        f = facts_for(ingredients=["rice"], nutrition={"Macro_Carbohydrate": (50, "g")})
        r = self.go(None, f)
        self.assertEqual((r.applicability_status, self.fields(r)), (X, ["recipe_nutrition.Fiber"]))


# ======================================================================================
# Anonymous behaviour is preserved
# ======================================================================================
class TestAnonymous(unittest.TestCase):
    def setUp(self):
        self.conn = build_db(recipes={"r1": {"name": "Rice", "ingredients": [("white rice", ()), ("spinach", ())],
                                             "steps": ["Boil rice."], "nutrition": nutr()}})

    def tearDown(self):
        self.conn.close()

    def test_no_context_calls_no_meal_behaviour_rule(self):
        ids = {c.rule_id for c in detect_rules.detect_rules(self.conn, "r1")}
        self.assertNotIn("GLY-010", ids)
        self.assertIn("GLY-005", ids)                               # a starch meal: asks for the order
        self.assertIn("GLY-011", ids)

    def test_a_meal_context_adds_the_post_meal_rule(self):
        ids = {c.rule_id for c in detect_rules.detect_rules(self.conn, "r1", EvaluationContext(meal_context=MealContext()))}
        self.assertIn("GLY-010", ids)

    def test_evaluating_without_context_never_needs_a_member(self):
        results = {e.rule_id: e for e in ev.evaluate_recipe_rules(self.conn, "r1")}
        self.assertEqual(results["GLY-005"].applicability_status, X)
        self.assertEqual(results["GLY-002"].applicability_status, A)
        self.assertEqual(results["GLY-002"].evidence["personalization"], "not evaluated: no member context supplied")


# ======================================================================================
# Loading a member's context
# ======================================================================================
def member_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE households (household_id TEXT, created_by_user_id TEXT, deleted_at TEXT);
        CREATE TABLE household_members (member_id TEXT, household_id TEXT, activity_level TEXT,
                                        life_stage TEXT, goal TEXT, deleted_at TEXT);
        CREATE TABLE member_conditions (record_id TEXT, member_id TEXT, condition_type TEXT,
                                        condition_code TEXT, value_text TEXT, created_at TEXT);
        INSERT INTO households VALUES ('h1', 'owner-1', NULL), ('h2', 'owner-2', NULL), ('h3', 'owner-1', '2020-01-01');
        INSERT INTO household_members VALUES
            ('m-a', 'h1', 'moderate', NULL, 'maintenance', NULL),
            ('m-none', 'h1', NULL, NULL, NULL, NULL),
            ('m-b', 'h2', 'athlete', 'lactating', 'weight_loss', NULL),
            ('m-deleted', 'h1', NULL, NULL, NULL, '2021-01-01'),
            ('m-in-deleted-household', 'h3', NULL, NULL, NULL, NULL);
        INSERT INTO member_conditions VALUES
            ('1', 'm-a', 'condition', NULL, 'Hemochromatosis', '2020-01-01'),
            ('2', 'm-a', 'condition', 'E11', NULL, '2020-01-02'),
            ('3', 'm-a', 'medication', NULL, 'Warfarin', '2020-01-03'),
            ('4', 'm-a', 'allergy', NULL, 'peanut', '2020-01-04'),
            ('5', 'm-b', 'supplement', NULL, 'iron', '2020-01-05');
    """)
    return conn


class TestMemberLoader(unittest.TestCase):
    def setUp(self):
        self.conn = member_db()

    def tearDown(self):
        self.conn.close()

    def test_the_owner_gets_the_members_context(self):
        c = MC.load_member_context(self.conn, "m-a", "owner-1")
        self.assertEqual(c.member_id, "m-a")
        self.assertEqual(set(c.conditions), {"hemochromatosis", "e11"})
        self.assertEqual(c.medications, ("warfarin",))
        self.assertEqual((c.goals, c.activity_level), (("maintenance",), "moderate"))

    def test_allergies_are_not_loaded_as_conditions(self):
        self.assertNotIn("peanut", MC.load_member_context(self.conn, "m-a", "owner-1").conditions)

    def test_a_different_account_is_denied(self):
        with self.assertRaises(MC.MemberAccessDenied):
            MC.load_member_context(self.conn, "m-a", "owner-2")

    def test_nonexistent_and_unauthorised_are_indistinguishable(self):
        errs = []
        for member, caller in (("m-a", "owner-2"), ("nobody", "owner-1")):
            with self.assertRaises(MC.MemberAccessDenied) as cm:
                MC.load_member_context(self.conn, member, caller)
            errs.append(str(cm.exception))
        self.assertEqual(errs[0], errs[1])

    def test_missing_ids_are_denied_rather_than_returning_someone_else(self):
        for member, caller in ((None, "owner-1"), ("m-a", None), ("", "owner-1"), ("m-a", "")):
            with self.assertRaises(MC.MemberAccessDenied):
                MC.load_member_context(self.conn, member, caller)

    def test_deleted_members_and_deleted_households_are_denied(self):
        for member in ("m-deleted", "m-in-deleted-household"):
            with self.assertRaises(MC.MemberAccessDenied):
                MC.load_member_context(self.conn, member, "owner-1")

    def test_no_condition_rows_means_unknown_not_none(self):
        c = MC.load_member_context(self.conn, "m-none", "owner-1")
        self.assertIsNone(c.conditions)
        self.assertIsNone(c.medications)
        self.assertIsNone(c.goals)

    def test_a_supplement_only_member_has_unknown_conditions(self):
        c = MC.load_member_context(self.conn, "m-b", "owner-2")
        self.assertEqual((c.conditions, c.supplements, c.life_stage), (None, ("iron",), "lactating"))

    def test_error_messages_carry_no_member_data(self):
        with self.assertRaises(MC.MemberAccessDenied) as cm:
            MC.load_member_context(self.conn, "m-a", "owner-2")
        self.assertNotIn("m-a", str(cm.exception))

    def test_loaded_context_changes_a_verdict(self):
        f = facts_for(ingredients=["rice"], nutrition=nutr())
        owner = MC.load_member_context(self.conn, "m-a", "owner-1")        # conditions include hemochromatosis
        r = run("GLY-002", "MACRO_CARB", f, owner)                          # not a GI condition
        self.assertEqual(r.applicability_status, A)
        unknown = MC.load_member_context(self.conn, "m-none", "owner-1")
        self.assertEqual(run("GLY-002", "MACRO_CARB", f, unknown).applicability_status, X)


if __name__ == "__main__":
    unittest.main()
