#!/usr/bin/env python3
"""Unit tests (no database) for the inhibitor rules: ingredient-to-step association, INH-005/006/007,
the manual-advisory guard (INH-003/008/009/010) and INH-011's boundaries.

    python3 -m unittest tests.test_inhibitor_rules -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests"))

import derived_facts as DF  # noqa: E402
import detect_rules  # noqa: E402
import evaluate_rules as ev  # noqa: E402
import ingredient_steps as IS  # noqa: E402
import inhibitor_rules as IR  # noqa: E402
import nutrition_facts as NF  # noqa: E402
from evaluate_rules import ApplicabilityStatus as S  # noqa: E402
from evaluation_context import EvaluationContext  # noqa: E402
from derived_fixtures import build_db, facts_for  # noqa: E402

A, N, X = S.APPLICABLE, S.NOT_APPLICABLE, S.NEEDS_CONTEXT
VITC, CRUC = "NUT_VITC", "ING_CRUCIFER"


def run(rule_id, trigger, facts, ctx=None):
    cand = detect_rules.DetectedRule(rule_id=rule_id, rule_name=rule_id, automation_status="recipe_safe",
                                     trigger_code=trigger, reason="candidate", action="act", recipe_engine_instruction="instr")
    return ev.evaluate_rule(cand, facts, ev.extract_process_facts(facts), ctx)


def vitc(ingredients, steps, tags=None):
    tags = tags or {n: (VITC,) for n in ingredients}
    return run("INH-006", VITC, facts_for(ingredients=ingredients, steps=steps, tags=tags))


def cruc(ingredients, steps, tags=None):
    tags = tags or {n: (CRUC,) for n in ingredients if n in ("broccoli", "kale", "cauliflower", "cabbage")}
    return run("INH-007", CRUC, facts_for(ingredients=ingredients, steps=steps, tags=tags))


def fields(r):
    return [m["field"] for m in r.missing_context]


def per(r):
    return {p["ingredient"]: p for p in r.evidence["ingredients"]}


REVIEWED_PROLONGED = IR.ProlongedHeatDefinition(minutes_at_or_above=30.0, methods=("slow_cook",),
                                                review_status="reviewed", source="test")
REVIEWED_HIGH_HEAT = IR.HighHeatDefinition(methods=("roast", "fry"), review_status="reviewed", source="test")


# ======================================================================================
# Ingredient names and step association
# ======================================================================================
class TestIngredientNames(unittest.TestCase):
    def test_descriptors_are_removed_and_the_name_is_kept(self):
        self.assertEqual(IS.aliases("frozen chopped spinach"), ["frozen chopped spinach", "spinach"])
        self.assertEqual(IS.aliases("lemon wedge"), ["lemon wedge", "lemon"])
        self.assertEqual(IS.aliases("broccoli florets"), ["broccoli florets", "broccoli floret", "broccoli"])

    def test_a_name_is_never_reduced_to_a_generic_word(self):
        for name in ("green pepper", "green bell pepper", "Brussels sprouts", "anaheim chilies", "tomato sauce"):
            for a in IS.aliases(name):
                self.assertNotIn(a, IS.GENERIC, (name, a))
        self.assertNotIn("pepper", IS.aliases("green bell pepper"))
        self.assertIn("bell pepper", IS.aliases("green bell pepper"))
        self.assertNotIn("sprouts", IS.aliases("Brussels sprouts"))

    def test_plural_and_singular_are_both_aliases(self):
        self.assertEqual(IS.aliases("tomatoes"), ["tomatoes", "tomato"])

    def test_canonical_keys_unify_aliases_and_keep_derived_forms_apart(self):
        self.assertEqual({IS.canonical_key(n) for n in ("tomato", "Tomatoes", "fresh tomatoes", "chopped tomatoes")}, {"tomato"})
        self.assertNotEqual(IS.canonical_key("tomato paste"), IS.canonical_key("tomatoes"))

    def test_whole_word_matching(self):
        steps = DF.parse_steps("1. Make lemonade.\n2. Add black pepper.\n3. Serve the lemon.")
        self.assertEqual(IS.treatment_of("1", "lemon", steps).steps, (3,))                    # not 'lemonade'
        self.assertEqual(IS.treatment_of("2", "green pepper", steps).state, "not_mentioned")    # not 'black pepper'


class TestStepReading(unittest.TestCase):
    def test_heat_methods_durations_and_brief_words(self):
        r = IS.read_segment("Quickly sauté the peppers for 3 minutes")
        self.assertEqual((r.methods, r.brief, [d.minutes_low for d in r.durations]), (("saute",), ("quickly",), [3.0]))

    def test_duration_units_and_ranges(self):
        d = IS.parse_durations("simmer 20 to 30 minutes, then 1 hour, then 90 seconds, overnight")
        self.assertEqual([(x.minutes_low, x.minutes_high) for x in d],
                         [(20.0, 30.0), (60.0, 60.0), (1.5, 1.5), (None, None)])

    def test_after_cooking_is_not_read_as_cooking(self):
        r = IS.read_segment("Stir in the lemon juice after cooking")
        self.assertEqual((r.heat, r.after), ((), ("after cooking",)))

    def test_cooking_spray_and_oil_are_not_heating(self):
        self.assertEqual(IS.read_segment("Coat the pan with cooking spray").heat, ())

    def test_negated_heat_is_recorded_but_is_not_heat(self):
        r = IS.read_segment("Do not boil the broccoli")
        self.assertEqual((r.heat, r.negated_heat), ((), ("boil",)))
        self.assertEqual(IS.read_segment("Avoid overheating the peppers").heat, ())

    def test_brief_is_never_inferred_from_the_method_or_from_until_tender(self):
        for text in ("Steam the broccoli", "Steam the broccoli until tender", "Cook the peppers until just tender",
                     "Cook quick-cooking oats", "Stir-fry the peppers"):
            self.assertEqual(IS.read_segment(text).brief, (), text)

    def test_a_cue_in_another_segment_is_not_borrowed(self):
        steps = DF.parse_steps("1. Simmer the beans for 40 minutes, garnish with lemon.")
        t = IS.treatment_of("1", "lemon", steps)
        self.assertEqual(t.state, "raw")        # 'garnish' is its own segment; the simmer is not lemon's


# ======================================================================================
# INH-006
# ======================================================================================
class TestInh006(unittest.TestCase):
    def test_prolonged_heating_cannot_be_classified_without_a_reviewed_definition(self):
        r = vitc(["green pepper"], ["Simmer the green pepper for 45 minutes."])
        self.assertEqual(r.applicability_status, X)
        self.assertEqual(fields(r), ["reviewed_definition.vitamin_c_prolonged_heat"])
        p = per(r)["green pepper"]
        self.assertEqual((p["state"], p["methods"], p["durations"][0]["minutes_low"]), ("heated", ["simmer"], 45.0))
        self.assertEqual(r.evidence["prolonged_heat_definition"]["review_status"], "unset")
        self.assertFalse(r.evidence["prolonged_heat_definition"]["usable"])

    def test_brief_heating_is_not_applicable_and_records_the_word_and_step(self):
        r = vitc(["green pepper"], ["Chop.", "Quickly sauté the green pepper for 2 minutes."])
        self.assertEqual(r.applicability_status, N)
        p = per(r)["green pepper"]
        self.assertEqual((p["brief_words"], p["mentions"][0]["instruction_step"]), (["quickly"], 2))
        self.assertEqual([s.step_number for s in r.matched_steps], [2])

    def test_briefly_also_counts(self):
        self.assertEqual(vitc(["spinach"], ["Briefly steam the spinach."]).applicability_status, N)

    def test_raw_and_garnish_are_not_applicable(self):
        for steps in (["Serve the spinach raw."], ["Garnish with lemon."], ["Top with raw spinach."]):
            ing = "lemon" if "lemon" in steps[0] else "spinach"
            r = vitc([ing], steps)
            self.assertEqual(r.applicability_status, N, steps)

    def test_added_after_cooking_is_not_applicable(self):
        r = vitc(["lemon"], ["Simmer the stew for 30 minutes.", "Stir in the lemon juice after cooking."])
        self.assertEqual(r.applicability_status, N)
        self.assertEqual(per(r)["lemon"]["mentions"][0]["after_cooking_words"], ["after cooking"])
        self.assertEqual([s.step_number for s in r.matched_steps], [2])         # not the unrelated simmer step

    def test_method_present_but_duration_absent_is_needs_context(self):
        r = vitc(["broccoli"], ["Steam the broccoli until tender."])
        self.assertEqual(r.applicability_status, X)
        self.assertIsNone(per(r)["broccoli"]["brief_words"] if "brief_words" in per(r)["broccoli"] else None)

    def test_an_ingredient_no_step_names_is_needs_context_and_not_assumed_raw(self):
        r = vitc(["lemon"], ["Simmer the beans for 40 minutes."])
        self.assertEqual(r.applicability_status, X)
        self.assertEqual(fields(r), ["recipe.instructions.ingredient_step"])
        self.assertIn("not assumed raw", r.missing_context[0]["reason"])

    def test_a_clear_garnish_does_not_decide_when_the_ingredient_is_also_used_unclearly_elsewhere(self):
        r = vitc(["lemon"], ["Add the juice of 2 lemons to the sauce.", "Garnish with lemon wedges."])
        self.assertEqual(r.applicability_status, X)
        self.assertEqual(per(r)["lemon"]["state"], "unresolved_mix")
        self.assertEqual(fields(r), ["recipe.instructions.ingredient_treatment"])
        self.assertIn("step 1", r.missing_context[0]["reason"])

    def test_plain_preparation_elsewhere_does_not_block_a_clear_garnish(self):
        r = vitc(["lemon"], ["Slice the lemon thinly.", "Garnish with lemon."])
        self.assertEqual(r.applicability_status, N)
        r = vitc(["spinach"], ["Wash and chop the spinach.", "Briefly steam the spinach."])
        self.assertEqual(r.applicability_status, N)

    def test_brief_heating_is_also_held_back_by_an_unclear_mention(self):
        r = vitc(["spinach"], ["Briefly steam the spinach.", "Stir the spinach into the soup."])
        self.assertEqual((r.applicability_status, per(r)["spinach"]["state"]), (X, "unresolved_mix"))

    def test_an_unrelated_ingredient_being_heated_does_not_count_for_this_one(self):
        r = vitc(["lemon"], ["Simmer the beans for 90 minutes.", "Garnish with lemon."])
        self.assertEqual(r.applicability_status, N)                 # lemon is the garnish; the beans are not lemon

    def test_negated_heating_is_not_evidence_either_way(self):
        r = vitc(["green pepper"], ["Do not boil the green pepper."])
        self.assertEqual(r.applicability_status, X)
        p = per(r)["green pepper"]
        self.assertEqual(p["state"], "neutral_only")
        self.assertEqual(p["mentions"][0]["negated_heat_words"], ["boil"])
        self.assertEqual(fields(r), ["recipe.instructions.ingredient_treatment"])

    def test_missing_instructions_need_context(self):
        r = run("INH-006", VITC, facts_for(ingredients=["lemon"], steps=None, tags={"lemon": (VITC,)}))
        self.assertEqual((r.applicability_status, fields(r)), (X, ["recipe.instructions"]))

    def test_a_step_that_names_the_ingredient_without_saying_how_it_is_used_is_unresolved(self):
        r = vitc(["lemon"], ["Cut the lemon into wedges."])
        self.assertEqual((r.applicability_status, fields(r)), (X, ["recipe.instructions.ingredient_treatment"]))

    def test_multiple_vitamin_c_ingredients_are_judged_separately(self):
        r = vitc(["lemon", "green pepper", "spinach"],
                 ["Garnish with lemon.", "Simmer the green pepper for 45 minutes.", "Briefly steam the spinach."])
        got = {k: v["verdict"] for k, v in per(r).items()}
        self.assertEqual(got, {"lemon": "NOT_APPLICABLE", "green pepper": "NEEDS_CONTEXT", "spinach": "NOT_APPLICABLE"})
        self.assertEqual(r.applicability_status, X)                  # one unresolved keeps the whole rule unresolved
        self.assertEqual(r.evidence["ingredient_verdicts"], {"APPLICABLE": 0, "NOT_APPLICABLE": 2, "NEEDS_CONTEXT": 1})

    def test_not_applicable_only_when_every_ingredient_is_handled_appropriately(self):
        r = vitc(["lemon", "spinach"], ["Garnish with lemon.", "Briefly steam the spinach."])
        self.assertEqual(r.applicability_status, N)
        self.assertEqual(r.conditions_failed, ())

    def test_applicable_is_unreachable_without_a_reviewed_definition(self):
        for text in ("Simmer the peppers for 3 hours.", "Slow cook the peppers all day.", "Cook the peppers overnight.",
                     "Boil the peppers for 8 hours.", "Simmer the peppers for 100 minutes."):
            r = vitc(["peppers"], [text], tags={"peppers": (VITC,)})
            self.assertNotEqual(r.applicability_status, A, text)

    def test_with_a_reviewed_definition_the_threshold_boundaries(self):
        with mock.patch.object(IR, "VITC_PROLONGED_HEAT", REVIEWED_PROLONGED):
            got = {m: vitc(["peppers"], ["Simmer the peppers for %d minutes." % m], tags={"peppers": (VITC,)}).applicability_status
                   for m in (29, 30, 31)}
            self.assertEqual(got, {29: N, 30: A, 31: A})
            r = vitc(["peppers"], ["Simmer the peppers for 20 to 40 minutes."], tags={"peppers": (VITC,)})
            self.assertEqual((r.applicability_status, fields(r)), (X, ["recipe.instructions.heating_duration"]))
            r = vitc(["peppers"], ["Simmer the peppers until soft."], tags={"peppers": (VITC,)})
            self.assertEqual((r.applicability_status, fields(r)), (X, ["recipe.instructions.heating_duration"]))
            r = vitc(["peppers"], ["Slow cook the peppers for 8 hours."], tags={"peppers": (VITC,)})
            self.assertEqual(r.applicability_status, A)
            self.assertEqual(r.conditions_failed, ("no prolonged heat exposure",))

    def test_with_a_reviewed_definition_applicable_wins_over_unresolved_and_not_applicable(self):
        with mock.patch.object(IR, "VITC_PROLONGED_HEAT", REVIEWED_PROLONGED):
            r = vitc(["lemon", "peppers", "spinach"], ["Garnish with lemon.", "Simmer the peppers for 45 minutes."],
                     tags={"lemon": (VITC,), "peppers": (VITC,), "spinach": (VITC,)})        # spinach: not mentioned
        self.assertEqual(r.applicability_status, A)
        self.assertEqual(r.evidence["ingredient_verdicts"], {"APPLICABLE": 1, "NOT_APPLICABLE": 1, "NEEDS_CONTEXT": 1})

    def test_heated_and_also_raw_stays_unresolved_even_with_a_reviewed_definition(self):
        with mock.patch.object(IR, "VITC_PROLONGED_HEAT", REVIEWED_PROLONGED):
            r = vitc(["peppers"], ["Simmer the peppers for 45 minutes.", "Garnish with peppers."], tags={"peppers": (VITC,)})
        self.assertEqual((r.applicability_status, fields(r)), (X, ["recipe.instructions.ingredient_split"]))

    def test_an_unset_definition_cannot_be_reviewed_by_accident(self):
        self.assertFalse(IR.ProlongedHeatDefinition().usable())
        self.assertFalse(IR.ProlongedHeatDefinition(minutes_at_or_above=30.0).usable())          # a number without review
        self.assertTrue(REVIEWED_PROLONGED.usable())

    def test_goal_gating_is_not_applied_and_the_decision_is_recorded(self):
        r = vitc(["lemon"], ["Garnish with lemon."])
        self.assertIn("not applied", r.evidence["goal_gating"])
        self.assertIn("INH-006", IR.OPEN_DECISIONS)

    def test_a_recipe_with_no_tagged_ingredient_line_is_unresolved(self):
        r = run("INH-006", VITC, facts_for(ingredients=["lemon"], steps=["Garnish with lemon."], codes={VITC}))
        self.assertEqual((r.applicability_status, fields(r)), (X, ["recipe.ingredients.NUT_VITC"]))


# ======================================================================================
# INH-007
# ======================================================================================
class TestInh007(unittest.TestCase):
    def test_raw_crucifer_is_not_applicable(self):
        r = cruc(["broccoli"], ["Toss raw broccoli with the dressing."])
        self.assertEqual(r.applicability_status, N)

    def test_explicit_brief_steaming_is_not_applicable(self):
        r = cruc(["broccoli"], ["Steam the broccoli briefly, about 3 minutes."])
        self.assertEqual(r.applicability_status, N)
        self.assertEqual(per(r)["broccoli"]["brief_words"], ["briefly"])
        self.assertEqual(per(r)["broccoli"]["methods"], ["steam"])

    def test_steaming_without_the_brief_wording_is_not_inferred_to_be_brief(self):
        for text in ("Steam the broccoli for 3 minutes.", "Steam the broccoli until tender.", "Steam the broccoli."):
            r = cruc(["broccoli"], [text])
            self.assertEqual(r.applicability_status, X, text)
            self.assertEqual(fields(r), ["reviewed_definition.myrosinase_high_heat_methods"], text)

    def test_brief_is_not_steaming_so_quickly_roasting_is_not_covered(self):
        self.assertEqual(cruc(["broccoli"], ["Quickly roast the broccoli."]).applicability_status, X)

    def test_mustard_forms_added_after_cooking_restore_myrosinase(self):
        for form in ("mustard powder", "ground mustard", "dry mustard", "Mustard Powder"):
            r = cruc(["cauliflower"], ["Roast the cauliflower for 25 minutes.", "Sprinkle with %s." % form])
            self.assertEqual(r.applicability_status, N, form)
            self.assertEqual(per(r)["cauliflower"]["restoration"]["timing"], "restored")

    def test_other_mustards_are_not_confirmed_restoration(self):
        for form in ("Dijon mustard", "prepared mustard", "mustard sauce", "mustard", "yellow mustard", "mustard seeds",
                     "ground mustard seed", "whole grain mustard"):
            r = cruc(["cauliflower"], ["Roast the cauliflower for 25 minutes.", "Serve with %s." % form])
            self.assertEqual(r.applicability_status, X, form)
            self.assertEqual(fields(r), ["reviewed_definition.myrosinase_high_heat_methods"], form)

    def test_mustard_in_the_same_step_needs_an_explicit_after_cooking_cue(self):
        r = cruc(["broccoli"], ["Roast the broccoli for 20 minutes, then stir in mustard powder after cooking."])
        self.assertEqual(r.applicability_status, N)
        r = cruc(["broccoli"], ["Roast the broccoli for 20 minutes with mustard powder."])
        self.assertEqual((r.applicability_status, fields(r)), (X, ["recipe.instructions.mustard_timing"]))

    def test_mustard_added_before_or_during_cooking_does_not_restore(self):
        r = cruc(["broccoli"], ["Mix mustard powder into the oil.", "Roast the broccoli for 20 minutes."])
        self.assertEqual((r.applicability_status, fields(r)), (X, ["recipe.instructions.mustard_timing"]))

    def test_mustard_that_is_itself_cooked_afterwards_does_not_restore(self):
        r = cruc(["broccoli"], ["Roast the broccoli for 20 minutes.", "Simmer the mustard powder sauce for 10 minutes."])
        self.assertEqual(r.applicability_status, X)

    def test_mustard_only_in_the_ingredient_list_has_unclear_timing(self):
        r = run("INH-007", CRUC, facts_for(ingredients=["broccoli", "mustard powder"], steps=["Roast the broccoli."],
                                           tags={"broccoli": (CRUC,)}))
        self.assertEqual((r.applicability_status, fields(r)), (X, ["recipe.instructions.mustard_timing"]))

    def test_negated_mustard_is_not_present(self):
        r = cruc(["broccoli"], ["Roast the broccoli.", "Do not add mustard powder."])
        self.assertEqual(fields(r), ["reviewed_definition.myrosinase_high_heat_methods"])

    def test_ambiguous_treatment_is_needs_context(self):
        r = cruc(["broccoli"], ["Add the broccoli to the pan."])
        self.assertEqual((r.applicability_status, fields(r)), (X, ["recipe.instructions.ingredient_treatment"]))

    def test_an_unrelated_ingredient_being_heated_is_not_this_one(self):
        r = cruc(["broccoli"], ["Roast the potatoes for 30 minutes."])
        self.assertEqual((r.applicability_status, fields(r)), (X, ["recipe.instructions.ingredient_step"]))
        r = cruc(["broccoli"], ["Roast the potatoes for 30 minutes.", "Serve with raw broccoli."])
        self.assertEqual(r.applicability_status, N)

    def test_negated_heating_is_not_evidence(self):
        r = cruc(["broccoli"], ["Do not steam the broccoli."])
        self.assertEqual((r.applicability_status, per(r)["broccoli"]["state"]), (X, "neutral_only"))

    def test_missing_duration_or_temperature_never_decides_anything(self):
        for text in ("Roast the broccoli.", "Roast the broccoli at 450F.", "Roast the broccoli at 450F for 30 minutes."):
            self.assertEqual(cruc(["broccoli"], [text]).applicability_status, X, text)

    def test_missing_instructions(self):
        r = run("INH-007", CRUC, facts_for(ingredients=["broccoli"], steps=None, tags={"broccoli": (CRUC,)}))
        self.assertEqual((r.applicability_status, fields(r)), (X, ["recipe.instructions"]))

    def test_applicable_is_unreachable_while_the_method_list_is_unreviewed(self):
        for text in ("Roast the broccoli for 40 minutes.", "Deep-fry the broccoli.", "Grill the broccoli.", "Bake the broccoli."):
            r = cruc(["broccoli"], [text])
            self.assertNotEqual(r.applicability_status, A, text)
            self.assertFalse(r.evidence["high_heat_definition"]["usable"])
            self.assertEqual(r.evidence["high_heat_definition"]["review_status"], "unreviewed")

    def test_the_proposed_methods_are_recorded_but_unused(self):
        r = cruc(["broccoli"], ["Roast the broccoli."])
        self.assertEqual(per(r)["broccoli"]["method_in_unreviewed_list"], ["roast"])
        self.assertEqual(r.applicability_status, X)

    def test_with_a_reviewed_list_a_high_heat_method_without_restoration_is_applicable(self):
        with mock.patch.object(IR, "MYROSINASE_HIGH_HEAT", REVIEWED_HIGH_HEAT):
            self.assertEqual(cruc(["broccoli"], ["Roast the broccoli."]).applicability_status, A)
            self.assertEqual(cruc(["broccoli"], ["Roast the broccoli.", "Sprinkle with mustard powder."]).applicability_status, N)
            self.assertEqual(cruc(["broccoli"], ["Steam the broccoli briefly."]).applicability_status, N)
            r = cruc(["broccoli"], ["Boil the broccoli."])             # method not in the reviewed list
            self.assertEqual((r.applicability_status, fields(r)), (X, ["reviewed_definition.myrosinase_high_heat_methods"]))

    def test_multiple_crucifers_aggregate_and_report_each(self):
        steps = ["Serve raw kale.", "Roast the broccoli for 25 minutes."]
        r = cruc(["kale", "broccoli"], steps)
        self.assertEqual({k: v["verdict"] for k, v in per(r).items()}, {"kale": "NOT_APPLICABLE", "broccoli": "NEEDS_CONTEXT"})
        self.assertEqual(r.applicability_status, X)
        with mock.patch.object(IR, "MYROSINASE_HIGH_HEAT", REVIEWED_HIGH_HEAT):
            self.assertEqual(cruc(["kale", "broccoli"], steps).applicability_status, A)
        r = cruc(["kale", "cabbage"], ["Serve raw kale.", "Garnish with cabbage."])
        self.assertEqual(r.applicability_status, N)

    def test_mustard_restoration_is_per_ingredient_timing(self):
        steps = ["Roast the broccoli.", "Add mustard powder.", "Roast the cauliflower."]
        r = cruc(["broccoli", "cauliflower"], steps)
        got = {k: v["restoration"]["timing"] for k, v in per(r).items()}
        self.assertEqual(got, {"broccoli": "restored", "cauliflower": "unclear"})
        self.assertEqual(r.applicability_status, X)


# ======================================================================================
# INH-005
# ======================================================================================
def egg(steps, ingredients=("flour",)):
    return run("INH-005", "ING_RAW_EGG_WHITE", facts_for(ingredients=list(ingredients), steps=steps))


class TestInh005(unittest.TestCase):
    def test_raw_egg_white_needs_the_frequency_and_is_never_applicable(self):
        r = egg(["Whisk the raw egg whites into the drink."])
        self.assertEqual(r.applicability_status, X)
        self.assertEqual(fields(r), ["meal_history.raw_egg_white_frequency"])
        self.assertEqual(r.evidence["egg_mentions"][0]["state"], "raw")

    def test_clearly_cooked_egg_white_is_not_applicable(self):
        for text in ("Scramble the egg whites in a hot pan.", "Bake the egg whites in a muffin tin for 15 minutes.",
                     "Poach the egg whites."):
            r = egg([text])
            self.assertEqual(r.applicability_status, N, text)
            self.assertIn("cooked egg intake is not a concern", r.reason)

    def test_a_cooking_word_elsewhere_in_the_segment_is_not_the_egg_being_cooked(self):
        """A false 'cooked' would be a wrong NOT_APPLICABLE, so the heat word must sit right before the egg."""
        for text in ("Fold the egg whites into the baked pie crust.", "Whisk baking powder and egg whites together.",
                     "Mix brown sugar and egg whites.", "Beat the egg whites, then bake the casserole.",
                     "Pour the egg whites over the fried rice mixture.", "Add the 4 egg whites to the roasting pan."):
            self.assertEqual(egg([text]).applicability_status, X, text)

    def test_imperative_and_participle_forms_are_cooked(self):
        for text in ("Gently scramble the egg whites.", "Chop the hard-boiled egg whites.", "Cook the egg whites until set.",
                     "Fry egg whites in a pan.", "Add scrambled egg whites to the bowl."):
            self.assertEqual(egg([text]).applicability_status, N, text)

    def test_an_ingredient_line_alone_never_decides_the_state(self):
        r = egg(["Scramble the egg whites."], ingredients=("egg whites",))          # named in both places
        self.assertEqual(r.applicability_status, N)
        r = egg(["Serve."], ingredients=("egg whites",))
        self.assertEqual((r.applicability_status, fields(r)), (X, ["recipe.instructions.egg_white_state"]))

    def test_a_mix_of_raw_and_cooked_is_not_cleared(self):
        r = egg(["Scramble the egg whites.", "Stir raw egg whites into the shake."])
        self.assertEqual((r.applicability_status, fields(r)), (X, ["meal_history.raw_egg_white_frequency"]))

    def test_unclear_state_is_needs_context(self):
        for text in ("Beat the egg whites until stiff peaks form.", "Fold in the egg whites.", "Chop the egg whites."):
            r = egg([text])
            self.assertEqual((r.applicability_status, fields(r)), (X, ["recipe.instructions.egg_white_state"]), text)

    def test_whole_egg_with_an_ambiguous_state(self):
        facts = facts_for(ingredients=["eggs"], steps=["Mix the eggs into the dressing."])
        self.assertEqual(IR.inhibitor_candidate_facts(facts), [])                       # not a candidate: BIO-011 covers eggs
        r = run("INH-005", "ING_RAW_EGG_WHITE", facts)
        self.assertEqual((r.applicability_status, fields(r)), (X, ["recipe.instructions.egg_white_state"]))

    def test_a_raw_whole_egg_is_a_candidate_and_needs_frequency(self):
        facts = facts_for(ingredients=["eggs"], steps=["Blend the raw eggs into the sauce."])
        [f] = IR.inhibitor_candidate_facts(facts)
        self.assertEqual((f.code, f.source, f.value["subject"], f.value["instruction_step"]),
                         ("ING_RAW_EGG_WHITE", "recipe_process", "raw_whole_egg", 1))
        self.assertEqual(run("INH-005", "ING_RAW_EGG_WHITE", facts).applicability_status, X)

    def test_a_pasteurized_product_is_recorded_but_does_not_satisfy_the_rule(self):
        r = egg(["Blend pasteurized raw egg whites into the shake."])
        self.assertEqual(r.applicability_status, X)
        self.assertTrue(r.evidence["egg_mentions"][0]["pasteurized"])
        self.assertIn("pasteurized", r.reason)
        r = egg(["Stir in the pasteurized egg whites."])
        self.assertEqual(r.applicability_status, X)

    def test_no_relevant_instruction(self):
        r = egg(["Serve warm."])
        self.assertEqual((r.applicability_status, fields(r)), (X, ["recipe.instructions.egg_white_state"]))
        r = egg(None)
        self.assertEqual(r.applicability_status, X)
        r = run("INH-005", "ING_RAW_EGG_WHITE", facts_for(ingredients=["flour"], steps=["Serve warm."]))
        self.assertEqual((r.applicability_status, fields(r)), (X, ["recipe.instructions.egg_white_state"]))

    def test_negated_wording_decides_nothing(self):
        r = egg(["Do not cook the egg whites."])
        self.assertEqual(r.applicability_status, X)
        self.assertEqual(r.evidence["egg_mentions"][0]["negated_heat_words"], ["cook"])
        self.assertEqual(r.evidence["egg_mentions"][0]["state"], "unclear")
        self.assertEqual(egg(["Do not use egg whites."]).applicability_status, X)

    def test_cooking_in_another_segment_is_not_borrowed(self):
        self.assertEqual(egg(["Chop the egg whites, then bake the casserole."]).applicability_status, X)

    def test_egg_white_named_only_in_the_ingredient_list(self):
        r = run("INH-005", "ING_RAW_EGG_WHITE", facts_for(ingredients=["egg whites"], steps=["Mix well."]))
        self.assertEqual(r.applicability_status, X)
        self.assertEqual(r.evidence["egg_mentions"][0]["origin"], "ingredient")

    def test_candidate_facts_come_from_text_not_tags(self):
        facts = facts_for(ingredients=["eggs"], steps=["Beat the egg whites until stiff.", "Bake."], tags={"eggs": ("ING_EGG",)})
        got = IR.inhibitor_candidate_facts(facts)
        self.assertEqual([(f.value["subject"], f.value["instruction_step"]) for f in got], [("egg_white", 1)])
        self.assertEqual(IR.inhibitor_candidate_facts(facts_for(ingredients=["eggs"], steps=["Boil the eggs."])), [])
        self.assertEqual(IR.inhibitor_candidate_facts(facts_for(ingredients=["eggplant"], steps=["Slice the eggplant."])), [])

    def test_applicable_is_unreachable(self):
        for text in ("Drink raw egg whites daily.", "Whisk raw egg whites into every shake.", "Use raw egg whites."):
            self.assertNotEqual(egg([text]).applicability_status, A)
        self.assertIn("INH-005", IR.OPEN_DECISIONS)

    def test_matched_steps_are_the_egg_steps(self):
        r = egg(["Chop onions.", "Scramble the egg whites."])
        self.assertEqual([s.step_number for s in r.matched_steps], [2])


class TestInh005Pipeline(unittest.TestCase):
    def setUp(self):
        self.conn = build_db(rules={"INH-005": "ING_RAW_EGG_WHITE"}, recipes={
            "r1": {"name": "Meringue", "ingredients": [("eggs", ("ING_EGG",))], "steps": ["Beat the egg whites until stiff."]},
            "r2": {"name": "Omelette", "ingredients": [("eggs", ("ING_EGG",))], "steps": ["Fry the eggs."]},
        })

    def tearDown(self):
        self.conn.close()

    def test_called_only_where_an_egg_white_is_named_and_never_through_a_tag(self):
        got = {c.rule_id: c for c in detect_rules.detect_rules(self.conn, "r1")}
        self.assertEqual(got["INH-005"].trigger_source, "recipe_process")
        self.assertEqual(got["INH-005"].matched_facts[0].code, "ING_RAW_EGG_WHITE")
        self.assertNotIn("INH-005", {c.rule_id for c in detect_rules.detect_rules(self.conn, "r2")})
        self.assertEqual(self.conn.execute("SELECT count(*) FROM ingredient_rule_tags WHERE rule_code='ING_RAW_EGG_WHITE'").fetchone()[0], 0)

    def test_result_has_trigger_source_steps_and_missing_context(self):
        d = {e.rule_id: e for e in ev.evaluate_recipe_rules(self.conn, "r1")}["INH-005"].as_dict()
        self.assertEqual((d["trigger_source"], d["applicability_status"]), ("recipe_process", "NEEDS_CONTEXT"))
        self.assertEqual([s["step_number"] for s in d["matched_on"]["steps"]], [1])
        self.assertEqual(d["missing_context"][0]["field"], "recipe.instructions.egg_white_state")


# ======================================================================================
# do_not_automate guards: INH-003, 008, 009, 010
# ======================================================================================
MANUAL = {"INH-003": "NUT_CALCIUM", "INH-008": "MED_ACID_SUPPRESS", "INH-009": "NUT_ZINC", "INH-010": "CMP_FIBER_PHYTATE"}


class TestManualAdvisories(unittest.TestCase):
    def go(self, rule, ctx=None, facts=None):
        return run(rule, MANUAL[rule], facts or facts_for(ingredients=["milk"], steps=["Serve."]), ctx)

    def test_registered_and_never_an_automatic_verdict(self):
        for rule in MANUAL:
            self.assertIn(rule, ev.RULE_EVALUATORS)
            r = self.go(rule)
            self.assertEqual(r.applicability_status, X, rule)
            self.assertEqual(fields(r), ["manual_review"], rule)
            self.assertTrue(r.evidence["manual_advisory"])
            self.assertEqual(r.conditions_failed, ("the rule may be automated",))
            self.assertNotIn("evaluator not implemented", r.reason)

    def test_context_omitted_empty_and_provided_are_distinguished(self):
        got = {}
        for label, ctx in (("none", None), ("omitted", EvaluationContext(member_id="m")),
                           ("empty", EvaluationContext(member_id="m", medications=(), supplements=())),
                           ("provided", EvaluationContext(member_id="m", medications=("warfarin",), supplements=("zinc",)))):
            got[label] = self.go("INH-008", ctx).evidence["member_context"]
        self.assertEqual(got["none"], {"medications": "omitted", "supplements": "omitted"})
        self.assertEqual(got["omitted"], got["none"])
        self.assertEqual(got["empty"], {"medications": "empty", "supplements": "empty"})
        self.assertEqual(got["provided"], {"medications": "provided", "supplements": "provided"})

    def test_matching_and_nonmatching_context_do_not_change_the_verdict(self):
        for ctx in (EvaluationContext(member_id="m", medications=("omeprazole",), supplements=("iron",)),
                    EvaluationContext(member_id="m", medications=("ibuprofen",), supplements=("fish oil",))):
            for rule in MANUAL:
                self.assertEqual(self.go(rule, ctx).applicability_status, X)

    def test_private_details_never_appear_in_the_result(self):
        ctx = EvaluationContext(member_id="m", medications=("omeprazole",), supplements=("zinc picolinate",),
                                conditions=("hemochromatosis",))
        for rule in MANUAL:
            text = str(self.go(rule, ctx).as_dict()).lower()
            for secret in ("omeprazole", "zinc picolinate", "hemochromatosis"):
                self.assertNotIn(secret, text, rule)

    def test_nothing_is_inferred_from_the_recipe(self):
        conn = build_db(rules={**MANUAL}, recipes={"r": {"name": "R", "steps": ["Take the supplement."], "ingredients": [
            ("calcium supplement", ()), ("zinc lozenges", ()), ("omeprazole", ()), ("bran fibre supplement", ())]}})
        self.assertEqual({c.rule_id for c in detect_rules.detect_rules(conn, "r")} & set(MANUAL), set())
        conn.close()

    def test_a_triggered_manual_rule_says_it_is_manual_in_the_full_flow(self):
        conn = build_db(rules={"INH-003": "NUT_CALCIUM"}, recipes={"r": {"name": "R", "steps": ["Serve."],
                        "ingredients": [("milk", ("NUT_CALCIUM",))]}})
        [e] = ev.evaluate_recipe_rules(conn, "r")
        self.assertEqual((e.rule_id, e.applicability_status, e.missing_context[0]["field"]), ("INH-003", X, "manual_review"))
        conn.close()


class TestPublicEndpointCannotLoadMembers(unittest.TestCase):
    """scripts/api.py is mounted publicly and names a person only by ?user_id=. Member health data must
    never be loadable through it."""

    def test_the_public_api_never_touches_member_data(self):
        text = (REPO / "scripts" / "api.py").read_text()
        for forbidden in ("member_context", "load_member_context", "member_conditions", "household_members",
                          "EvaluationContext", "medication", "supplement"):
            self.assertNotIn(forbidden, text, forbidden)

    def test_the_public_evaluation_is_the_recipe_alone(self):
        text = (REPO / "scripts" / "api.py").read_text()
        self.assertIn("evaluate_all_rules(conn, facts)", text)            # no context argument
        self.assertNotIn("evaluate_all_rules(conn, facts, ", text)

    def test_only_the_authenticated_route_loads_a_member(self):
        main = (REPO / "api" / "app" / "main.py").read_text()
        evaluation = (REPO / "api" / "app" / "recipe_evaluation.py").read_text()
        self.assertIn("Depends(auth.signed_in)", main[main.index("def evaluate_for_member") - 200:main.index("def evaluate_for_member") + 200])
        self.assertIn("load_member_context(conn, body.member_id, caller_user_id", evaluation)
        for path in (REPO / "scripts").glob("*.py"):
            if path.name != "member_context.py":
                self.assertNotIn("load_member_context(", path.read_text(), path.name)


# ======================================================================================
# INH-011 boundaries
# ======================================================================================
def fat_facts(fat):
    n = {"Macro_Carbohydrate": (20.0, "g"), "Macro_Protein": (2.0, "g"), "Fiber": (3.0, "g"), "Energy": (90.0, "kcal")}
    if fat is not None:
        n["Macro_Fat"] = (fat, "g")
    return facts_for(ingredients=["carrots"], nutrition=n, tags={"carrots": ("NUT_CAROTENOIDS",)})


class TestInh011(unittest.TestCase):
    def candidate(self, fat):
        return {f.code for f in NF.nutrition_candidate_facts(fat_facts(fat))
                if f.confidence != "unknown"} & {"MACRO_FAT_LOW"}

    def test_fat_free_is_exactly_zero_grams_at_the_boundaries(self):
        got = {fat: bool(self.candidate(fat)) for fat in (0.0, 0.1, 0.4, 0.5)}
        self.assertEqual(got, {0.0: True, 0.1: False, 0.4: False, 0.5: False})

    def test_the_verdict_at_each_boundary(self):
        got = {fat: str(run("INH-011", "MACRO_FAT_LOW", fat_facts(fat)).applicability_status)
               for fat in (0.0, 0.1, 0.4, 0.5)}
        self.assertEqual(got, {0.0: "APPLICABLE", 0.1: "NOT_APPLICABLE", 0.4: "NOT_APPLICABLE", 0.5: "NOT_APPLICABLE"})

    def test_missing_fat_is_unknown_and_needs_context(self):
        facts = fat_facts(None)
        fact = [f for f in NF.nutrition_candidate_facts(facts) if f.code == "MACRO_FAT_LOW"][0]
        self.assertEqual((fact.value, fact.confidence), (None, "unknown"))
        r = run("INH-011", "MACRO_FAT_LOW", facts)
        self.assertEqual((r.applicability_status, fields(r)), (X, ["recipe_nutrition.Macro_Fat"]))

    def test_the_definition_is_marked_unreviewed_on_every_result(self):
        for fat in (0.0, 0.4, None):
            r = run("INH-011", "MACRO_FAT_LOW", fat_facts(fat))
            if fat is None:
                continue                                    # the marker sits beside the fat reading, which is absent here
            [d] = r.evidence["definitions_under_review"]
            self.assertEqual((d["term"], d["threshold"], d["unit"], d["definition_status"]), ("fat-free", 0.0, "g", "unreviewed"))
            self.assertIn("0.5 g", d["note"])
        self.assertEqual(NF.NUTRITION_RULE_CONFIG["MACRO_FAT_LOW"].definition_status, "unreviewed")

    def test_the_threshold_is_configurable_without_touching_the_evaluator(self):
        reviewed = NF.NutritionCriterion("fat_free", "Macro_Fat", "<", 0.5, "g", "per_serving", "reviewed", "nutrition review", "r",
                                         definition_status="reviewed")
        with mock.patch.dict(NF.NUTRITION_RULE_CONFIG, {"MACRO_FAT_LOW": reviewed}):
            got = {fat: bool(self.candidate(fat)) for fat in (0.0, 0.1, 0.4, 0.5)}
            r = run("INH-011", "MACRO_FAT_LOW", fat_facts(0.4))
        self.assertEqual(got, {0.0: True, 0.1: True, 0.4: True, 0.5: False})
        self.assertNotIn("definitions_under_review", r.evidence)

    def test_the_evidence_keeps_value_unit_and_threshold(self):
        r = run("INH-011", "MACRO_FAT_LOW", fat_facts(0.0))
        self.assertEqual((r.evidence["fat"]["reading"]["value"], r.evidence["fat"]["reading"]["unit"],
                          r.evidence["fat"]["criterion"]["threshold"]), (0.0, "g", 0.0))


# ======================================================================================
# Registry and full-flow behaviour
# ======================================================================================
class TestFullFlow(unittest.TestCase):
    def setUp(self):
        self.conn = build_db(
            rules={"INH-006": VITC, "INH-007": CRUC},
            recipes={"r": {"name": "R", "ingredients": [("lemon", (VITC,)), ("broccoli", (VITC, CRUC)), ("green pepper", (VITC,))],
                           "steps": ["Roast the broccoli for 25 minutes.", "Sprinkle with mustard powder.",
                                     "Garnish with lemon.", "Simmer the green pepper for 45 minutes."]}})

    def tearDown(self):
        self.conn.close()

    def test_both_rules_return_decisions_with_the_new_response_fields(self):
        by = {e.rule_id: e for e in ev.evaluate_recipe_rules(self.conn, "r")}
        self.assertEqual(by["INH-007"].applicability_status, N)
        self.assertEqual(by["INH-006"].applicability_status, X)              # the pepper and the roasted broccoli are unclassified
        d = by["INH-006"].as_dict()
        self.assertEqual(d["trigger_source"], "ingredient")
        self.assertEqual({i["name"] for i in d["matched_on"]["ingredients"]}, {"lemon", "broccoli", "green pepper"})
        self.assertEqual([s["step_number"] for s in d["matched_on"]["steps"]], [1, 3, 4])
        self.assertTrue(d["matched_on"]["facts"] and d["missing_context"] and d["evidence"]["ingredients"])
        self.assertTrue(d["reason"])
        for old in ("rule_id", "applicability_status", "conditions_checked", "reason", "candidate", "trigger_code"):
            self.assertIn(old, d)

    def test_each_inhibitor_result_ties_a_step_or_says_why_not(self):
        for e in ev.evaluate_recipe_rules(self.conn, "r"):
            if e.rule_id in ("INH-006", "INH-007"):
                self.assertTrue(e.matched_steps or e.missing_context, e.rule_id)


if __name__ == "__main__":
    unittest.main()
