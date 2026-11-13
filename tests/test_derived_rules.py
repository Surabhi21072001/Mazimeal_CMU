#!/usr/bin/env python3
"""Unit tests (no database) for fact-driven triggering: DerivedFact, GLY-015, and later phases.

    python3 -m unittest tests.test_derived_rules -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests"))

import derived_facts as DF  # noqa: E402
import detect_rules  # noqa: E402
import evaluate_rules as ev  # noqa: E402
from evaluate_rules import ApplicabilityStatus as S  # noqa: E402
from derived_fixtures import build_db, facts_for  # noqa: E402
import recipe_facts  # noqa: E402

A, N, X = S.APPLICABLE, S.NOT_APPLICABLE, S.NEEDS_CONTEXT


def cand(rule_id, trigger, auto="instruction_only"):
    return detect_rules.DetectedRule(rule_id=rule_id, rule_name="Rule " + rule_id,
                                     automation_status=auto, trigger_code=trigger, reason="candidate")


def run(rule_id, trigger, facts, context=None):
    """Evaluate one rule the way the pipeline does, without a database."""
    pf = ev.extract_process_facts(facts)
    return ev.evaluate_rule(cand(rule_id, trigger), facts, pf, context)


# ======================================================================================
# DerivedFact and text matching
# ======================================================================================
class TestDerivedFact(unittest.TestCase):
    def test_every_documented_source_is_accepted(self):
        for source in ("ingredient", "recipe_nutrition", "recipe_process", "meal_context",
                       "user_context", "equipment", "engine_result"):
            self.assertEqual(DF.DerivedFact("X", source).source, source)

    def test_an_unknown_source_is_rejected(self):
        with self.assertRaises(ValueError):
            DF.DerivedFact("X", "guess")

    def test_fact_is_immutable(self):
        fact = DF.DerivedFact("X", "equipment")
        with self.assertRaises(Exception):
            fact.code = "Y"

    def test_as_dict_carries_every_field_and_hoists_the_step(self):
        d = DF.DerivedFact("PROC_COOL_REHEAT", "recipe_process", {"instruction_step": 4}, None,
                           "Cool the rice", "high").as_dict()
        self.assertEqual((d["code"], d["source"], d["instruction_step"], d["evidence"], d["confidence"]),
                         ("PROC_COOL_REHEAT", "recipe_process", 4, "Cool the rice", "high"))


class TestTextMatching(unittest.TestCase):
    def test_whole_word_phrases_do_not_match_inside_words(self):
        pat = DF.compile_phrases(["oil"])
        self.assertFalse(pat.search("boil the water"))
        self.assertFalse(pat.search("broil for 5 minutes"))
        self.assertTrue(pat.search("add oil"))

    def test_hyphen_space_and_plural_are_equivalent(self):
        pat = DF.compile_phrases(["cast iron"])
        for text in ("cast iron", "cast-iron", "Cast  Iron"):
            self.assertTrue(pat.search(text), text)

    def test_negation_is_scoped_to_the_sentence(self):
        text = "Do not stir. Chill it."
        m = DF._COOL.search(text)
        self.assertFalse(DF.is_negated(text, m.start()))
        text = "Do not refrigerate the rice."
        self.assertTrue(DF.is_negated(text, DF._COOL.search(text).start()))

    def test_steps_keep_their_numbers_and_continuation_lines(self):
        steps = DF.parse_steps("1. Boil rice.\ncontinued here\n2. Chill it.")
        self.assertEqual([(s.number, s.text) for s in steps],
                         [(1, "Boil rice. continued here"), (2, "Chill it.")])

    def test_no_instructions_gives_no_steps(self):
        self.assertEqual(DF.parse_steps(None), [])
        self.assertEqual(DF.parse_steps("  \n "), [])


# ======================================================================================
# PHASE 1 - GLY-015
# ======================================================================================
RICE = dict(ingredients=["long grain rice", "peas"])


class TestGly015Facts(unittest.TestCase):
    def test_no_cooling_or_reheating_means_no_trigger_fact(self):
        f = facts_for(steps=["Boil the rice.", "Serve hot."], **RICE)
        self.assertEqual(DF.process_cool_reheat_facts(f), [])

    def test_cooling_fact_keeps_step_number_and_text(self):
        f = facts_for(steps=["Boil the rice.", "Spread the rice on a tray to cool.", "Serve."], **RICE)
        facts = DF.process_cool_reheat_facts(f)
        self.assertEqual([(x.value["role"], x.value["instruction_step"], x.source) for x in facts],
                         [("cooling", 2, "recipe_process")])
        self.assertEqual(facts[0].evidence, "Spread the rice on a tray to cool.")
        self.assertEqual(facts[0].code, "PROC_COOL_REHEAT")

    def test_no_starch_ingredient_means_no_fact_even_if_a_step_cools(self):
        f = facts_for(ingredients=["chicken"], steps=["Chill the chicken."])
        self.assertEqual(DF.process_cool_reheat_facts(f), [])

    def test_a_step_that_does_not_name_the_starch_is_unattributed_not_a_trigger(self):
        f = facts_for(steps=["Boil the rice.", "Let cool completely."], **RICE)
        self.assertEqual(DF.process_cool_reheat_facts(f), [])
        scan = DF.cooling_scan(DF.parse_steps(f.instructions))
        self.assertEqual([h["instruction_step"] for h in scan["unattributed"]], [2])

    def test_rice_vinegar_is_not_a_starch(self):
        self.assertEqual(DF.starch_mentions("add rice vinegar and chill"), [])
        self.assertEqual(DF.starch_mentions("cooked rice and potatoes"), ["rice", "potatoes"])

    def test_pasta_tag_counts_as_starch_without_a_matching_name(self):
        f = facts_for(ingredients=["cellophane noodles"], steps=["Chill the noodles."])
        self.assertTrue(DF.recipe_starch_ingredients(f))     # 'noodle' word

    def test_unrelated_uses_of_cool_do_not_trigger(self):
        for step in ("Top the rice with cool whip.", "Rinse the rice in cool water.",
                     "Add cold water to the rice.", "Serve the rice with a cool breeze of mint."):
            f = facts_for(steps=[step], **RICE)
            self.assertEqual(DF.process_cool_reheat_facts(f), [], step)

    def test_negated_mentions_do_not_trigger_but_are_recorded(self):
        f = facts_for(steps=["Do not refrigerate the rice.", "Never reheat the rice."], **RICE)
        self.assertEqual(DF.process_cool_reheat_facts(f), [])
        scan = DF.cooling_scan(DF.parse_steps(f.instructions))
        self.assertEqual({h["kind"] for h in scan["negated"]}, {"cooling", "refrigeration", "reheating"})

    def test_the_old_booleans_are_now_precise(self):
        f = facts_for(steps=["Add cold water.", "Top with cool whip."], **RICE)
        pf = ev.extract_process_facts(f)
        self.assertFalse(pf["cooling_detected"].value)
        f = facts_for(steps=["Chill the dish.", "Reheat gently."], **RICE)
        pf = ev.extract_process_facts(f)
        self.assertTrue(pf["cooling_detected"].value)
        self.assertEqual(pf["cooling_detected"].evidence, "1. Chill the dish.")
        self.assertTrue(pf["reheating_detected"].value)


class TestGly015Evaluator(unittest.TestCase):
    def ev(self, steps, **kw):
        return run("GLY-015", "PROC_COOL_REHEAT", facts_for(steps=steps, **{**RICE, **kw}))

    def test_registered(self):
        self.assertIn("GLY-015", ev.RULE_EVALUATORS)

    def test_starch_with_no_cooling_or_reheating_is_not_applicable(self):
        r = self.ev(["Boil the rice for 15 minutes.", "Serve."])
        self.assertEqual(r.applicability_status, N)
        self.assertIn("No step cools or reheats", r.reason)

    def test_cooling_only_is_applicable(self):
        r = self.ev(["Boil the rice.", "Refrigerate the rice in a shallow tray."])
        self.assertEqual(r.applicability_status, A)
        self.assertIn("reheating", r.conditions_failed[0])

    def test_reheating_only_is_applicable(self):
        r = self.ev(["Reheat the cooked rice in a pan."])
        self.assertEqual(r.applicability_status, A)
        self.assertIn("cooling step names the starch", r.conditions_failed)

    def test_cooling_then_reheating_with_refrigeration_satisfies_the_rule(self):
        r = self.ev(["Refrigerate the rice within an hour.", "Reheat the rice until steaming."])
        self.assertEqual(r.applicability_status, N)
        self.assertIn("not checked", r.reason)                      # limits are declared unchecked
        self.assertIn("validated_limits", r.evidence)

    def test_cooling_and_reheating_without_refrigeration_is_applicable(self):
        r = self.ev(["Let the rice cool on the counter.", "Reheat the rice."])
        self.assertEqual(r.applicability_status, A)
        self.assertEqual(r.conditions_failed, ("refrigeration stated",))

    def test_reheating_before_cooling_needs_context_with_exact_missing_field(self):
        r = self.ev(["Reheat the rice.", "Then cool the rice and refrigerate."])
        self.assertEqual(r.applicability_status, X)
        self.assertEqual(r.missing_context[0]["field"], "recipe.instructions.order")
        self.assertIn("step 1", r.missing_context[0]["reason"])

    def test_same_step_order_is_taken_from_the_text(self):
        r = self.ev(["Cool the rice and reheat before serving."])
        self.assertNotEqual(r.applicability_status, X)               # cooling comes first
        r = self.ev(["Reheat the rice, then cool it."])
        self.assertEqual(r.applicability_status, X)

    def test_instructions_unavailable_needs_context(self):
        r = run("GLY-015", "PROC_COOL_REHEAT", facts_for(steps=None, **RICE))
        self.assertEqual(r.applicability_status, X)
        self.assertEqual(r.missing_context[0]["field"], "recipe.instructions")

    def test_a_step_that_names_no_food_needs_context(self):
        r = self.ev(["Boil the rice.", "Let cool completely."])
        self.assertEqual(r.applicability_status, X)
        self.assertEqual(r.missing_context[0]["field"], "recipe.instructions.food_cooled_or_reheated")

    def test_negated_language_is_not_a_cooling_step(self):
        r = self.ev(["Do not refrigerate the rice; serve at once."])
        self.assertEqual(r.applicability_status, N)
        self.assertIn("explicitly ruled out", r.reason)

    def test_unrelated_cool_is_not_cooling(self):
        r = self.ev(["Top the rice with cool whip."])
        self.assertEqual(r.applicability_status, N)

    def test_no_starch_ingredient_is_not_applicable(self):
        r = run("GLY-015", "PROC_COOL_REHEAT", facts_for(ingredients=["chicken"], steps=["Chill the chicken."]))
        self.assertEqual(r.applicability_status, N)

    def test_multiple_steps_keep_their_numbers_in_evidence(self):
        steps = ["Boil the rice.", "Cool the rice quickly.", "Refrigerate the rice.", "Serve.",
                 "Reheat the rice thoroughly."]
        r = self.ev(steps)
        self.assertEqual(r.applicability_status, N)
        self.assertEqual([h["instruction_step"] for h in r.evidence["cooling"]], [2, 3])
        self.assertEqual([h["instruction_step"] for h in r.evidence["reheating"]], [5])
        self.assertEqual([h["instruction_step"] for h in r.evidence["refrigeration"]], [3])


class TestGly015Pipeline(unittest.TestCase):
    """Through detection, enrichment and as_dict: the structured evidence a caller sees."""

    def setUp(self):
        self.conn = build_db(recipes={
            "r1": {"name": "Cooled Rice", "ingredients": [("rice", ()), ("peas", ())],
                   "steps": ["Boil the rice.", "Cool the rice, then refrigerate it.", "Reheat the rice before serving."]},
            "r2": {"name": "Plain Rice", "ingredients": [("rice", ())], "steps": ["Boil the rice."]},
            "r3": {"name": "No Steps", "ingredients": [("rice", ())], "steps": None},
        })

    def tearDown(self):
        self.conn.close()

    def test_trigger_comes_from_a_process_fact_not_a_tag(self):
        rules = {c.rule_id: c for c in detect_rules.detect_rules(self.conn, "r1")}
        self.assertIn("GLY-015", rules)
        self.assertEqual(rules["GLY-015"].trigger_source, "recipe_process")
        self.assertIn("PROC_COOL_REHEAT", rules["GLY-015"].reason)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM ingredient_rule_tags").fetchone()[0], 0)

    def test_candidates_only_where_the_process_is_in_the_steps(self):
        # These fixtures carry no nutrition, so other (nutrition) rules may be called; GLY-015 must not be.
        self.assertNotIn("GLY-015", {c.rule_id for c in detect_rules.detect_rules(self.conn, "r2")})
        self.assertNotIn("GLY-015", {c.rule_id for c in detect_rules.detect_rules(self.conn, "r3")})

    def test_ingredient_only_detection_is_unchanged(self):
        facts = recipe_facts.build_recipe_facts(self.conn, "r1")
        self.assertEqual(detect_rules.detect_rules_from_facts(self.conn, facts, include_derived=False), [])

    def test_result_has_structured_evidence(self):
        [r] = [e for e in ev.evaluate_recipe_rules(self.conn, "r1") if e.rule_id == "GLY-015"]
        d = r.as_dict()
        self.assertEqual(d["trigger_source"], "recipe_process")
        self.assertEqual(d["applicability_status"], "NOT_APPLICABLE")
        self.assertEqual({f["code"] for f in d["matched_on"]["facts"]}, {"PROC_COOL_REHEAT"})
        steps = {s["step_number"] for s in d["matched_on"]["steps"]}
        self.assertEqual(steps, {2, 3})
        self.assertEqual(d["missing_context"], [])
        for old in ("rule_id", "applicability_status", "conditions_checked", "conditions_passed",
                    "conditions_failed", "reason", "candidate", "trigger_code"):
            self.assertIn(old, d)                       # existing fields are still there
        self.assertEqual(set(d["matched_on"]), {"ingredients", "steps", "facts"})


# ======================================================================================
# Regression: BIO-003 must not read 'boil' as 'oil' or 'buttermilk' as 'butter'
# ======================================================================================
class TestBio003FatWordRegression(unittest.TestCase):
    def bio003(self, ingredients, steps):
        f = facts_for(ingredients=ingredients, steps=steps, codes={"ING_TOMATO"})
        return run("BIO-003", "ING_TOMATO", f, None)

    def test_boil_is_not_oil(self):
        r = self.bio003(["tomatoes"], ["Boil the tomatoes until soft."])
        self.assertEqual(r.applicability_status, A, r.reason)
        self.assertIn("no culinary fat", r.reason)

    def test_broil_is_not_oil(self):
        r = self.bio003(["tomatoes"], ["Broil the tomatoes and cook until charred."])
        self.assertEqual(r.applicability_status, A, r.reason)

    def test_buttermilk_is_not_butter(self):
        r = self.bio003(["tomatoes", "buttermilk"], ["Cook the tomatoes."])
        self.assertEqual(r.applicability_status, A, r.reason)

    def test_real_fats_are_still_found(self):
        for name in ("olive oil", "butter", "peanut butter", "oils", "ghee", "tahini"):
            r = self.bio003(["tomatoes", name], ["Cook the tomatoes."])
            self.assertEqual(r.applicability_status, N, name)
        r = self.bio003(["tomatoes"], ["Cook the tomatoes in a little oil."])
        self.assertEqual(r.applicability_status, N)

    def test_butter_beans_and_butternut_are_not_butter(self):
        for name in ("butter beans", "butternut squash"):
            r = self.bio003(["tomatoes", name], ["Cook the tomatoes."])
            self.assertEqual(r.applicability_status, A, name)


if __name__ == "__main__":
    unittest.main()
