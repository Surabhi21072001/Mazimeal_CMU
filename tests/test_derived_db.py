#!/usr/bin/env python3
"""PostgreSQL tests for fact-driven rules: all 400 seed recipes, the real schema, authorization.

These run ONLY against a disposable local database loaded from the repository
(tests/load_local_db.sh), and skip otherwise:

    tests/load_local_db.sh mazi_derived_audit
    MAZIMEAL_TEST_DSN="postgresql:///mazi_derived_audit?host=/tmp" \\
        python3 -m unittest tests.test_derived_db -v

Safety: tests/dbguard.py refuses any non-local host before and after connecting. Every write a
test makes (households, members, synthetic recipes, reviews) happens in a transaction that is
rolled back, so the database is left as it was.
"""
from __future__ import annotations

import collections
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

# Trigger codes that are NEVER ingredient tags: derived from nutrition, process, meal,
# equipment or engine results.
DERIVED_TRIGGER_CODES = ("MACRO_CARB", "MACRO_AVAIL_CARB", "MACRO_FAT_LOW", "MEAL_MIXED", "BEH_POSTMEAL",
                         "PROC_COOL_REHEAT", "PROC_COOKWARE", "RULE_CONFLICT")
LEGACY = ("BIO-002", "BIO-003", "BIO-007", "BIO-011", "GLY-007")


@unittest.skipUnless(DSN and psycopg, "set MAZIMEAL_TEST_DSN to a disposable local database to run these")
class DerivedDbCase(unittest.TestCase):
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
        import detect_rules, evaluate_rules, recipe_facts
        cls.detect, cls.ev, cls.rf = detect_rules, evaluate_rules, recipe_facts

    @classmethod
    def tearDownClass(cls):
        cls.conn.rollback()
        cls.conn.close()

    def tearDown(self):
        self.conn.rollback()

    def one(self, sql, params=()):
        return self.conn.execute(sql, params).fetchone()[0]


# ======================================================================================
# Protection
# ======================================================================================
class TestDatabaseHostProtection(unittest.TestCase):
    def test_the_case_runs_the_guard_before_and_after_connecting(self):
        import inspect
        src = inspect.getsource(DerivedDbCase.setUpClass.__func__)
        self.assertLess(src.index("dbguard.assert_local_dsn(DSN)"), src.index("psycopg.connect(DSN)"))
        self.assertIn("dbguard.assert_local_host(cls.conn.info.host)", src)

    def test_hosted_and_remote_dsns_are_refused_before_any_connection(self):
        hosted = "super" + "base"                      # built here so no hosted name appears in this file
        for dsn in ("postgresql://u:x@db.abcdefghijkl.%s.co:5432/postgres" % hosted,
                    "postgresql://u@aws-0-us-east-1.pooler.%s.com:6543/postgres" % hosted,
                    "postgresql://u@10.0.0.9/db", "host=staging.example.com dbname=x"):
            with self.assertRaises(AssertionError, msg=dsn):
                dbguard.assert_local_dsn(dsn)

    def test_a_local_dsn_is_accepted(self):
        for dsn in ("postgresql:///x?host=/tmp", "postgresql://u@127.0.0.1:5432/x", "host=localhost dbname=x"):
            dbguard.assert_local_dsn(dsn)

    def test_the_scratch_loader_refuses_non_local_hosts(self):
        text = (REPO / "tests" / "load_local_db.sh").read_text()
        self.assertIn("refusing non-local host", text)
        self.assertIn("refusing to modify it", text)


# ======================================================================================
# All 400 recipes
# ======================================================================================
class TestAllSeedRecipes(DerivedDbCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ids = [str(r[0]) for r in cls.conn.execute(
            "SELECT recipe_id FROM recipes WHERE deleted_at IS NULL ORDER BY recipe_name")]
        cls.facts = {rid: cls.rf.build_recipe_facts(cls.conn, rid) for rid in cls.ids}
        cls.results = {rid: cls.ev.evaluate_all_rules(cls.conn, cls.facts[rid]) for rid in cls.ids}
        cls.by_rule = collections.defaultdict(dict)
        for rid, res in cls.results.items():
            for r in res:
                cls.by_rule[r.rule_id][rid] = r
        cls.conn.rollback()

    def test_there_are_400_recipes_and_every_one_evaluates(self):
        self.assertEqual(len(self.ids), 400)
        self.assertEqual(set(self.results), set(self.ids))

    def test_one_result_per_rule_per_recipe(self):
        for rid, res in self.results.items():
            ids = [r.rule_id for r in res]
            self.assertEqual(len(ids), len(set(ids)), rid)

    def test_every_result_has_a_trigger_source_facts_and_a_known_status(self):
        for rid, res in self.results.items():
            for r in res:
                self.assertIn(str(r.applicability_status), ("APPLICABLE", "NOT_APPLICABLE", "NEEDS_CONTEXT"))
                self.assertTrue(r.trigger_source, (rid, r.rule_id))
                self.assertTrue(r.matched_facts, (rid, r.rule_id))

    def test_every_needs_context_result_says_exactly_what_is_missing(self):
        for rid, res in self.results.items():
            for r in res:
                if str(r.applicability_status) == "NEEDS_CONTEXT":
                    self.assertTrue(r.missing_context, (rid, r.rule_id, r.reason))
                    for m in r.missing_context:
                        self.assertTrue(m["field"] and m["reason"], (rid, r.rule_id))

    def test_no_derived_trigger_code_is_an_ingredient_tag(self):
        n = self.one("SELECT count(*) FROM ingredient_rule_tags WHERE rule_code = ANY(%s)",
                     (list(DERIVED_TRIGGER_CODES),))
        self.assertEqual(n, 0)

    # ---- nutrition-derived triggers ----------------------------------------------------
    def nutrient(self, rid, nid):
        return self.facts[rid].nutrients.get(nid)

    def test_macro_carb_rules_are_called_exactly_for_recipes_with_carbohydrate(self):
        for rule in ("GLY-002", "GLY-003", "GLY-004", "GLY-009"):
            expected = {rid for rid in self.ids if (self.nutrient(rid, "Macro_Carbohydrate") or 0) > 0}
            self.assertEqual(set(self.by_rule[rule]), expected, rule)
        self.assertEqual(len(self.by_rule["GLY-002"]), 397)

    def test_every_recipe_has_the_nutrients_the_rules_read(self):
        for rid in self.ids:
            for nid in ("Macro_Carbohydrate", "Macro_Protein", "Macro_Fat", "Fiber"):
                self.assertIn(nid, self.facts[rid].nutrients, (rid, nid))
            self.assertEqual(self.facts[rid].metadata["nutrition_basis"], "per_serving")

    def test_fat_free_is_read_literally_so_no_seed_recipe_calls_inh_011(self):
        self.assertEqual(min(self.nutrient(rid, "Macro_Fat") for rid in self.ids) > 0, True)
        self.assertEqual(self.by_rule.get("INH-011", {}), {})

    def test_gly_002_never_needs_context_on_the_seed(self):
        statuses = collections.Counter(str(r.applicability_status) for r in self.by_rule["GLY-002"].values())
        self.assertEqual(statuses["NEEDS_CONTEXT"], 0)
        self.assertGreater(statuses["APPLICABLE"], 0)
        self.assertGreater(statuses["NOT_APPLICABLE"], 0)

    def test_dominant_and_rich_rules_never_claim_applicable_without_a_reviewed_definition(self):
        for rule in ("GLY-003", "GLY-004", "GLY-009"):
            statuses = {str(r.applicability_status) for r in self.by_rule[rule].values()}
            self.assertNotIn("APPLICABLE", statuses, rule)

    def test_threshold_value_unit_and_basis_are_in_the_evidence(self):
        r = next(iter(self.by_rule["GLY-002"].values()))
        crit = r.evidence["carbohydrate"]["criterion"]
        reading = r.evidence["carbohydrate"]["reading"]
        self.assertEqual((crit["threshold"], crit["operator"], crit["unit"], crit["basis"]), (0.0, ">", "g", "per_serving"))
        self.assertEqual((reading["unit"], reading["basis"]), ("g", "per_serving"))

    # ---- GLY-015 -----------------------------------------------------------------------
    def test_gly_015_is_called_only_where_a_starch_step_cools_or_reheats(self):
        for rid, r in self.by_rule["GLY-015"].items():
            self.assertEqual(r.trigger_source, "recipe_process")
            self.assertTrue(r.matched_steps, rid)
            roles = {f.value["role"] for f in r.matched_facts}
            self.assertTrue(roles & {"cooling", "refrigeration", "reheating"})
            for f in r.matched_facts:
                self.assertIsNotNone(f.value["instruction_step"])
        called = set(self.by_rule["GLY-015"])
        for rid in self.ids:
            if rid not in called:
                self.assertEqual(self.ev.DF.process_cool_reheat_facts(self.facts[rid]), [], rid)

    # ---- meal rules --------------------------------------------------------------------
    def test_anonymous_evaluation_never_calls_the_post_meal_rule(self):
        self.assertEqual(self.by_rule.get("GLY-010", {}), {})

    def test_gly_005_without_a_sequence_is_always_needs_context_anonymous(self):
        for r in self.by_rule["GLY-005"].values():
            self.assertEqual(str(r.applicability_status), "NEEDS_CONTEXT")
            self.assertEqual(r.missing_context[0]["field"], "meal_context.eating_sequence")

    def test_gly_011_names_every_missing_input_for_every_recipe(self):
        for r in self.by_rule["GLY-011"].values():
            self.assertEqual(str(r.applicability_status), "NEEDS_CONTEXT")
            fields = [m["field"] for m in r.missing_context]
            self.assertEqual(fields, ["reviewed_definition.high_carbohydrate_serving",
                                      "meal_context.intended_portions", "user_context.goals",
                                      "user_context.conditions"])

    # ---- existing evaluators -----------------------------------------------------------
    def test_the_five_original_evaluators_give_identical_results_with_and_without_derived_facts(self):
        for rid in self.ids[::5]:                        # every fifth recipe: same code path, faster
            facts = self.facts[rid]
            pf = self.ev.extract_process_facts(facts)
            old = {}
            for cand in self.detect.detect_rules_from_facts(self.conn, facts, include_derived=False):
                if cand.rule_id in LEGACY:
                    r = self.ev.evaluate_rule(cand, facts, pf)
                    old[cand.rule_id] = (str(r.applicability_status), r.reason, r.conditions_checked,
                                         r.conditions_passed, r.conditions_failed)
            new = {r.rule_id: (str(r.applicability_status), r.reason, r.conditions_checked,
                               r.conditions_passed, r.conditions_failed)
                   for r in self.results[rid] if r.rule_id in LEGACY}
            self.assertEqual(old, new, rid)

    def test_candidates_by_ingredient_alone_are_unchanged(self):
        for rid in self.ids[::7]:
            only_ing = {c.rule_id for c in self.detect.detect_rules_from_facts(
                self.conn, self.facts[rid], include_derived=False)}
            derived_codes = {c.rule_id for c in self.detect.detect_rules_from_facts(self.conn, self.facts[rid])
                             if c.trigger_source and "ingredient" not in c.trigger_source}
            self.assertEqual(only_ing & derived_codes, set(), rid)

    def test_evaluation_writes_nothing(self):
        tables = ("ingredient_rule_tags", "business_rules", "recipe_nutrition", "recipe_steps", "rule_codes")
        before = {t: self.one("SELECT count(*) FROM %s" % t) for t in tables}
        for rid in self.ids[:20]:
            self.ev.evaluate_all_rules(self.conn, self.rf.build_recipe_facts(self.conn, rid))
        self.assertEqual({t: self.one("SELECT count(*) FROM %s" % t) for t in tables}, before)


# ======================================================================================
# Nutrition verification (the data-readiness layer)
# ======================================================================================
class TestNutritionReviews(DerivedDbCase):
    def pick(self):
        return str(self.one("SELECT recipe_id FROM recipes r WHERE EXISTS (SELECT 1 FROM recipe_nutrition n "
                            "WHERE n.recipe_id = r.recipe_id AND n.nutrient_id='Macro_Carbohydrate' AND n.per_serving > 0) "
                            "ORDER BY recipe_name LIMIT 1"))

    def review(self, rid, verdict, reason="because"):
        self.conn.execute("INSERT INTO recipe_nutrition_reviews (recipe_id, verdict, reason, reviewer) "
                          "VALUES (%s, %s, %s, 'test@example.com')", (rid, verdict, reason))

    def status(self, rid, rule="GLY-002"):
        return {r.rule_id: r for r in self.ev.evaluate_recipe_rules(self.conn, rid)}[rule]

    def test_unreviewed_nutrition_is_used_and_says_so(self):
        r = self.status(self.pick())
        self.assertEqual(r.evidence["carbohydrate"]["reading"]["verification"], "unreviewed")

    def test_an_implausible_verdict_stops_the_rule_with_needs_context(self):
        rid = self.pick()
        self.review(rid, "implausible")
        r = self.status(rid)
        self.assertEqual(str(r.applicability_status), "NEEDS_CONTEXT")
        self.assertTrue(r.missing_context[0]["field"].endswith(".verification"))
        self.assertEqual(r.matched_facts[0].confidence, "unknown")

    def test_needs_data_also_stops_it(self):
        rid = self.pick()
        self.review(rid, "needs_data", "numbers cannot be judged yet")
        self.assertEqual(str(self.status(rid).applicability_status), "NEEDS_CONTEXT")

    def test_the_newest_verdict_wins(self):
        rid = self.pick()
        self.review(rid, "implausible")
        self.conn.execute("INSERT INTO recipe_nutrition_reviews (recipe_id, verdict, reviewer, reviewed_at) "
                          "VALUES (%s, 'plausible', 'b@example.com', now() + interval '1 minute')", (rid,))
        r = self.status(rid)
        self.assertNotEqual(str(r.applicability_status), "NEEDS_CONTEXT")
        self.assertEqual(r.matched_facts[0].confidence, "high")


# ======================================================================================
# Authorization against the real schema
# ======================================================================================
class TestMemberAuthorization(DerivedDbCase):
    def setUp(self):
        import member_context
        self.MC = member_context
        self.owner, self.other = str(uuid.uuid4()), str(uuid.uuid4())
        self.household = self.one("INSERT INTO households (created_by_user_id, household_name) "
                                  "VALUES (%s, 'zz test') RETURNING household_id", (self.owner,))
        self.member = self.member_in(self.household, goal="maintenance", activity="moderate")
        self.conn.execute("INSERT INTO member_conditions (member_id, condition_type, condition_code, value_text) "
                          "VALUES (%s, 'condition', NULL, 'Iron Overload'), (%s, 'medication', NULL, 'Warfarin')",
                          (self.member, self.member))

    def member_in(self, household, goal=None, activity=None):
        return self.one("INSERT INTO household_members (household_id, member_name, goal, activity_level) "
                        "VALUES (%s, 'zz', %s, %s) RETURNING member_id", (household, goal, activity))

    def test_the_owner_loads_their_member(self):
        c = self.MC.load_member_context(self.conn, str(self.member), self.owner)
        self.assertEqual((c.conditions, c.medications, c.goals, c.activity_level),
                         (("iron_overload",), ("warfarin",), ("maintenance",), "moderate"))

    def test_another_account_is_denied(self):
        with self.assertRaises(self.MC.MemberAccessDenied):
            self.MC.load_member_context(self.conn, str(self.member), self.other)

    def test_unknown_and_malformed_ids_are_denied_the_same_way(self):
        for member in (str(uuid.uuid4()), "not-a-uuid", "' OR 1=1 --"):
            with self.assertRaises(self.MC.MemberAccessDenied):
                self.MC.load_member_context(self.conn, member, self.owner)
        with self.assertRaises(self.MC.MemberAccessDenied):
            self.MC.load_member_context(self.conn, str(self.member), "not-a-uuid")
        self.conn.execute("SELECT 1")                      # the connection is still usable after a malformed id

    def test_a_soft_deleted_member_or_household_is_denied(self):
        self.conn.execute("UPDATE household_members SET deleted_at = now() WHERE member_id = %s", (self.member,))
        with self.assertRaises(self.MC.MemberAccessDenied):
            self.MC.load_member_context(self.conn, str(self.member), self.owner)
        other_hh = self.one("INSERT INTO households (created_by_user_id, deleted_at) VALUES (%s, now()) "
                            "RETURNING household_id", (self.owner,))
        gone = self.member_in(other_hh)
        with self.assertRaises(self.MC.MemberAccessDenied):
            self.MC.load_member_context(self.conn, str(gone), self.owner)

    def test_allergies_are_not_conditions(self):
        self.conn.execute("INSERT INTO member_conditions (member_id, condition_type, value_text) "
                          "VALUES (%s, 'allergy', 'peanut')", (self.member,))
        c = self.MC.load_member_context(self.conn, str(self.member), self.owner)
        self.assertNotIn("peanut", c.conditions)

    def test_a_member_with_no_rows_has_unknown_conditions_not_none(self):
        bare = self.member_in(self.household)
        c = self.MC.load_member_context(self.conn, str(bare), self.owner)
        self.assertIsNone(c.conditions)
        self.assertIsNone(c.medications)

    def test_a_loaded_context_can_change_a_verdict_end_to_end(self):
        rid = str(self.one("SELECT recipe_id FROM recipes ORDER BY recipe_name LIMIT 1"))
        mine = self.MC.load_member_context(self.conn, str(self.member), self.owner)
        res = {r.rule_id: r for r in self.ev.evaluate_recipe_rules(self.conn, rid, mine)}
        self.assertNotIn("user_context.conditions", [m["field"] for r in res.values() for m in r.missing_context])
        bare = self.member_in(self.household)
        unknown = self.MC.load_member_context(self.conn, str(bare), self.owner)
        res = {r.rule_id: r for r in self.ev.evaluate_recipe_rules(self.conn, rid, unknown)}
        self.assertIn("user_context.conditions", [m["field"] for r in res.values() for m in r.missing_context])

    def test_loading_a_member_writes_nothing(self):
        before = self.one("SELECT count(*) FROM member_conditions")
        self.MC.load_member_context(self.conn, str(self.member), self.owner)
        self.assertEqual(self.one("SELECT count(*) FROM member_conditions"), before)


MIGRATIONS = REPO / "schema" / "migrations"
EQUIP_CODES = {"EQUIP_CAST_IRON", "EQUIP_ENAMELED_CAST_IRON", "EQUIP_DUTCH_OVEN",
               "EQUIP_NONIRON_COOKWARE", "EQUIP_COOKWARE_UNSPECIFIED"}


def strip_transaction(sql: str) -> str:
    """A migration owns its BEGIN/COMMIT. Inside a test transaction we need neither."""
    import re
    return re.sub(r"^(BEGIN|COMMIT);\s*$", "", sql, flags=re.M)


class TestMigration013(DerivedDbCase):
    """013_recipe_equipment.sql. Every run happens inside a transaction that is rolled back."""

    def run_013(self):
        self.conn.execute(strip_transaction((MIGRATIONS / "013_recipe_equipment.sql").read_text()))

    def a_recipe(self):
        return self.one("SELECT recipe_id FROM recipes ORDER BY recipe_name LIMIT 1")

    def test_numbering_follows_the_existing_migrations_with_no_gap_or_duplicate(self):
        numbers = sorted(int(p.name[:3]) for p in MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql"))
        self.assertEqual(numbers, list(range(1, 14)))

    def test_it_is_idempotent(self):
        before = self.one("SELECT count(*) FROM rule_codes")
        self.run_013()
        self.run_013()
        self.assertEqual(self.one("SELECT count(*) FROM rule_codes"), before)
        got = {r[0] for r in self.conn.execute("SELECT code FROM rule_codes WHERE code LIKE 'EQUIP\\_%'")}
        self.assertEqual(got, EQUIP_CODES)

    def test_it_changes_no_existing_row(self):
        tables = ("ingredient_rule_tags", "business_rules", "recipes", "recipe_steps", "recipe_nutrition")
        before = {t: self.one("SELECT count(*) FROM %s" % t) for t in tables}
        self.run_013()
        self.assertEqual({t: self.one("SELECT count(*) FROM %s" % t) for t in tables}, before)

    def test_row_level_security_is_on_with_no_policy(self):
        self.assertTrue(self.one("SELECT relrowsecurity FROM pg_class WHERE oid = 'public.recipe_equipment'::regclass"))
        self.assertEqual(self.one("SELECT count(*) FROM pg_policies WHERE tablename = 'recipe_equipment'"), 0)

    def insert(self, **kw):
        row = dict(recipe_id=self.a_recipe(), equipment_code="EQUIP_CAST_IRON", source="structured",
                   confidence="high", review_status="auto")
        row.update(kw)
        cols = ", ".join(row)
        self.conn.execute("INSERT INTO recipe_equipment (%s) VALUES (%s)" % (cols, ", ".join(["%s"] * len(row))),
                          tuple(row.values()))

    def test_constraints_reject_bad_rows(self):
        bad = [dict(source="guess"), dict(confidence="certain"), dict(review_status="maybe"),
               dict(evidence_step=0), dict(review_status="confirmed"),            # decision with no reviewer
               dict(equipment_code="ING_GARLIC")]                                  # not an equipment code
        for kw in bad:
            with self.assertRaises(psycopg.errors.IntegrityError, msg=str(kw)):
                self.insert(**kw)
            self.conn.rollback()

    def test_an_unknown_code_or_recipe_is_rejected(self):
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            self.insert(equipment_code="EQUIP_MADE_UP")
        self.conn.rollback()
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            self.insert(recipe_id=str(uuid.uuid4()))

    def test_a_decision_needs_a_reviewer_and_a_time(self):
        self.insert(review_status="confirmed", reviewed_by="a@example.com", reviewed_at="2026-01-01")
        self.assertEqual(self.one("SELECT count(*) FROM recipe_equipment"), 1)

    def test_one_row_per_recipe_code_and_source_and_deleting_the_recipe_removes_it(self):
        self.insert()
        with self.assertRaises(psycopg.errors.UniqueViolation):
            self.insert()
        self.conn.rollback()
        self.insert()
        self.conn.execute("DELETE FROM recipes WHERE recipe_id = %s", (self.a_recipe(),))
        self.assertEqual(self.one("SELECT count(*) FROM recipe_equipment"), 0)

    def test_stored_equipment_reaches_recipe_facts(self):
        rid = self.a_recipe()
        self.insert(recipe_id=rid, evidence_step=2, evidence_text="Heat the cast iron pan.")
        f = self.rf.build_recipe_facts(self.conn, str(rid))
        self.assertEqual([(e.equipment_code, e.source, e.evidence_step) for e in f.equipment],
                         [("EQUIP_CAST_IRON", "structured", 2)])

    def test_a_recipe_with_nothing_stored_has_no_equipment(self):
        self.assertEqual(self.rf.build_recipe_facts(self.conn, str(self.a_recipe())).equipment, ())

    def test_a_reviewer_rejection_changes_the_verdict_end_to_end(self):
        # Find a seed recipe whose steps name a cast iron vessel (if any), else make one.
        rid = self.one("INSERT INTO recipes (recipe_name, meal_category) VALUES ('zz equipment test', 'Dinner') RETURNING recipe_id")
        self.conn.execute("INSERT INTO recipe_steps (recipe_id, step_number, instruction) VALUES (%s, 1, 'Simmer in a cast iron skillet.')", (rid,))

        def syn012():
            return {r.rule_id: r for r in self.ev.evaluate_recipe_rules(self.conn, str(rid))}["SYN-012"]
        self.assertEqual(str(syn012().applicability_status), "NOT_APPLICABLE")
        self.conn.execute("INSERT INTO recipe_equipment (recipe_id, equipment_code, source, confidence, review_status, "
                          "reviewed_by, reviewed_at) VALUES (%s, 'EQUIP_CAST_IRON', 'admin_review', 'high', 'rejected', "
                          "'r@example.com', now())", (rid,))
        # The only cookware fact was the one the reviewer rejected, so the rule is no longer called.
        self.assertNotIn("SYN-012", {r.rule_id for r in self.ev.evaluate_recipe_rules(self.conn, str(rid))})
        # With other cookware stated it IS called, and cast iron no longer counts as used.
        self.conn.execute("INSERT INTO recipe_steps (recipe_id, step_number, instruction) VALUES (%s, 2, 'Add a pot of water.')", (rid,))
        self.assertEqual(str(syn012().applicability_status), "NEEDS_CONTEXT")


class TestInh012OnSeed(DerivedDbCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import engine_rules
        cls.ER = engine_rules
        cls.rows = []
        for (rid,) in cls.conn.execute("SELECT recipe_id FROM recipes WHERE deleted_at IS NULL").fetchall():
            facts = cls.rf.build_recipe_facts(cls.conn, str(rid))
            primary = cls.ev.evaluate_primary_rules(cls.conn, facts)
            cls.rows.append((str(rid), facts, primary, cls.ER.evaluate_engine_rules(cls.conn, facts, None, primary)))
        cls.conn.rollback()

    def test_it_is_called_exactly_when_both_members_of_the_pair_are_candidates(self):
        for rid, facts, primary, engine in self.rows:
            ids = {r.rule_id for r in primary}
            self.assertEqual(bool(engine), {"BIO-003", "INH-006"} <= ids, rid)
        self.assertGreater(sum(1 for *_, e in self.rows if e), 0)

    def test_the_verdict_follows_the_two_primary_results(self):
        for rid, facts, primary, engine in self.rows:
            if not engine:
                continue
            by = {r.rule_id: str(r.applicability_status) for r in primary}
            a, b = by["BIO-003"], by["INH-006"]
            want = ("NOT_APPLICABLE" if "NOT_APPLICABLE" in (a, b)
                    else "APPLICABLE" if (a, b) == ("APPLICABLE", "APPLICABLE") else "NEEDS_CONTEXT")
            self.assertEqual(str(engine[0].applicability_status), want, rid)
            if want == "NEEDS_CONTEXT":
                self.assertTrue(engine[0].missing_context, rid)
                self.assertTrue(all(m["field"].startswith("primary_results.") for m in engine[0].missing_context))

    def test_it_never_suppresses_or_reorders_a_primary_result(self):
        for rid, facts, primary, engine in self.rows:
            again = self.ev.evaluate_primary_rules(self.conn, facts)
            full = self.ev.evaluate_all_rules(self.conn, facts)
            self.assertEqual(again, primary, rid)
            self.assertEqual(full[:len(primary)], primary, rid)
            for e in engine:
                self.assertEqual((e.evidence["suppressed_rules"], e.evidence["priority_changes"]), ([], []))

    def test_primary_detection_never_returns_it(self):
        for rid, facts, primary, engine in self.rows[::13]:
            self.assertNotIn("INH-012", {c.rule_id for c in self.detect.detect_rules_from_facts(self.conn, facts)})
            self.assertNotIn("INH-012", {r.rule_id for r in primary})

    def test_it_records_the_primary_results_that_caused_it(self):
        for rid, facts, primary, engine in self.rows:
            for e in engine:
                self.assertEqual({t["rule_id"] for t in e.evidence["triggered_by"]}, {"BIO-003", "INH-006"})


class TestSyn012OnSeed(DerivedDbCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import equipment_facts
        cls.EQ = equipment_facts
        cls.rows = []
        for (rid,) in cls.conn.execute("SELECT recipe_id FROM recipes WHERE deleted_at IS NULL").fetchall():
            facts = cls.rf.build_recipe_facts(cls.conn, str(rid))
            cls.rows.append((str(rid), facts, cls.EQ.equipment_candidate_facts(facts)))
        cls.conn.rollback()

    def test_the_rule_is_called_exactly_for_recipes_whose_steps_name_cookware(self):
        called = {rid for rid, facts, eq in self.rows if eq}
        for rid, facts, eq in self.rows[::9]:
            ids = {c.rule_id for c in self.detect.detect_rules_from_facts(self.conn, facts)}
            self.assertEqual("SYN-012" in ids, rid in called, rid)
        self.assertGreater(len(called), 0)

    def test_equipment_is_never_read_from_ingredient_names(self):
        for rid, facts, eq in self.rows:
            for f in eq:
                self.assertEqual(f.value["equipment_source"], "instruction_extraction")
                self.assertIsNotNone(f.value["instruction_step"], rid)
                self.assertTrue(f.evidence, rid)

    def test_every_verdict_is_a_decision_the_rule_text_supports(self):
        seen = set()
        for rid, facts, eq in self.rows:
            if not eq:
                continue
            r = {x.rule_id: x for x in self.ev.evaluate_primary_rules(self.conn, facts)}["SYN-012"]
            seen.add(str(r.applicability_status))
            if str(r.applicability_status) == "NEEDS_CONTEXT":
                self.assertIn("recipe.dish_acidity_and_moisture", [m["field"] for m in r.missing_context])
        self.assertNotIn("APPLICABLE", seen)

    def test_no_seed_recipe_names_a_dutch_oven_without_it_being_held_for_review(self):
        for rid, facts, eq in self.rows:
            for f in eq:
                if f.value["equipment_code"] == "EQUIP_DUTCH_OVEN":
                    self.assertEqual(f.value["review_status"], "pending_review")


if __name__ == "__main__":
    unittest.main()
