#!/usr/bin/env python3
"""Tests for reviewed suggestion text (migration 013, api/app/content_review.py).

The review screen's corrections used to live in one browser's localStorage. They are
rows now, and these tests cover the three claims that move depended on:

  * a reviewer merely OPENING a recipe must not make its text read as "reviewed";
  * a decision never overwrites an earlier one, so "the model was left alone" is
    countable and a disagreement survives;
  * what a version says about who decided cannot come from a browser.

Static tests and the fingerprint tests need no database. The behaviour tests need a
disposable local PostgreSQL and skip otherwise, so the normal run needs no database.
Unlike tests/test_tag_db.py these need no seed data at all - only recipes, gen_ulid()
and migration 013 - so a throwaway database is three commands:

    createdb -h 127.0.0.1 -U postgres mazi_rcv_test
    DSN=postgresql://postgres@127.0.0.1/mazi_rcv_test
    psql "$DSN" -f schema/00_data_sources.sql -f schema/01_recipes.sql
    psql "$DSN" -f schema/migrations/001_household_identity.sql   # for gen_ulid()
    psql "$DSN" -f schema/migrations/014_recipe_content_versions.sql

    MAZIMEAL_TEST_DSN=$DSN python3 -m pytest tests/test_content_review.py -v

A clone loaded the way test_tag_db.py wants also works.

Safety: tests/dbguard.py refuses any non-local host, so these can never reach
Supabase. Every row written is deleted again in tearDown, and only rows for this
module's own synthetic recipe are touched.
"""
from __future__ import annotations

import os
import re
import sys
import unittest
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO / "api"))
import dbguard  # noqa: E402

DSN = os.environ.get("MAZIMEAL_TEST_DSN")
MIGRATION = REPO / "schema" / "migrations" / "014_recipe_content_versions.sql"

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None


# --------------------------------------------------------------------------
# The migration, as committed. No database.
# --------------------------------------------------------------------------
class MigrationStatic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = MIGRATION.read_text()

    def test_it_is_additive_and_safe_to_re_run(self):
        self.assertIn("CREATE TABLE IF NOT EXISTS public.recipe_content_versions", self.text)
        self.assertIn("CREATE INDEX IF NOT EXISTS", self.text)
        self.assertEqual(self.text.count("BEGIN;"), 1)
        self.assertTrue(self.text.rstrip().endswith("COMMIT;"))

    def test_it_never_drops_or_rewrites_anything(self):
        # A migration that can delete review history is a migration that can
        # delete the evidence of who decided what.
        # ON DELETE CASCADE on the recipe FK is allowed and is the point: a
        # recipe that goes away takes its own review history with it.
        statements = re.sub(r"ON DELETE CASCADE", "", self.text)
        self.assertNotRegex(statements, r"\b(DROP|TRUNCATE|DELETE)\b")
        self.assertNotRegex(statements, r"\bUPDATE\s+public\.")

    def test_the_browser_keys_cannot_reach_the_table(self):
        self.assertIn("ENABLE ROW LEVEL SECURITY", self.text)
        self.assertIn("REVOKE ALL ON public.recipe_content_versions FROM anon, authenticated", self.text)
        # RLS with no policy is the point: there must be no CREATE POLICY here.
        self.assertNotIn("CREATE POLICY", self.text)

    def test_the_constraints_that_keep_the_count_honest_are_present(self):
        for constraint in (
            "ck_rcv_outcome_on_review",   # version 1 is the model's; later ones are decisions
            "ck_rcv_reviewer",            # a decision with no reviewer is uncountable
            "ck_rcv_parent",
            "uq_rcv_recipe_version",      # two reviewers cannot both write version 4
            "fk_rcv_recipe",
        ):
            self.assertIn(constraint, self.text, constraint)

    def test_the_four_outcomes_are_the_ones_the_frontend_sends(self):
        store = (REPO / "web" / "src" / "features" / "review" / "reviewStore.js").read_text()
        block = store.split("export const OUTCOME = {", 1)[1].split("};", 1)[0]
        in_js = set(re.findall(r'"([a-z_]+)"', block))
        in_sql = set(re.findall(r"'(confirmed_unchanged|edited|rejected|reverted_to_original)'", self.text))
        self.assertEqual(in_js, in_sql, "the OUTCOME map and the CHECK constraint disagree")


# --------------------------------------------------------------------------
# fingerprint(): pure, and the reason a stale edit is visible. No database.
# --------------------------------------------------------------------------
class Fingerprint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("MAZIMEAL_DSN", "postgresql://unused@127.0.0.1/unused")
        from app import content_review

        cls.cr = content_review

    def test_rule_order_does_not_change_it(self):
        recipe_a = {"recipe_id": "r1", "matched_rules": [{"rule_id": "B"}, {"rule_id": "A"}]}
        recipe_b = {"recipe_id": "r1", "matched_rules": [{"rule_id": "A"}, {"rule_id": "B"}]}
        self.assertEqual(self.cr.fingerprint(recipe_a, {"model": "m"}), self.cr.fingerprint(recipe_b, {"model": "m"}))

    def test_a_different_set_of_rules_changes_it(self):
        one = self.cr.fingerprint({"recipe_id": "r1", "matched_rules": [{"rule_id": "A"}]}, {"model": "m"})
        two = self.cr.fingerprint({"recipe_id": "r1", "matched_rules": [{"rule_id": "A"}, {"rule_id": "B"}]}, {"model": "m"})
        self.assertNotEqual(one, two)

    def test_a_different_model_changes_it(self):
        recipe = {"recipe_id": "r1", "matched_rules": []}
        self.assertNotEqual(self.cr.fingerprint(recipe, {"model": "m1"}), self.cr.fingerprint(recipe, {"model": "m2"}))

    def test_an_unnamed_model_reads_as_the_template_not_as_where_it_was_found(self):
        # "cache" is where the text was found, not what wrote it. Recording it
        # would make a cache hit look like a different input from the template
        # run that filled the cache, and so raise a stale-edit warning about
        # text nobody changed.
        recipe = {"recipe_id": "r1", "matched_rules": []}
        self.assertEqual(self.cr.fingerprint(recipe, {"source": "cache"}), "r1||template")
        self.assertEqual(self.cr.fingerprint(recipe, {}), "r1||template")
        self.assertEqual(self.cr.fingerprint(recipe, {"model": "m", "source": "cache"}), "r1||m")

    def test_a_rule_with_no_id_is_ignored_rather_than_recorded_as_none(self):
        recipe = {"recipe_id": "r1", "matched_rules": [{"rule_id": "A"}, {"name": "no id"}]}
        self.assertEqual(self.cr.fingerprint(recipe, {"model": "m"}), "r1|A|m")


# --------------------------------------------------------------------------
# Behaviour, against a disposable local database.
# --------------------------------------------------------------------------
@unittest.skipIf(not DSN, "set MAZIMEAL_TEST_DSN to a disposable local database to run these")
@unittest.skipIf(psycopg is None, "psycopg is not installed")
class Behaviour(unittest.TestCase):
    """Writes only rows for one synthetic recipe, and deletes them again."""

    @classmethod
    def setUpClass(cls):
        dbguard.assert_local_dsn(DSN)
        os.environ["MAZIMEAL_DSN"] = DSN
        from app import content_review, supabase_repo

        dbguard.assert_local_host(psycopg.conninfo.conninfo_to_dict(DSN).get("host"))
        supabase_repo.DSN = DSN            # the module read the env at import time
        cls.cr = content_review
        cls.recipe_id = str(uuid.uuid4())
        with psycopg.connect(DSN) as conn:
            missing = conn.execute(
                "SELECT to_regclass('public.recipe_content_versions') IS NULL"
            ).fetchone()[0]
            if missing:
                raise unittest.SkipTest("run schema/migrations/013 against the test database first")
            conn.execute(
                """INSERT INTO recipes (recipe_id, recipe_name, meal_category, external_source_id)
                   VALUES (%s, 'content-review test recipe', 'Dinner', %s)""",
                (cls.recipe_id, "content-review-test"),
            )
            conn.commit()

    @classmethod
    def tearDownClass(cls):
        with psycopg.connect(DSN) as conn:
            conn.execute("DELETE FROM recipe_content_versions WHERE recipe_id = %s", (cls.recipe_id,))
            conn.execute("DELETE FROM recipes WHERE recipe_id = %s", (cls.recipe_id,))
            conn.commit()

    def setUp(self):
        with psycopg.connect(DSN) as conn:
            conn.execute("DELETE FROM recipe_content_versions WHERE recipe_id = %s", (self.recipe_id,))
            conn.commit()
        self.recipe = {
            "recipe_id": self.recipe_id,
            "matched_rules": [{"rule_id": "BIO-002"}, {"rule_id": "INH-006"}],
        }
        self.payload = {
            "model": "test/model-1",
            "suggestions": [{"rule_id": "BIO-002", "headline": "as written", "body": "original"}],
            "summary": {"text": "a summary"},
        }

    def seed(self):
        return self.cr.seed(self.recipe, self.payload)

    # -- version 1 ---------------------------------------------------------
    def test_seeding_writes_the_models_output_as_version_one(self):
        record = self.seed()
        self.assertEqual(record["current_version"], 1)
        first = record["versions"][0]
        self.assertEqual(first["author"], "model:model-1")
        self.assertIsNone(first["review"])
        self.assertEqual(first["suggestions"], self.payload["suggestions"])

    def test_seeding_twice_does_not_rewrite_the_baseline(self):
        self.seed()
        again = self.cr.seed(self.recipe, {**self.payload, "suggestions": [], "model": "other/model-2"})
        self.assertEqual(len(again["versions"]), 1)
        self.assertEqual(again["versions"][0]["author"], "model:model-1")
        self.assertEqual(again["versions"][0]["suggestions"], self.payload["suggestions"])

    def test_an_unnamed_model_is_recorded_as_the_template_not_as_where_it_was_found(self):
        record = self.cr.seed(self.recipe, {"source": "cache", "suggestions": []})
        self.assertEqual(record["versions"][0]["author"], "model:template")

    # -- what a cook sees --------------------------------------------------
    def test_a_recipe_with_only_the_baseline_reads_as_unreviewed(self):
        self.seed()
        self.assertIsNone(self.cr.current(self.recipe_id))

    def test_a_decision_is_what_the_cook_screen_shows(self):
        self.seed()
        self.cr.add_version(self.recipe_id, {"outcome": self.cr.EDITED,
                                             "suggestions": [{"rule_id": "BIO-002", "body": "edited"}]},
                            reviewer="a@example.com")
        version = self.cr.current(self.recipe_id)
        self.assertEqual(version["version"], 2)
        self.assertEqual(version["suggestions"][0]["body"], "edited")
        self.assertEqual(version["review"]["reviewer"], "a@example.com")

    def test_a_rejection_publishes_nothing_even_over_an_earlier_approval(self):
        self.seed()
        self.cr.add_version(self.recipe_id, {"outcome": self.cr.EDITED,
                                             "suggestions": [{"body": "approved once"}]},
                            reviewer="a@example.com")
        self.assertIsNotNone(self.cr.current(self.recipe_id))
        self.cr.add_version(self.recipe_id, {"outcome": self.cr.REJECTED, "note": "not good enough"},
                            reviewer="b@example.com")
        self.assertIsNone(self.cr.current(self.recipe_id))

    # -- history and inheritance -------------------------------------------
    def test_every_decision_appends_including_one_that_changed_nothing(self):
        self.seed()
        for reviewer in ("a@example.com", "b@example.com"):
            self.cr.add_version(self.recipe_id, {"outcome": self.cr.CONFIRMED}, reviewer=reviewer)
        record = self.cr.get(self.recipe_id)
        self.assertEqual([v["version"] for v in record["versions"]], [1, 2, 3])
        self.assertEqual([v["review"]["reviewer"] for v in record["versions"][1:]],
                         ["a@example.com", "b@example.com"])

    def test_a_field_left_out_is_inherited_not_cleared(self):
        self.seed()
        self.cr.add_version(self.recipe_id, {"outcome": self.cr.EDITED, "rules_removed": ["INH-006"]},
                            reviewer="a@example.com")
        # A second reviewer changes only the text; the rule removal must survive.
        record = self.cr.add_version(
            self.recipe_id,
            {"outcome": self.cr.EDITED, "suggestions": [{"body": "reworded"}]},
            reviewer="b@example.com",
        )
        latest = record["versions"][-1]
        self.assertEqual(latest["rules_removed"], ["INH-006"])
        self.assertEqual(latest["suggestions"][0]["body"], "reworded")

    def test_an_empty_list_clears_where_omission_inherits(self):
        self.seed()
        self.cr.add_version(self.recipe_id, {"outcome": self.cr.EDITED, "rules_removed": ["INH-006"]},
                            reviewer="a@example.com")
        record = self.cr.add_version(self.recipe_id, {"outcome": self.cr.EDITED, "rules_removed": []},
                                     reviewer="a@example.com")
        self.assertEqual(record["versions"][-1]["rules_removed"], [])

    def test_the_author_is_the_reviewer_the_caller_verified(self):
        self.seed()
        record = self.cr.add_version(self.recipe_id, {"outcome": self.cr.CONFIRMED},
                                     reviewer="who@example.com")
        self.assertEqual(record["versions"][-1]["author"], "human:who@example.com")

    # -- refusals ----------------------------------------------------------
    def test_an_unknown_outcome_is_refused(self):
        from fastapi import HTTPException

        self.seed()
        with self.assertRaises(HTTPException) as raised:
            self.cr.add_version(self.recipe_id, {"outcome": "looks_good"}, reviewer="a@example.com")
        self.assertEqual(raised.exception.status_code, 400)

    def test_reviewing_a_recipe_with_no_baseline_is_refused(self):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as raised:
            self.cr.add_version(self.recipe_id, {"outcome": self.cr.EDITED}, reviewer="a@example.com")
        self.assertEqual(raised.exception.status_code, 409)

    def test_a_decision_with_no_reviewer_is_refused(self):
        from fastapi import HTTPException

        self.seed()
        with self.assertRaises(HTTPException):
            self.cr.add_version(self.recipe_id, {"outcome": self.cr.CONFIRMED}, reviewer="")

    def test_an_id_that_names_no_recipe_is_a_404_not_a_500(self):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as raised:
            self.cr.get("not-a-uuid")
        self.assertEqual(raised.exception.status_code, 404)

    def test_the_database_refuses_an_outcome_on_version_one(self):
        # The API never writes this; the constraint is what makes it true of the
        # data rather than of the code that happens to write it.
        with psycopg.connect(DSN) as conn:
            with self.assertRaises(psycopg.errors.CheckViolation):
                conn.execute(
                    """INSERT INTO recipe_content_versions
                           (recipe_id, version, author, outcome, reviewer)
                       VALUES (%s, 1, 'model:x', 'edited', 'a@example.com')""",
                    (self.recipe_id,),
                )
            conn.rollback()

    def test_the_database_refuses_two_rows_for_one_version(self):
        self.seed()
        with psycopg.connect(DSN) as conn:
            with self.assertRaises(psycopg.errors.UniqueViolation):
                conn.execute(
                    """INSERT INTO recipe_content_versions
                           (recipe_id, version, parent, author, outcome, reviewer)
                       VALUES (%s, 1, NULL, 'model:x', NULL, NULL)""",
                    (self.recipe_id,),
                )
            conn.rollback()

    # -- the count ---------------------------------------------------------
    def test_a_revert_is_counted_but_kept_out_of_the_ratio(self):
        self.seed()
        self.cr.add_version(self.recipe_id, {"outcome": self.cr.CONFIRMED}, reviewer="a@example.com")
        before = self.cr.stats()
        self.cr.add_version(self.recipe_id, {"outcome": self.cr.REVERTED}, reviewer="a@example.com")
        after = self.cr.stats()
        self.assertEqual(after["reverted"], before["reverted"] + 1)
        self.assertEqual(after["unchangedRate"], before["unchangedRate"])


if __name__ == "__main__":
    unittest.main()
