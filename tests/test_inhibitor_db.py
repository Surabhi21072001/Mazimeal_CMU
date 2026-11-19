#!/usr/bin/env python3
"""PostgreSQL tests for the inhibitor rules over the 400 seed recipes.

Runs ONLY against a disposable local database loaded from the repository (tests/load_local_db.sh), and
skips otherwise:

    MAZIMEAL_TEST_DSN="postgresql:///mazi_derived_audit?host=/tmp" python3 -m unittest tests.test_inhibitor_db -v

tests/dbguard.py refuses any non-local host before and after connecting. Every write a test makes is rolled back.
"""
from __future__ import annotations

import collections
import json
import os
import sys
import unittest
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests"))

import dbguard  # noqa: E402

DSN = os.environ.get("MAZIMEAL_TEST_DSN")
try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None

# Verdict counts (APPLICABLE, NOT_APPLICABLE, NEEDS_CONTEXT) of every rule that existed before the
# inhibitor evaluators, measured on the 400 seed recipes BEFORE this change. None may move.
PRE_EXISTING = {
    "BIO-001": (0, 0, 12), "BIO-002": (11, 18, 71), "BIO-003": (1, 9, 48), "BIO-004": (0, 0, 14),
    "BIO-005": (0, 0, 14), "BIO-006": (0, 0, 17), "BIO-007": (8, 6, 3), "BIO-008": (0, 0, 26),
    "BIO-009": (0, 0, 76), "BIO-010": (0, 0, 76), "BIO-011": (111, 13, 0), "BIO-012": (0, 0, 26),
    "BIO-013": (0, 0, 17), "BIO-014": (0, 0, 6), "BIO-015": (0, 0, 44),
    "GLY-002": (357, 40, 0), "GLY-003": (0, 209, 188), "GLY-004": (0, 110, 287), "GLY-005": (0, 0, 82),
    "GLY-007": (18, 0, 0), "GLY-008": (0, 0, 76), "GLY-009": (0, 30, 367), "GLY-011": (0, 0, 397),
    "GLY-015": (4, 0, 0),
    "SYN-001": (0, 0, 21), "SYN-002": (0, 0, 25), "SYN-003": (0, 0, 5), "SYN-004": (0, 0, 4),
    "SYN-005": (0, 0, 81), "SYN-006": (0, 0, 25), "SYN-007": (0, 0, 5), "SYN-008": (0, 0, 21),
    "SYN-009": (0, 0, 37), "SYN-011": (0, 0, 8), "SYN-012": (0, 4, 228),
}
INHIBITOR_RULES = [f"INH-{n:03d}" for n in range(1, 13)]
NEVER_CALLED = {
    "INH-001": "BEV_TEA_COFFEE: no reviewed mapping, no meal-beverage or timing context, no iron-optimization goal",
    "INH-002": "CMP_PHYTATE: curated compound awaiting citation and reviewer",
    "INH-003": "NUT_CALCIUM / supplement context; do_not_automate",
    "INH-004": "CMP_OXALATE: curated compound awaiting citation and reviewer",
    "INH-008": "MED_ACID_SUPPRESS: medication context; do_not_automate",
    "INH-009": "NUT_ZINC / supplement context; do_not_automate",
    "INH-010": "CMP_FIBER_PHYTATE / supplement context; do_not_automate",
    "INH-011": "no seed recipe has exactly 0 g fat per serving (minimum 0.1 g)",
    "INH-012": "no ingredient is tagged for both BIO-003 and INH-006: tomato carries no NUT_VITC tag",
}


@unittest.skipUnless(DSN and psycopg, "set MAZIMEAL_TEST_DSN to a disposable local database to run these")
class InhibitorDbCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dbguard.assert_local_dsn(DSN)                       # refuse before opening any connection
        cls.conn = psycopg.connect(DSN)
        try:
            dbguard.assert_local_host(cls.conn.info.host)   # and again on the host libpq actually used
        except AssertionError:
            cls.conn.close()
            raise
        have = cls.conn.execute("SELECT to_regclass('rule_code_components') IS NOT NULL, "
                                "(SELECT count(*) FROM business_rules), (SELECT count(*) FROM recipes)").fetchone()
        if not have[0] or have[1] != 54 or have[2] != 400:
            cls.conn.close()
            raise unittest.SkipTest("database is not the loaded repo seed (rules=%s recipes=%s)" % (have[1], have[2]))
        cls.conn.rollback()
        import detect_rules, evaluate_rules, recipe_facts, engine_rules
        cls.detect, cls.ev, cls.rf, cls.ER = detect_rules, evaluate_rules, recipe_facts, engine_rules

    @classmethod
    def tearDownClass(cls):
        cls.conn.rollback()
        cls.conn.close()

    def tearDown(self):
        self.conn.rollback()

    def one(self, sql, params=()):
        return self.conn.execute(sql, params).fetchone()[0]


class TestHostProtection(unittest.TestCase):
    def test_the_guard_runs_before_and_after_connecting(self):
        import inspect
        src = inspect.getsource(InhibitorDbCase.setUpClass.__func__)
        self.assertLess(src.index("dbguard.assert_local_dsn(DSN)"), src.index("psycopg.connect(DSN)"))
        self.assertIn("dbguard.assert_local_host(cls.conn.info.host)", src)


class TestSeedRecipes(InhibitorDbCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ids = [str(r[0]) for r in cls.conn.execute("SELECT recipe_id FROM recipes WHERE deleted_at IS NULL ORDER BY recipe_name")]
        cls.results = {rid: cls.ev.evaluate_recipe_rules(cls.conn, rid) for rid in cls.ids}
        cls.by_rule = collections.defaultdict(dict)
        for rid, res in cls.results.items():
            for r in res:
                cls.by_rule[r.rule_id][rid] = r
        cls.conn.rollback()

    def counts(self, rule):
        c = collections.Counter(str(r.applicability_status) for r in self.by_rule.get(rule, {}).values())
        return (c["APPLICABLE"], c["NOT_APPLICABLE"], c["NEEDS_CONTEXT"])

    def recipes_with_tag(self, code):
        return {str(r[0]) for r in self.conn.execute(
            "SELECT DISTINCT ri.recipe_id FROM recipe_ingredients ri JOIN ingredient_rule_tags t USING (ingredient_id) "
            "WHERE t.rule_code = %s", (code,))}

    # ---- which inhibitor rules are called ----------------------------------------------------
    def test_all_400_recipes_evaluate(self):
        self.assertEqual(len(self.ids), 400)
        self.assertEqual(set(self.results), set(self.ids))

    def test_inh_006_and_inh_007_are_called_exactly_where_their_ingredient_tags_are(self):
        self.assertEqual(set(self.by_rule["INH-006"]), self.recipes_with_tag("NUT_VITC"))
        self.assertEqual(set(self.by_rule["INH-007"]), self.recipes_with_tag("ING_CRUCIFER"))
        self.assertEqual((len(self.by_rule["INH-006"]), len(self.by_rule["INH-007"])), (59, 17))

    def test_the_blocked_rules_are_never_called_and_each_has_a_reason(self):
        for rule, why in NEVER_CALLED.items():
            self.assertEqual(self.by_rule.get(rule, {}), {}, "%s (%s)" % (rule, why))
            self.assertTrue(why)

    def test_inh_005_is_called_exactly_where_the_steps_name_an_egg_white(self):
        named = {str(r[0]) for r in self.conn.execute(
            "SELECT DISTINCT recipe_id FROM recipe_steps WHERE instruction ~* '(^|[^a-z])egg[ -]+whites?([^a-z]|$)'")}
        named |= {str(r[0]) for r in self.conn.execute(
            "SELECT DISTINCT ri.recipe_id FROM recipe_ingredients ri JOIN ingredients i USING (ingredient_id) "
            "WHERE i.ingredient_name ~* '(^|[^a-z])egg[ -]+whites?([^a-z]|$)'")}
        self.assertEqual(set(self.by_rule["INH-005"]), named)
        self.assertEqual(len(named), 4)
        for r in self.by_rule["INH-005"].values():
            self.assertEqual(r.trigger_source, "recipe_process")
            self.assertEqual(r.matched_facts[0].code, "ING_RAW_EGG_WHITE")

    # ---- verdicts -----------------------------------------------------------------------------
    def test_no_inhibitor_rule_is_applicable_without_a_reviewed_definition(self):
        for rule in INHIBITOR_RULES:
            self.assertEqual(self.counts(rule)[0], 0, rule)

    def test_inh_006_and_inh_007_split_between_not_applicable_and_needs_context(self):
        self.assertEqual(self.counts("INH-006"), (0, 4, 55))
        self.assertEqual(self.counts("INH-007"), (0, 1, 16))
        self.assertEqual(self.counts("INH-005"), (0, 0, 4))

    def test_every_not_applicable_names_the_ingredient_the_step_and_why(self):
        n = 0
        for rule in ("INH-006", "INH-007"):
            for rid, r in self.by_rule[rule].items():
                if str(r.applicability_status) != "NOT_APPLICABLE":
                    continue
                n += 1
                self.assertTrue(r.matched_steps and r.matched_ingredients, (rid, rule))
                for ing in r.evidence["ingredients"]:
                    self.assertEqual(ing["verdict"], "NOT_APPLICABLE")
                    m = [x for x in ing["mentions"] if x["role"] in ("raw", "after_cooking", "heated")][0]
                    self.assertTrue(m["instruction_step"] and m["segment"] and ing["reason"], (rid, rule))
        self.assertEqual(n, 5)

    def test_every_needs_context_names_what_is_missing(self):
        known = {"recipe.instructions", "recipe.instructions.ingredient_step", "recipe.instructions.ingredient_treatment",
                 "reviewed_definition.vitamin_c_prolonged_heat", "reviewed_definition.myrosinase_high_heat_methods",
                 "recipe.instructions.mustard_timing", "recipe.instructions.egg_white_state",
                 "meal_history.raw_egg_white_frequency"}
        for rule in ("INH-005", "INH-006", "INH-007"):
            for rid, r in self.by_rule[rule].items():
                if str(r.applicability_status) == "NEEDS_CONTEXT":
                    self.assertTrue(r.missing_context, (rid, rule))
                    for m in r.missing_context:
                        self.assertIn(m["field"], known, (rid, rule))
                        self.assertTrue(m["reason"])

    def test_every_inhibitor_result_has_the_full_structured_evidence(self):
        for rule in ("INH-005", "INH-006", "INH-007"):
            for rid, r in self.by_rule[rule].items():
                d = r.as_dict()
                json.dumps(d, default=str)                                   # serialisable
                self.assertTrue(d["trigger_source"] and d["reason"], (rid, rule))
                self.assertTrue(d["matched_on"]["facts"], (rid, rule))
                self.assertIn("evidence", d)
                if rule != "INH-005":
                    self.assertEqual(d["trigger_source"], "ingredient")
                    self.assertTrue(d["matched_on"]["ingredients"], (rid, rule))
                    self.assertTrue(d["evidence"]["ingredients"])
                    self.assertIn("aggregation", d["evidence"])

    def test_aggregation_is_auditable_from_the_per_ingredient_evidence(self):
        for rule in ("INH-006", "INH-007"):
            for rid, r in self.by_rule[rule].items():
                verdicts = [i["verdict"] for i in r.evidence["ingredients"]]
                want = ("APPLICABLE" if "APPLICABLE" in verdicts else
                        "NEEDS_CONTEXT" if "NEEDS_CONTEXT" in verdicts else "NOT_APPLICABLE")
                self.assertEqual(str(r.applicability_status), want, (rid, rule))

    def test_unreviewed_definitions_are_visible_in_the_evidence(self):
        any_heated = False
        for r in self.by_rule["INH-006"].values():
            self.assertEqual(r.evidence["prolonged_heat_definition"]["review_status"], "unset")
            any_heated = any_heated or any(i["state"] == "heated" for i in r.evidence["ingredients"])
        for r in self.by_rule["INH-007"].values():
            self.assertEqual(r.evidence["high_heat_definition"]["review_status"], "unreviewed")
        self.assertTrue(any_heated)

    # ---- INH-012 ------------------------------------------------------------------------------
    def test_inh_012_falls_from_20_false_candidates_to_zero(self):
        bio003, inh006 = set(self.by_rule["BIO-003"]), set(self.by_rule["INH-006"])
        self.assertEqual(len(bio003 & inh006), 20)               # what the old rule fired on: co-occurrence
        self.assertEqual(self.by_rule.get("INH-012", {}), {})
        self.assertEqual(self.one("SELECT count(*) FROM ingredient_rule_tags t JOIN ingredients i USING (ingredient_id) "
                                  "WHERE t.rule_code = 'NUT_VITC' AND i.ingredient_name ~* 'tomato'"), 0)

    def test_none_of_the_20_co_occurrences_shares_an_ingredient(self):
        for rid in set(self.by_rule["BIO-003"]) & set(self.by_rule["INH-006"]):
            a, b = self.by_rule["BIO-003"][rid], self.by_rule["INH-006"][rid]
            self.assertEqual(self.ER.shared_ingredients(a, b), [], rid)

    def test_it_would_fire_for_the_same_tomato_when_a_reviewed_tag_exists(self):
        """Not a mapping change: a rolled-back what-if showing the shared-ingredient path works on real data."""
        self.conn.execute("INSERT INTO ingredient_rule_tags (ingredient_id, rule_code) SELECT ingredient_id, 'NUT_VITC' "
                          "FROM ingredients WHERE ingredient_name = 'tomatoes' ON CONFLICT DO NOTHING")
        fired = {}
        for rid in self.by_rule["BIO-003"]:
            for r in self.ev.evaluate_recipe_rules(self.conn, rid):
                if r.rule_id == "INH-012":
                    fired[rid] = r
        self.assertTrue(fired)
        for r in fired.values():
            self.assertEqual({i["key"] for i in r.evidence["pairs"][0]["shared_ingredients"]}, {"tomato"})
            self.assertEqual(r.evidence["suppressed_rules"], [])
        self.conn.rollback()
        for rid in fired:
            self.assertNotIn("INH-012", {r.rule_id for r in self.ev.evaluate_recipe_rules(self.conn, rid)})

    # ---- regressions --------------------------------------------------------------------------
    def test_every_pre_existing_evaluator_has_exactly_its_old_verdict_counts(self):
        for rule, want in PRE_EXISTING.items():
            self.assertEqual(self.counts(rule), want, rule)
        self.assertEqual(set(PRE_EXISTING) & {"INH-005", "INH-006", "INH-007", "INH-012"}, set())

    def test_no_pre_existing_rule_gained_or_lost_a_candidate(self):
        seen = {r for r in self.by_rule} - {"INH-005", "INH-006", "INH-007", "INH-012"}
        self.assertEqual(seen, set(PRE_EXISTING))

    def test_ingredient_tag_counts_are_unchanged(self):
        self.assertEqual(self.one("SELECT count(*) FROM ingredient_rule_tags"), 306)
        for code, want in (("NUT_VITC", 33), ("ING_CRUCIFER", 11), ("ING_EGG", 3)):
            self.assertEqual(self.one("SELECT count(DISTINCT ingredient_id) FROM ingredient_rule_tags WHERE rule_code=%s", (code,)), want, code)
        for code in ("BEV_TEA_COFFEE", "CMP_PHYTATE", "CMP_OXALATE", "ING_RAW_EGG_WHITE", "NUT_CALCIUM", "NUT_ZINC",
                     "CMP_FIBER_PHYTATE", "MED_ACID_SUPPRESS", "RULE_CONFLICT"):
            self.assertEqual(self.one("SELECT count(*) FROM ingredient_rule_tags WHERE rule_code=%s", (code,)), 0, code)

    def test_the_old_response_fields_are_all_still_present(self):
        for rid in self.ids[:40]:
            for r in self.results[rid]:
                d = r.as_dict()
                for k in ("rule_id", "rule_name", "rule_category", "rule_type", "automation_status", "evidence_tier",
                          "applicability_status", "candidate", "trigger_code", "target_code", "action", "conditions_checked",
                          "conditions_passed", "conditions_failed", "matched_on", "reason", "source_title", "source_url"):
                    self.assertIn(k, d)
                self.assertTrue({"ingredients", "steps"} <= set(d["matched_on"]))

    def test_evaluation_writes_nothing(self):
        before = self.one("SELECT (SELECT count(*) FROM ingredient_rule_tags) + (SELECT count(*) FROM recipe_equipment)")
        for rid in self.ids[:15]:
            self.ev.evaluate_recipe_rules(self.conn, rid)
        self.assertEqual(self.one("SELECT (SELECT count(*) FROM ingredient_rule_tags) + (SELECT count(*) FROM recipe_equipment)"), before)


class TestContextOnRealSchema(InhibitorDbCase):
    """Member context for the medication/supplement rules, on the real households schema."""

    def setUp(self):
        import member_context
        from evaluation_context import EvaluationContext
        self.MC, self.Ctx = member_context, EvaluationContext
        self.owner, self.other = str(uuid.uuid4()), str(uuid.uuid4())
        hh = self.one("INSERT INTO households (created_by_user_id) VALUES (%s) RETURNING household_id", (self.owner,))
        self.member = str(self.one("INSERT INTO household_members (household_id, member_name) VALUES (%s, 'zz') RETURNING member_id", (hh,)))
        self.bare = str(self.one("INSERT INTO household_members (household_id, member_name) VALUES (%s, 'bare') RETURNING member_id", (hh,)))
        self.conn.execute("INSERT INTO member_conditions (member_id, condition_type, value_text) VALUES "
                          "(%s, 'medication', 'Secret Medication'), (%s, 'supplement', 'Secret Supplement')",
                          (self.member, self.member))

    def advisory(self, ctx):
        import inhibitor_rules as IR, detect_rules
        cand = detect_rules.DetectedRule(rule_id="INH-008", rule_name="x", automation_status="do_not_automate",
                                         trigger_code="MED_ACID_SUPPRESS", reason="c", action="Flag for clinician review")
        facts = self.rf.build_recipe_facts(self.conn, str(self.one("SELECT recipe_id FROM recipes LIMIT 1")))
        return self.ev.evaluate_rule(cand, facts, self.ev.extract_process_facts(facts), ctx)

    def test_omitted_context_is_not_the_same_as_an_empty_or_a_provided_one(self):
        owner_ctx = self.MC.load_member_context(self.conn, self.member, self.owner)
        bare_ctx = self.MC.load_member_context(self.conn, self.bare, self.owner)
        self.assertEqual(self.advisory(owner_ctx).evidence["member_context"], {"medications": "provided", "supplements": "provided"})
        self.assertEqual(self.advisory(bare_ctx).evidence["member_context"], {"medications": "omitted", "supplements": "omitted"})
        stated_empty = self.Ctx(member_id=self.bare, medications=(), supplements=())
        self.assertEqual(self.advisory(stated_empty).evidence["member_context"], {"medications": "empty", "supplements": "empty"})

    def test_a_loaded_medication_list_never_reaches_the_result(self):
        r = self.advisory(self.MC.load_member_context(self.conn, self.member, self.owner))
        self.assertNotIn("secret", str(r.as_dict()).lower())
        self.assertEqual(str(r.applicability_status), "NEEDS_CONTEXT")

    def test_another_account_cannot_load_the_member(self):
        with self.assertRaises(self.MC.MemberAccessDenied):
            self.MC.load_member_context(self.conn, self.member, self.other)

    def test_matching_and_nonmatching_member_data_give_the_same_manual_verdict(self):
        mine = self.advisory(self.MC.load_member_context(self.conn, self.member, self.owner))
        theirs = self.advisory(self.Ctx(member_id="x", medications=("something else",), supplements=()))
        self.assertEqual((mine.applicability_status, mine.missing_context), (theirs.applicability_status, theirs.missing_context))


if __name__ == "__main__":
    unittest.main()
