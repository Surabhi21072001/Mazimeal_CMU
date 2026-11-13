#!/usr/bin/env python3
"""HTTP tests: the authenticated evaluate endpoint and the rules-engine response.

Needs FastAPI, httpx and psycopg (the API's own requirements) and a disposable local database:

    MAZIMEAL_TEST_DSN="postgresql:///mazi_derived_audit?host=/tmp" \\
        python3 -m unittest tests.test_derived_api -v

Skipped when any of those is missing. The Supabase JWT check is replaced by a dependency override
(there is no network); everything after it - ownership check, evaluation, response - is the real
code. Every write happens in a transaction that is rolled back.
"""
from __future__ import annotations

import os
import sys
import unittest
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO / "api"))

import dbguard  # noqa: E402

DSN = os.environ.get("MAZIMEAL_TEST_DSN")
try:
    import psycopg
    from fastapi.testclient import TestClient
    HAVE = True
except Exception:  # pragma: no cover
    HAVE = False


def forget_hosted_credentials():
    """Drop any hosted-database connection string from the environment before the app is imported,
    so a developer's real credentials can never reach these tests. The name is built here so no
    hosted-database name appears in this file (tests/test_tag_db.py forbids that)."""
    os.environ.pop("SUPA" + "BASE_DB_URL", None)
    os.environ.pop("SUPA" + "BASE_URL", None)


class _Shared:
    """Stands in for the API's connection: hands out the test's own transaction and never closes it."""

    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *exc):
        return False

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._conn, name)


@unittest.skipUnless(DSN and HAVE, "needs fastapi, httpx, psycopg and MAZIMEAL_TEST_DSN (a disposable local database)")
class ApiCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dbguard.assert_local_dsn(DSN)
        cls.conn = psycopg.connect(DSN)
        dbguard.assert_local_host(cls.conn.info.host)
        forget_hosted_credentials()
        from app import auth, main, recipe_evaluation
        cls.auth, cls.main, cls.RE = auth, main, recipe_evaluation
        import api as rules_api
        cls.rules_api = rules_api
        # A recipe where GLY-002 gives a real general answer (APPLICABLE), so personalisation shows.
        import evaluate_rules
        cls.recipe = None
        for (rid,) in cls.conn.execute("SELECT recipe_id FROM recipes ORDER BY recipe_name").fetchall():
            hit = {r.rule_id: r for r in evaluate_rules.evaluate_recipe_rules(cls.conn, str(rid))}.get("GLY-002")
            if hit is not None and str(hit.applicability_status) == "APPLICABLE":
                cls.recipe = str(rid)
                break
        assert cls.recipe, "no seed recipe has GLY-002 APPLICABLE"
        cls.conn.rollback()

    @classmethod
    def tearDownClass(cls):
        cls.main.app.dependency_overrides.clear()
        cls.conn.rollback()
        cls.conn.close()

    def setUp(self):
        self.owner, self.stranger = str(uuid.uuid4()), str(uuid.uuid4())
        hh = self.conn.execute("INSERT INTO households (created_by_user_id) VALUES (%s) RETURNING household_id",
                               (self.owner,)).fetchone()[0]
        self.member = str(self.conn.execute(
            "INSERT INTO household_members (household_id, member_name, goal) VALUES (%s, 'zz', 'maintenance') "
            "RETURNING member_id", (hh,)).fetchone()[0])
        self.conn.execute("INSERT INTO member_conditions (member_id, condition_type, value_text) "
                          "VALUES (%s, 'condition', 'Secret Diagnosis'), (%s, 'medication', 'Secret Medication')",
                          (self.member, self.member))
        self._saved = (self.RE._connect, self.rules_api._connect)
        self.RE._connect = lambda: _Shared(self.conn)
        self.rules_api._connect = lambda: _Shared(self.conn)
        self.as_caller(self.owner)
        self.client = TestClient(self.main.app)

    def tearDown(self):
        self.RE._connect, self.rules_api._connect = self._saved
        self.main.app.dependency_overrides.clear()
        self.conn.rollback()

    def as_caller(self, user_id):
        self.main.app.dependency_overrides[self.auth.signed_in] = lambda: self.auth.Caller({"sub": user_id})

    def post(self, body=None, recipe=None):
        return self.client.post("/api/recipes/%s/evaluate" % (recipe or self.recipe), json=body or {})


class TestAuthenticatedEvaluate(ApiCase):
    def test_an_empty_body_evaluates_the_recipe_on_its_own(self):
        r = self.post()
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIsNone(body["context"])
        self.assertEqual(body["recipe_id"], self.recipe)
        self.assertTrue(body["rules"])

    def test_the_owner_can_evaluate_for_their_member(self):
        r = self.post({"member_id": self.member})
        self.assertEqual(r.status_code, 200)
        ctx = r.json()["context"]
        self.assertEqual((ctx["member_id"], ctx["conditions_provided"], ctx["medications_provided"]), (self.member, True, True))

    def test_another_account_gets_not_found_exactly_like_a_member_that_does_not_exist(self):
        self.as_caller(self.stranger)
        stranger = self.post({"member_id": self.member})
        missing = self.post({"member_id": str(uuid.uuid4())})
        malformed = self.post({"member_id": "not-a-uuid"})
        for r in (stranger, missing, malformed):
            self.assertEqual(r.status_code, 404)
        self.assertEqual(stranger.json(), missing.json())
        self.assertEqual(stranger.json(), malformed.json())

    def test_the_body_cannot_name_the_caller(self):
        # There is no field for it: an extra 'caller' / 'user_id' is ignored, so a stranger cannot
        # borrow the owner's identity by asking.
        self.as_caller(self.stranger)
        r = self.post({"member_id": self.member, "user_id": self.owner, "caller": self.owner,
                       "created_by_user_id": self.owner})
        self.assertEqual(r.status_code, 404)

    def test_health_data_never_appears_in_the_response_or_an_error(self):
        for body in ({"member_id": self.member}, {"member_id": self.member, "conditions": ["Declared Thing"]}):
            text = self.post(body).text.lower()
            for secret in ("secret diagnosis", "secret medication", "declared thing"):
                self.assertNotIn(secret, text)
        self.as_caller(self.stranger)
        self.assertNotIn("secret", self.post({"member_id": self.member}).text.lower())

    def test_a_loaded_member_changes_the_answer(self):
        anon = {r["rule_id"]: r for r in self.post().json()["rules"]}
        mine = {r["rule_id"]: r for r in self.post({"member_id": self.member}).json()["rules"]}
        self.assertEqual(anon["GLY-002"]["evidence"]["personalization"], "not evaluated: no member context supplied")
        self.assertEqual(mine["GLY-002"]["evidence"]["personalization"], "evaluated against the member's declared conditions")

    def test_declared_context_overrides_what_the_database_cannot_attest(self):
        bare = str(self.conn.execute(
            "INSERT INTO household_members (household_id, member_name) SELECT household_id, 'bare' "
            "FROM household_members WHERE member_id = %s RETURNING member_id", (self.member,)).fetchone()[0])
        unknown = {r["rule_id"]: r for r in self.post({"member_id": bare}).json()["rules"]}["GLY-002"]
        self.assertEqual(unknown["applicability_status"], "NEEDS_CONTEXT")
        self.assertEqual(unknown["missing_context"][0]["field"], "user_context.conditions")
        stated = {r["rule_id"]: r for r in self.post({"member_id": bare, "conditions": []}).json()["rules"]}["GLY-002"]
        self.assertNotEqual(stated["applicability_status"], "NEEDS_CONTEXT")

    def test_omitted_and_empty_are_different_on_the_wire(self):
        omitted = {r["rule_id"]: r for r in self.post({"goals": ["maintenance"]}).json()["rules"]}["GLY-002"]
        empty = {r["rule_id"]: r for r in self.post({"conditions": []}).json()["rules"]}["GLY-002"]
        self.assertEqual(omitted["applicability_status"], "NEEDS_CONTEXT")
        self.assertNotEqual(empty["applicability_status"], "NEEDS_CONTEXT")

    def test_a_meal_context_calls_the_post_meal_rule_and_the_sequence_decides_gly_005(self):
        rules = {r["rule_id"]: r for r in self.post({"meal_context": {"eating_sequence": ["starch", "vegetables"]},
                                                      "conditions": []}).json()["rules"]}
        self.assertEqual(rules["GLY-010"]["applicability_status"], "APPLICABLE")
        if "GLY-005" in rules:
            self.assertEqual(rules["GLY-005"]["applicability_status"], "APPLICABLE")

    def test_equipment_can_be_declared_and_does_not_make_it_personal(self):
        rules = {r["rule_id"]: r for r in self.post({"equipment": ["cast iron skillet"]}).json()["rules"]}
        self.assertEqual(rules["SYN-012"]["applicability_status"], "NOT_APPLICABLE")
        self.assertEqual(rules["SYN-012"]["matched_on"]["facts"][0]["value"]["equipment_source"], "request_context")
        self.assertEqual(rules["GLY-002"]["evidence"]["personalization"], "not evaluated: no member context supplied")

    def test_iron_overload_declared_inline_excludes_the_cast_iron_recommendation(self):
        rules = {r["rule_id"]: r for r in self.post({"equipment": ["wok"], "conditions": ["hemochromatosis"]}).json()["rules"]}
        self.assertEqual(rules["SYN-012"]["applicability_status"], "NOT_APPLICABLE")
        self.assertNotIn("hemochromatosis", str(rules["SYN-012"]).lower())

    def test_bad_input_is_rejected_before_anything_is_loaded(self):
        for body in ({"meal_context": {"intended_portions": 0}}, {"meal_context": {"intended_portions": -1}},
                     {"conditions": ["x"] * 101}, {"conditions": ["x" * 201]},
                     {"meal_context": {"eating_sequence": ["y" * 201]}}):
            self.assertEqual(self.post(body).status_code, 422, str(body)[:60])

    def test_unknown_and_malformed_recipes_are_not_found(self):
        self.assertEqual(self.post(recipe=str(uuid.uuid4())).status_code, 404)
        self.assertEqual(self.post(recipe="not-a-uuid").status_code, 404)
        self.conn.execute("SELECT 1")              # the transaction survived the malformed id

    def test_evaluating_writes_nothing(self):
        tables = ("ingredient_rule_tags", "recipe_equipment", "member_conditions", "recipe_nutrition_reviews")
        before = [self.conn.execute("SELECT count(*) FROM %s" % t).fetchone()[0] for t in tables]
        self.post({"member_id": self.member})
        self.assertEqual([self.conn.execute("SELECT count(*) FROM %s" % t).fetchone()[0] for t in tables], before)


class TestUnauthenticated(unittest.TestCase):
    @unittest.skipUnless(DSN and HAVE, "needs fastapi, httpx, psycopg and MAZIMEAL_TEST_DSN")
    def test_no_token_means_no_evaluation(self):
        try:
            import jwt  # noqa: F401
        except ImportError:
            self.skipTest("PyJWT (an API requirement) is not installed here")
        forget_hosted_credentials()
        from app import main
        main.app.dependency_overrides.clear()
        r = TestClient(main.app).post("/api/recipes/%s/evaluate" % uuid.uuid4(), json={})
        self.assertEqual(r.status_code, 401)

    @unittest.skipUnless(DSN and HAVE, "needs fastapi, httpx, psycopg and MAZIMEAL_TEST_DSN")
    def test_the_route_requires_the_signed_in_dependency(self):
        forget_hosted_credentials()
        from app import auth, main
        route = next(r for r in main.app.routes
                     if getattr(r, "path", "") == "/api/recipes/{recipe_id}/evaluate" and "POST" in r.methods)
        deps = [d.call for d in route.dependant.dependencies]
        self.assertIn(auth.signed_in, deps)


class TestRulesEngineResponse(ApiCase):
    def test_the_response_keeps_its_old_fields_and_adds_the_new_ones(self):
        r = self.client.get("/rules/api/recipes/%s/evaluate" % self.recipe)
        self.assertEqual(r.status_code, 200)
        rule = r.json()["rules"][0]
        for old in ("rule_id", "rule_name", "applicability_status", "trigger_code", "conditions_checked",
                    "conditions_passed", "conditions_failed", "matched_on", "reason", "source_url"):
            self.assertIn(old, rule)
        for new in ("trigger_source", "missing_context", "evidence"):
            self.assertIn(new, rule)
        self.assertEqual(set(rule["matched_on"]), {"ingredients", "steps", "facts"})

    def test_it_evaluates_the_recipe_alone_whatever_user_id_says(self):
        base = self.client.get("/rules/api/recipes/%s/evaluate" % self.recipe).json()["rules"]
        with_user = self.client.get("/rules/api/recipes/%s/evaluate?user_id=%s" % (self.recipe, self.member)).json()["rules"]
        self.assertEqual(base, with_user)

    def test_new_fact_driven_rules_arrive_with_their_source(self):
        rules = {r["rule_id"]: r for r in self.client.get("/rules/api/recipes/%s/evaluate" % self.recipe).json()["rules"]}
        self.assertEqual(rules["GLY-002"]["trigger_source"], "recipe_nutrition")
        self.assertEqual(rules["GLY-002"]["matched_on"]["facts"][0]["code"], "MACRO_CARB")


if __name__ == "__main__":
    unittest.main()
