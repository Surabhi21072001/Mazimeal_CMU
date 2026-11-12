#!/usr/bin/env python3
"""Phase 5 (no database): INH-012, the engine-level rule that reads the other rules' results.

    python3 -m unittest tests.test_derived_engine -v
"""
from __future__ import annotations

import copy
import dataclasses
import random
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests"))

import detect_rules  # noqa: E402
import engine_rules as ER  # noqa: E402
import evaluate_rules as ev  # noqa: E402
from evaluate_rules import ApplicabilityStatus as S  # noqa: E402
from derived_fixtures import build_db, facts_for  # noqa: E402

A, N, X = S.APPLICABLE, S.NOT_APPLICABLE, S.NEEDS_CONTEXT


def primary(rule_id, status, trigger="ING_TOMATO", reason="r"):
    return ev.EvaluatedRule(rule_id=rule_id, rule_name=rule_id, trigger_code=trigger, automation_status="recipe_safe",
                            candidate=True, applicability_status=status, conditions_checked=(), conditions_passed=(),
                            conditions_failed=(), reason=reason)


def engine(results, pairs=None, conn=None):
    conn = conn or build_db()
    return ER.evaluate_engine_rules(conn, facts_for(), None, results, pairs)


class TestConflictPairs(unittest.TestCase):
    def test_the_only_configured_pair_is_the_one_the_rule_text_names(self):
        self.assertEqual([p.members for p in ER.CONFLICT_PAIRS], [("BIO-003", "INH-006")])
        pair = ER.CONFLICT_PAIRS[0]
        self.assertIn("lycopene", pair.source)
        self.assertIn("vitamin C", pair.source)
        self.assertEqual(pair.review_status, "wording")

    def test_pair_members_must_be_distinct_and_sorted(self):
        with self.assertRaises(ValueError):
            ER.ConflictPair(("B", "A"), "x", "y", "z")
        with self.assertRaises(ValueError):
            ER.ConflictPair(("A", "A"), "x", "y", "z")


class TestPairState(unittest.TestCase):
    def state(self, a, b):
        return ER.pair_state(primary("BIO-003", a), primary("INH-006", b))

    def test_both_live_is_a_conflict(self):
        self.assertEqual(self.state(A, A), "conflict")

    def test_one_not_being_recommended_means_nothing_competes(self):
        for other in (A, N, X):
            self.assertEqual(self.state(N, other), "none")
            self.assertEqual(self.state(other, N), "none")

    def test_any_undecided_result_leaves_it_undetermined(self):
        for pair in ((A, X), (X, A), (X, X)):
            self.assertEqual(self.state(*pair), "undetermined")


class TestEngineStage(unittest.TestCase):
    def test_both_applicable_is_applicable_and_explains_the_tradeoff(self):
        [r] = engine([primary("BIO-003", A), primary("INH-006", A)])
        self.assertEqual((r.rule_id, r.applicability_status, r.trigger_source), ("INH-012", A, "engine_result"))
        self.assertIn("lycopene", r.reason)
        self.assertIn("vitamin C", r.reason)

    def test_an_undecided_member_needs_context_and_is_named(self):
        [r] = engine([primary("BIO-003", A), primary("INH-006", X, reason="condition evaluator not implemented")])
        self.assertEqual(r.applicability_status, X)
        self.assertEqual([m["field"] for m in r.missing_context], ["primary_results.INH-006"])
        self.assertIn("condition evaluator not implemented", r.missing_context[0]["reason"])

    def test_both_undecided_names_both(self):
        [r] = engine([primary("BIO-003", X), primary("INH-006", X)])
        self.assertEqual([m["field"] for m in r.missing_context], ["primary_results.BIO-003", "primary_results.INH-006"])

    def test_a_recommendation_that_is_not_being_made_means_no_conflict(self):
        [r] = engine([primary("BIO-003", N), primary("INH-006", X)])
        self.assertEqual((r.applicability_status, r.missing_context), (N, ()))

    def test_a_single_member_is_not_a_conflict_and_is_not_called(self):
        self.assertEqual(engine([primary("BIO-003", A)]), [])
        self.assertEqual(engine([primary("INH-006", A)]), [])

    def test_no_primary_results_means_not_called(self):
        self.assertEqual(engine([]), [])

    def test_unrelated_primary_results_do_not_call_it(self):
        self.assertEqual(engine([primary("BIO-002", A), primary("GLY-002", A)]), [])

    def test_it_is_not_called_when_the_rule_is_inactive_or_missing(self):
        conn = build_db(rules={})
        self.assertEqual(engine([primary("BIO-003", A), primary("INH-006", A)], conn=conn), [])
        conn = build_db()
        conn.execute("UPDATE business_rules SET is_active = 0")
        conn.commit()                  # the loader's fallback path rolls back, as the detector's does
        self.assertEqual(engine([primary("BIO-003", A), primary("INH-006", A)], conn=conn), [])


class TestExplicitEffects(unittest.TestCase):
    def setUp(self):
        self.inputs = [primary("BIO-003", A), primary("INH-006", A), primary("GLY-002", A, "MACRO_CARB")]
        [self.r] = engine(self.inputs)

    def test_primary_results_are_not_modified(self):
        before = copy.deepcopy(self.inputs)
        ids = [id(x) for x in self.inputs]
        engine(self.inputs)
        self.assertEqual(self.inputs, before)
        self.assertEqual([id(x) for x in self.inputs], ids)
        self.assertEqual(len(self.inputs), 3)

    def test_results_are_immutable(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            self.inputs[0].applicability_status = N
        with self.assertRaises(dataclasses.FrozenInstanceError):
            self.r.reason = "changed"

    def test_nothing_is_suppressed_or_re_ranked_and_it_says_so(self):
        self.assertEqual(self.r.evidence["suppressed_rules"], [])
        self.assertEqual(self.r.evidence["priority_changes"], [])
        self.assertEqual(self.r.evidence["annotations"][0]["rule_ids"], ["BIO-003", "INH-006"])

    def test_it_records_which_primary_results_caused_it(self):
        self.assertEqual([(t["rule_id"], t["applicability_status"]) for t in self.r.evidence["triggered_by"]],
                         [("BIO-003", "APPLICABLE"), ("INH-006", "APPLICABLE")])
        self.assertEqual(self.r.matched_facts[0].source, "engine_result")
        self.assertEqual(self.r.matched_facts[0].value["statuses"], {"BIO-003": "APPLICABLE", "INH-006": "APPLICABLE"})

    def test_unrelated_primary_results_are_not_listed_as_causes(self):
        self.assertNotIn("GLY-002", [t["rule_id"] for t in self.r.evidence["triggered_by"]])


class TestDeterminismAndRecursion(unittest.TestCase):
    PAIRS = (ER.ConflictPair(("A-1", "A-2"), "p1", "e1", "s"), ER.ConflictPair(("B-1", "B-2"), "p2", "e2", "s"),
             ER.ConflictPair(("BIO-003", "INH-006"), "tomatoes", "lycopene vs vitamin C", "s"))

    def summary(self, results):
        return [(r.rule_id, str(r.applicability_status), r.reason,
                 [t["rule_id"] for t in r.evidence["triggered_by"]], [m["field"] for m in r.missing_context])
                for r in results]

    def test_the_same_inputs_give_the_same_result_whatever_their_order(self):
        base = [primary("BIO-003", A), primary("INH-006", A), primary("A-1", A), primary("A-2", X),
                primary("B-1", N), primary("B-2", A)]
        want = self.summary(engine(base, self.PAIRS))
        rng = random.Random(7)
        for _ in range(25):
            shuffled = base[:]
            rng.shuffle(shuffled)
            self.assertEqual(self.summary(engine(shuffled, self.PAIRS)), want)

    def test_repeated_evaluation_is_identical(self):
        base = [primary("BIO-003", A), primary("INH-006", A)]
        self.assertEqual(engine(base), engine(base))

    def test_a_real_conflict_outranks_an_undetermined_pair_and_both_are_reported(self):
        base = [primary("BIO-003", A), primary("INH-006", A), primary("A-1", A), primary("A-2", X)]
        [r] = engine(base, self.PAIRS)
        self.assertEqual(r.applicability_status, A)
        self.assertEqual([p["state"] for p in r.evidence["pairs"]], ["undetermined", "conflict"])   # sorted by members
        self.assertEqual(len(r.matched_facts), 2)

    def test_an_undetermined_pair_outranks_a_resolved_one(self):
        base = [primary("A-1", N), primary("A-2", A), primary("B-1", A), primary("B-2", X)]
        [r] = engine(base, self.PAIRS)
        self.assertEqual(r.applicability_status, X)
        self.assertEqual([m["field"] for m in r.missing_context], ["primary_results.B-2"])

    def test_only_resolved_pairs_is_not_applicable(self):
        [r] = engine([primary("A-1", N), primary("A-2", A)], self.PAIRS)
        self.assertEqual(r.applicability_status, N)

    def test_there_is_one_engine_result_however_many_pairs_conflict(self):
        base = [primary("BIO-003", A), primary("INH-006", A), primary("A-1", A), primary("A-2", A)]
        self.assertEqual(len(engine(base, self.PAIRS)), 1)

    def test_its_own_result_is_never_an_input_so_it_cannot_recurse(self):
        base = [primary("BIO-003", A), primary("INH-006", A)]
        first = engine(base)
        again = engine(base + first)                 # feeding the engine result back in
        self.assertEqual(len(again), 1)
        self.assertEqual(self.summary(first), self.summary(again))
        self.assertEqual(ER.conflicts_present([primary("INH-012", A)] + base), ER.conflicts_present(base))

    def test_it_is_not_an_ordinary_evaluator_or_trigger(self):
        self.assertNotIn("INH-012", ev.RULE_EVALUATORS)
        self.assertEqual(ER.ENGINE_RULE_IDS, {"INH-012"})

    def test_ordinary_detection_never_calls_it_even_when_the_rule_is_active(self):
        conn = build_db(recipes={"r1": {"name": "T", "ingredients": [("tomatoes", ("ING_TOMATO",))],
                                        "steps": ["Cook the tomatoes."]}},
                        extra_rules=[("BIO-003", "ING_TOMATO"), ("INH-006", "NUT_VITC")])
        conn.execute("INSERT INTO ingredient_rule_tags VALUES ((SELECT ingredient_id FROM ingredients LIMIT 1), 'NUT_VITC')")
        ids = {c.rule_id for c in detect_rules.detect_rules(conn, "r1")}
        self.assertIn("BIO-003", ids)
        self.assertNotIn("INH-012", ids)


class TestThroughTheFullFlow(unittest.TestCase):
    def setUp(self):
        self.conn = build_db(
            recipes={"r1": {"name": "Tomato", "ingredients": [("tomatoes", ("ING_TOMATO", "NUT_VITC")), ("olive oil", ())],
                            "steps": ["Cook the tomatoes in olive oil."]},
                     "r2": {"name": "Rice", "ingredients": [("rice", ())], "steps": ["Boil rice."]}},
            extra_rules=[("BIO-003", "ING_TOMATO"), ("INH-006", "NUT_VITC")])

    def tearDown(self):
        self.conn.close()

    def test_engine_results_follow_the_primary_results(self):
        out = ev.evaluate_recipe_rules(self.conn, "r1")
        ids = [r.rule_id for r in out]
        self.assertEqual(ids[-1], "INH-012")
        self.assertEqual(len(ids), len(set(ids)))
        by = {r.rule_id: r for r in out}
        self.assertEqual(by["BIO-003"].applicability_status, N)          # fat already present
        self.assertEqual(by["INH-012"].applicability_status, N)          # so nothing competes

    def test_a_recipe_without_the_pair_has_no_engine_result(self):
        self.assertNotIn("INH-012", {r.rule_id for r in ev.evaluate_recipe_rules(self.conn, "r2")})

    def test_evaluate_primary_rules_alone_never_contains_it(self):
        facts = ev.build_recipe_facts(self.conn, "r1")
        self.assertNotIn("INH-012", {r.rule_id for r in ev.evaluate_primary_rules(self.conn, facts)})

    def test_primary_results_are_identical_with_and_without_the_engine_stage(self):
        facts = ev.build_recipe_facts(self.conn, "r1")
        alone = ev.evaluate_primary_rules(self.conn, facts)
        full = ev.evaluate_all_rules(self.conn, facts)
        self.assertEqual(full[:len(alone)], alone)

    def test_the_result_serialises_with_trigger_source_and_facts(self):
        d = {r.rule_id: r for r in ev.evaluate_recipe_rules(self.conn, "r1")}["INH-012"].as_dict()
        self.assertEqual(d["trigger_source"], "engine_result")
        self.assertEqual(d["matched_on"]["facts"][0]["source"], "engine_result")
        self.assertEqual(d["evidence"]["suppressed_rules"], [])


if __name__ == "__main__":
    unittest.main()
