#!/usr/bin/env python3
"""Phase 4 (no database): equipment facts and SYN-012.

    python3 -m unittest tests.test_derived_equipment -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests"))

import detect_rules  # noqa: E402
import equipment_facts as EQ  # noqa: E402
import evaluate_rules as ev  # noqa: E402
import recipe_facts as RF  # noqa: E402
from evaluate_rules import ApplicabilityStatus as S  # noqa: E402
from evaluation_context import EvaluationContext  # noqa: E402
from derived_fixtures import build_db, facts_for  # noqa: E402

A, N, X = S.APPLICABLE, S.NOT_APPLICABLE, S.NEEDS_CONTEXT


def codes(text):
    return sorted(d.code for d, _ in EQ.extract_from_text(text))


def run(facts, ctx=None):
    cand = detect_rules.DetectedRule(rule_id="SYN-012", rule_name="SYN-012", automation_status="instruction_only",
                                     trigger_code="PROC_COOKWARE", reason="candidate")
    return ev.evaluate_rule(cand, facts, ev.extract_process_facts(facts), ctx)


def row(code, source="structured", confidence="high", status="auto", step=None, text=None):
    return RF.EquipmentFact(code, source, confidence, status, step, text)


# ======================================================================================
# Extraction
# ======================================================================================
class TestExtraction(unittest.TestCase):
    def test_cast_iron_in_all_its_spellings_and_plurals(self):
        for text in ("Heat a cast iron skillet.", "Use a cast-iron pan.", "Cast  Iron pans work best.",
                     "Sear in cast iron skillets.", "a CAST IRON pot"):
            self.assertEqual(codes(text), ["EQUIP_CAST_IRON"], text)

    def test_vessel_aliases_and_plurals_are_recognised(self):
        for text in ("a frying pan", "a fry pan", "a saute pan", "a sauté pan", "a stock pot", "a stockpot",
                     "a sauce pan", "a saucepan", "a large skillet", "two skillets", "a wok", "a heavy pot",
                     "a slow cooker", "a Crock-Pot", "the pressure cooker"):
            self.assertEqual(codes(text), ["EQUIP_COOKWARE_UNSPECIFIED"], text)

    def test_substrings_are_not_cookware(self):
        for text in ("Peel the potatoes.", "Mash the potato.", "Make a pot roast.", "Line a baking pan.",
                     "Use two sheet pans.", "Grease a loaf pan.", "Pan-fry the fish.", "Add panko crumbs.",
                     "Serve in a hot pot.", "Sauteed onions.", "A workable plan.", "Add the pottery glaze."):
            self.assertEqual(codes(text), [], text)

    def test_a_material_counts_only_beside_a_cooking_vessel(self):
        self.assertEqual(codes("Heat a nonstick skillet."), ["EQUIP_NONIRON_COOKWARE"])
        self.assertEqual(codes("Use a non-stick pan."), ["EQUIP_NONIRON_COOKWARE"])
        self.assertEqual(codes("Simmer in a stainless steel saucepan."), ["EQUIP_NONIRON_COOKWARE"])
        self.assertEqual(codes("Toss in a stainless steel bowl."), [])
        self.assertEqual(codes("Add ceramic tiles."), [])

    def test_enameled_cast_iron_is_not_bare_cast_iron(self):
        self.assertEqual(codes("An enameled cast iron pot."), ["EQUIP_ENAMELED_CAST_IRON"])
        self.assertEqual(codes("Use enamelled cast-iron."), ["EQUIP_ENAMELED_CAST_IRON"])

    def test_dutch_oven_material_is_uncertain(self):
        [(defn, _)] = EQ.extract_from_text("Braise in a Dutch oven.")
        self.assertEqual((defn.code, defn.review_status, defn.confidence), ("EQUIP_DUTCH_OVEN", "pending_review", "low"))

    def test_a_named_material_replaces_the_generic_vessel(self):
        self.assertEqual(codes("A cast iron skillet."), ["EQUIP_CAST_IRON"])        # not also UNSPECIFIED

    def test_negated_mentions_are_not_mentions(self):
        for text in ("Do not use a cast iron skillet.", "Avoid cast iron for this dish.", "Never use cast-iron."):
            self.assertEqual(codes(text), [], text)

    def test_negation_does_not_leak_across_sentences(self):
        self.assertEqual(codes("Do not boil. Use a cast iron skillet."), ["EQUIP_CAST_IRON"])

    def test_nothing_is_read_from_a_text_that_names_no_equipment(self):
        self.assertEqual(codes("Stir well and serve."), [])


# ======================================================================================
# Facts, sources, review
# ======================================================================================
class TestEquipmentFacts(unittest.TestCase):
    def facts_of(self, facts, ctx=None):
        return EQ.equipment_candidate_facts(facts, ctx)

    def test_extraction_keeps_the_step_number_and_text(self):
        f = facts_for(steps=["Chop onions.", "Heat oil in a cast iron skillet.", "Simmer in a pot."])
        got = self.facts_of(f)
        by = {x.value["equipment_code"]: x for x in got}
        self.assertEqual(by["EQUIP_CAST_IRON"].value["instruction_step"], 2)
        self.assertEqual(by["EQUIP_CAST_IRON"].evidence, "Heat oil in a cast iron skillet.")
        self.assertEqual(by["EQUIP_COOKWARE_UNSPECIFIED"].value["instruction_step"], 3)
        for x in got:
            self.assertEqual((x.code, x.source, x.value["equipment_source"]), ("PROC_COOKWARE", "equipment", "instruction_extraction"))

    def test_equipment_is_never_taken_from_ingredients(self):
        f = facts_for(ingredients=["cast iron skillet", "nonstick pan spray", "saucepan"], steps=["Mix and serve."])
        self.assertEqual(self.facts_of(f), [])

    def test_no_mention_means_no_fact_not_a_negative_fact(self):
        self.assertEqual(self.facts_of(facts_for(steps=["Mix."])), [])
        self.assertEqual(self.facts_of(facts_for(steps=None)), [])

    def test_the_same_equipment_in_one_step_is_reported_once(self):
        f = facts_for(steps=["Heat a skillet, then return the skillet to the heat."])
        self.assertEqual(len(self.facts_of(f)), 1)

    def test_stored_rows_are_reported_as_stored(self):
        f = facts_for(steps=["Mix."], equipment=[row("EQUIP_CAST_IRON", "structured", step=3, text="Cast iron")])
        [x] = self.facts_of(f)
        self.assertEqual((x.value["equipment_source"], x.value["instruction_step"], x.confidence),
                         ("structured", 3, "high"))

    def test_a_rejected_row_suppresses_extraction_of_that_code(self):
        f = facts_for(steps=["Heat a cast iron skillet."], equipment=[
            row("EQUIP_CAST_IRON", "admin_review", status="rejected")])
        self.assertEqual(self.facts_of(f), [])

    def test_a_rejection_does_not_hide_other_equipment(self):
        f = facts_for(steps=["Use a cast iron skillet and a Dutch oven."], equipment=[
            row("EQUIP_CAST_IRON", "admin_review", status="rejected")])
        self.assertEqual([x.value["equipment_code"] for x in self.facts_of(f)], ["EQUIP_DUTCH_OVEN"])

    def test_a_confirmed_row_is_high_confidence(self):
        f = facts_for(steps=["Mix."], equipment=[row("EQUIP_DUTCH_OVEN", "admin_review", "low", "confirmed")])
        [x] = self.facts_of(f)
        self.assertEqual((x.confidence, x.value["review_status"]), ("high", "confirmed"))

    def test_an_unreviewed_row_keeps_its_pending_status(self):
        f = facts_for(equipment=[row("EQUIP_DUTCH_OVEN", "instruction_extraction", "low", "pending_review")])
        self.assertEqual(self.facts_of(f)[0].value["review_status"], "pending_review")

    def test_a_row_with_an_unknown_code_is_ignored(self):
        self.assertEqual(self.facts_of(facts_for(equipment=[row("EQUIP_MADE_UP")])), [])

    def test_request_context_equipment(self):
        ctx = EvaluationContext(equipment=("cast iron skillet",))
        [x] = self.facts_of(facts_for(steps=["Mix."]), ctx)
        self.assertEqual((x.value["equipment_code"], x.value["equipment_source"]), ("EQUIP_CAST_IRON", "request_context"))

    def test_request_context_equipment_does_not_make_the_evaluation_personal(self):
        self.assertFalse(EvaluationContext(equipment=("wok",)).is_personal())


# ======================================================================================
# SYN-012
# ======================================================================================
class TestSyn012(unittest.TestCase):
    def fields(self, r):
        return [m["field"] for m in r.missing_context]

    def test_registered(self):
        self.assertIn("SYN-012", ev.RULE_EVALUATORS)

    def test_cast_iron_already_used_satisfies_the_rule(self):
        r = run(facts_for(steps=["Simmer the tomato sauce in a cast iron skillet."]))
        self.assertEqual(r.applicability_status, N)
        self.assertIn("step 1", r.reason)
        self.assertEqual(r.conditions_failed, ("bare cast iron is not already used",))

    def test_iron_overload_is_an_explicit_exclusion_even_when_cast_iron_is_used(self):
        for steps in (["Use a cast iron skillet."], ["Use a nonstick pan."]):
            r = run(facts_for(steps=steps), EvaluationContext(member_id="m", conditions=("hemochromatosis",)))
            self.assertEqual(r.applicability_status, N)
            self.assertEqual(r.conditions_failed, ("no iron-overload limit applies",))
            self.assertNotIn("hemochromatosis", str(r.as_dict()))

    def test_no_cookware_stated_needs_context_and_is_not_assumed_absent(self):
        r = run(facts_for(steps=["Mix and serve."]))
        self.assertEqual((r.applicability_status, self.fields(r)), (X, ["recipe_equipment"]))
        self.assertIn("does not show", r.reason)

    def test_other_cookware_needs_the_dish_classified_and_the_members_conditions(self):
        r = run(facts_for(steps=["Simmer tomatoes in a nonstick pan."]))
        self.assertEqual(r.applicability_status, X)
        self.assertEqual(self.fields(r), ["recipe.dish_acidity_and_moisture", "user_context.conditions"])

    def test_with_conditions_known_only_the_dish_classification_is_missing(self):
        r = run(facts_for(steps=["Simmer tomatoes in a pot."]), EvaluationContext(member_id="m", conditions=()))
        self.assertEqual(self.fields(r), ["recipe.dish_acidity_and_moisture"])

    def test_an_unsettled_material_is_reported_with_its_step(self):
        r = run(facts_for(steps=["Chop.", "Braise in a Dutch oven."]), EvaluationContext(conditions=()))
        self.assertEqual(self.fields(r)[0], "recipe_equipment.material")
        self.assertIn("step 2", r.missing_context[0]["reason"])
        self.assertIn("awaiting review", r.missing_context[0]["reason"])

    def test_a_dutch_oven_is_not_treated_as_cast_iron(self):
        self.assertNotEqual(run(facts_for(steps=["Use a Dutch oven."])).applicability_status, N)

    def test_enameled_cast_iron_is_not_treated_as_bare_cast_iron(self):
        r = run(facts_for(steps=["Use an enameled cast iron pot."]), EvaluationContext(conditions=()))
        self.assertEqual(r.applicability_status, X)
        self.assertEqual(self.fields(r)[0], "recipe_equipment.material")

    def test_a_rejected_cast_iron_row_means_the_recipe_does_not_count_as_using_it(self):
        f = facts_for(steps=["Use a cast iron skillet."], equipment=[row("EQUIP_CAST_IRON", "admin_review", status="rejected")])
        self.assertEqual(run(f).applicability_status, X)

    def test_it_never_claims_applicable_without_a_definition_of_acidic_moist(self):
        for steps in (["Use a skillet."], ["Use a nonstick pan."], ["Use a pot."], ["Use a Dutch oven."]):
            for ctx in (None, EvaluationContext(conditions=()), EvaluationContext(member_id="m", conditions=("hay fever",))):
                self.assertNotEqual(run(facts_for(steps=steps), ctx).applicability_status, A, (steps, ctx))

    def test_request_context_cast_iron_counts(self):
        r = run(facts_for(steps=["Mix."]), EvaluationContext(equipment=("cast iron skillet",)))
        self.assertEqual(r.applicability_status, N)

    def test_evidence_lists_the_equipment_with_sources(self):
        r = run(facts_for(steps=["Use a cast iron skillet."]))
        self.assertEqual(r.evidence["equipment"][0]["value"]["equipment_source"], "instruction_extraction")


class TestSyn012Pipeline(unittest.TestCase):
    def setUp(self):
        self.conn = build_db(recipes={
            "r1": {"name": "Skillet", "ingredients": [("tomatoes", ())], "steps": ["Simmer in a cast iron skillet."],
                   "nutrition": None},
            "r2": {"name": "No Gear", "ingredients": [("tomatoes", ())], "steps": ["Mix."], "nutrition": None},
        })

    def tearDown(self):
        self.conn.close()

    def test_equipment_calls_the_rule_with_no_tag(self):
        got = {c.rule_id: c for c in detect_rules.detect_rules(self.conn, "r1")}
        self.assertEqual(got["SYN-012"].trigger_source, "equipment")
        self.assertEqual(got["SYN-012"].matched_facts[0].code, "PROC_COOKWARE")
        self.assertEqual(self.conn.execute("SELECT count(*) FROM ingredient_rule_tags").fetchone()[0], 0)

    def test_no_equipment_no_candidate(self):
        self.assertNotIn("SYN-012", {c.rule_id for c in detect_rules.detect_rules(self.conn, "r2")})

    def test_result_has_step_evidence(self):
        r = {e.rule_id: e for e in ev.evaluate_recipe_rules(self.conn, "r1")}["SYN-012"]
        d = r.as_dict()
        self.assertEqual(d["trigger_source"], "equipment")
        self.assertEqual([s["step_number"] for s in d["matched_on"]["steps"]], [1])
        self.assertEqual(d["applicability_status"], "NOT_APPLICABLE")


if __name__ == "__main__":
    unittest.main()
