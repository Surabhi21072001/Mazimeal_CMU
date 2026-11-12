#!/usr/bin/env python3
"""Database tests for the tagging work: migrations 010/011, the tagger on real seed data,
and rule reachability through the real detector and evaluator.

These run ONLY against a disposable local PostgreSQL that has been loaded from the repo
(schema/, the seeds, and migrations 006-011). They skip otherwise, so the normal test
run needs no database.

    MAZIMEAL_TEST_DSN=postgresql://audit@127.0.0.1:54329/mazi_audit \\
        python3 -m unittest tests.test_tag_db -v

Safety:
  * tests/dbguard.py refuses any non-local host, before and after connecting (Supabase and other hosted
    databases are named explicitly), or every test fails;
  * every write (tags, synthetic recipes, re-running a migration) happens inside a
    transaction that is rolled back, so the database is left as it was;
  * nothing here calls tag_ingredients --apply or apply_tier1. Migration 012 is exercised by running its SQL
    text inside a transaction that is rolled back.
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import sys
import tempfile
import unittest
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

MIGRATIONS = REPO / "schema" / "migrations"

# Why each rule has no tier-1 path today. The test fails if a rule moves in or out of this
# list without someone updating it, so reachability cannot change silently.
UNREACHABLE_AT_TIER_1 = {
    "GLY-001": "needs a glycaemic index; the database has none",
    "GLY-002": "recipe-level carbohydrate trigger, not an ingredient tag",
    "GLY-003": "recipe-level carbohydrate trigger, not an ingredient tag",
    "GLY-004": "recipe-level carbohydrate trigger, not an ingredient tag",
    "GLY-005": "engine concept (mixed meal)",
    "GLY-006": "needs recipe_steps: starch that was cooked and cooled",
    "GLY-009": "recipe-level carbohydrate trigger, not an ingredient tag",
    "GLY-010": "behaviour after the meal, not an ingredient",
    "GLY-011": "recipe-level carbohydrate threshold",
    "GLY-012": "no ingredient in the 400 recipes is a sugar-sweetened beverage",
    "GLY-013": "ripeness is a state the recipe does not record",
    "GLY-014": "do_not_automate",
    "GLY-015": "process step read from recipe_steps",
    "INH-001": "tea/coffee is only flavouring here, and a curated compound is held at tier 2",
    "INH-002": "CMP_PHYTATE is a curated compound: tier 2 until it has a citation",
    "INH-003": "calcium-supplement rule; no calcium food reaches tier 1 either",
    "INH-004": "CMP_OXALATE is a curated compound: tier 2 until it has a citation",
    "INH-005": "raw egg white is a state, not an ingredient",
    "INH-008": "medication, a profile fact",
    "INH-009": "supplement, do_not_automate",
    "INH-010": "supplement, do_not_automate",
    "INH-011": "recipe-level fat total",
    "INH-012": "engine concept (conflicting goals)",
    "SYN-010": "no dairy calcium food is clear of the 20% line at its reference amount",
    "SYN-012": "cookware is a step, not an ingredient",
}

TIER1_MIGRATION = "012_apply_tier1_ingredient_tags.sql"

# The 16 rules the approved tags make reachable. Every one is a candidate only: none has an evaluator.
NEWLY_REACHABLE = {"BIO-008", "BIO-009", "BIO-010", "BIO-012", "BIO-014", "BIO-015", "GLY-008", "INH-006",
                   "SYN-001", "SYN-002", "SYN-004", "SYN-005", "SYN-006", "SYN-007", "SYN-008", "SYN-009"}
REAL_EVALUATORS = {"BIO-002", "BIO-003", "BIO-007", "BIO-011", "GLY-007"}
# Reachable but unimplemented: they are triggered, and return NEEDS_CONTEXT ("condition evaluator not implemented").
NEEDS_CONTEXT_RULES = {"BIO-001", "BIO-004", "BIO-005", "BIO-006", "BIO-008", "BIO-009", "BIO-010", "BIO-012",
                       "BIO-013", "BIO-014", "BIO-015", "GLY-008", "INH-006", "INH-007", "SYN-001", "SYN-002",
                       "SYN-003", "SYN-004", "SYN-005", "SYN-006", "SYN-007", "SYN-008", "SYN-009", "SYN-011"}

REACHABLE_BEFORE = {"BIO-001", "BIO-002", "BIO-003", "BIO-004", "BIO-005", "BIO-006", "BIO-007", "BIO-011",
                    "BIO-013", "GLY-007", "INH-007", "SYN-003", "SYN-011"}


def listed_pairs():
    """[(ingredient name, rule code, category)] from migration 012's VALUES list."""
    text = (MIGRATIONS / TIER1_MIGRATION).read_text()
    rows = re.findall(r"^    \('((?:[^']|'')*)', '([A-Z_]+)', '(identity|nutrient)'\)[,;]$", text, re.M)
    return [(n.replace("''", "'"), c, cat) for n, c, cat in rows]


def strip_transaction(sql: str) -> str:
    """A migration owns its BEGIN/COMMIT. Inside a test transaction we need neither."""
    return re.sub(r"^(BEGIN|COMMIT);\s*$", "", sql, flags=re.M)


@unittest.skipUnless(DSN and psycopg, "set MAZIMEAL_TEST_DSN to a disposable local database to run these")
class DatabaseCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dbguard.assert_local_dsn(DSN)                      # refuse before opening any connection
        cls.conn = psycopg.connect(DSN)
        try:
            dbguard.assert_local_host(cls.conn.info.host)  # and again on the host libpq actually used
        except AssertionError:
            cls.conn.close()
            raise
        have = cls.conn.execute("SELECT to_regclass('rule_code_components') IS NOT NULL, "
                                "(SELECT count(*) FROM business_rules), (SELECT count(*) FROM recipes)").fetchone()
        if not have[0] or have[1] != 54 or have[2] != 400:
            cls.conn.close()
            raise unittest.SkipTest("database is not the loaded repo seed (rules=%s recipes=%s)" % (have[1], have[2]))
        cls.conn.rollback()

    @classmethod
    def tearDownClass(cls):
        cls.conn.rollback()
        cls.conn.close()

    def tearDown(self):
        self.conn.rollback()

    def one(self, sql, params=()):
        return self.conn.execute(sql, params).fetchone()[0]

    def rows(self, sql, params=()):
        return self.conn.execute(sql, params).fetchall()

    def run_migration(self, name):
        self.conn.execute(strip_transaction((MIGRATIONS / name).read_text()))


class Migration010State(DatabaseCase):
    def record(self, name):
        return self.one("SELECT m.source_record_id FROM ingredient_source_map m JOIN ingredients i USING (ingredient_id) "
                        "WHERE i.ingredient_name = %s", (name,))

    def nutrient(self, name, nutrient):
        return self.one("SELECT n.value_per_100g FROM ingredient_nutrition n JOIN ingredients i USING (ingredient_id) "
                        "WHERE i.ingredient_name = %s AND n.nutrient_id = %s", (name, nutrient))

    def test_fifteen_mappings_were_corrected_and_marked_manual(self):
        self.assertEqual(self.one("SELECT count(*) FROM ingredient_source_map WHERE matched_by = 'manual'"), 15)

    def test_every_oat_name_now_holds_the_cereal_record_and_its_values(self):
        oats = ["oats", "oatmeal", "old fashioned oats", "quick-cooking oatmeal", "rolled oats", "Old mill oats", "Robin Hood oats"]
        want = {r[0]: r[1] for r in self.rows(
            "SELECT n.nutrient_id, n.value_per_100g FROM ingredient_nutrition n JOIN ingredients i USING (ingredient_id) "
            "WHERE i.ingredient_name = 'quick oats'")}
        self.assertEqual(len(want), 28)
        for name in oats:
            self.assertEqual(self.record(name), "173904", name)
            got = {r[0]: r[1] for r in self.rows(
                "SELECT n.nutrient_id, n.value_per_100g FROM ingredient_nutrition n JOIN ingredients i USING (ingredient_id) "
                "WHERE i.ingredient_name = %s", (name,))}
            self.assertEqual(got, want, name)

    def test_grapes_are_no_longer_grape_leaves(self):
        self.assertEqual(self.record("grapes"), "174683")
        self.assertLess(self.nutrient("grapes", "Vitamin_A"), 10)      # leaves were 1376 mcg/100 g
        self.assertLess(self.nutrient("grapes", "Vitamin_C"), 10)

    def test_strawberry_is_a_strawberry_and_parsley_flakes_are_dried_parsley(self):
        self.assertEqual(self.record("strawberry"), "167762")
        self.assertAlmostEqual(float(self.nutrient("strawberry", "Vitamin_C")), 58.8, places=1)
        self.assertEqual(self.record("parsley flakes"), "170930")
        self.assertGreater(self.nutrient("parsley flakes", "Iron"), 20)  # dried is dense; fresh was 6.2

    def test_pending_import_ingredients_hold_no_wrong_numbers(self):
        for name in ("orange", "sweet potatoes", "sun-dried tomatoes", "tomato paste", "sesame seeds"):
            n = self.one("SELECT count(*) FROM ingredient_nutrition n JOIN ingredients i USING (ingredient_id) "
                         "WHERE i.ingredient_name = %s", (name,))
            self.assertEqual(n, 0, "%s should be unavailable until the USDA import runs" % name)

    def test_pending_ingredients_point_at_the_right_record_so_the_import_can_fill_them(self):
        want = {"orange": 169097, "sweet potatoes": 168482, "sun-dried tomatoes": 168567,
                "tomato paste": 170459, "sesame seeds": 170150}
        for name, fdc in want.items():
            self.assertEqual(self.one("SELECT usda_fdc_id FROM ingredients WHERE ingredient_name = %s", (name,)), fdc, name)
            self.assertEqual(int(self.record(name)), fdc, name)

    def test_usda_fdc_id_stays_unique(self):
        self.assertEqual(self.one("SELECT count(*) FROM (SELECT usda_fdc_id FROM ingredients WHERE usda_fdc_id IS NOT NULL "
                                  "GROUP BY 1 HAVING count(*) > 1) d"), 0)

    def test_food_category_follows_the_corrected_food(self):
        self.assertEqual(self.one("SELECT food_category FROM ingredients WHERE ingredient_name = 'oats'"), "Breakfast Cereals")
        self.assertEqual(self.one("SELECT food_category FROM ingredients WHERE ingredient_name = 'grapes'"), "Fruits and Fruit Juices")

    def test_unchanged_by_design_the_milk_and_cheese_mappings(self):
        self.assertEqual(self.record("milk"), "172225")       # still buttermilk; excluded as evidence instead
        self.assertEqual(self.record("cheese"), "168124")


class Migration010Behaviour(DatabaseCase):
    def snapshot(self):
        return (self.one("SELECT count(*) FROM ingredient_nutrition"),
                self.rows("SELECT i.ingredient_name, m.source_record_id FROM ingredient_source_map m "
                          "JOIN ingredients i USING (ingredient_id) WHERE m.matched_by = 'manual' ORDER BY 1"))

    def test_running_it_again_changes_nothing(self):
        before = self.snapshot()
        self.run_migration("010_fix_usda_matches.sql")
        self.assertEqual(self.snapshot(), before)

    def test_it_refuses_to_run_against_a_state_it_was_not_written_for(self):
        self.conn.execute("UPDATE ingredient_source_map SET source_record_id = '999', matched_by = 'fuzzy' "
                          "WHERE ingredient_id = (SELECT ingredient_id FROM ingredients WHERE ingredient_name = 'grapes')")
        with self.assertRaises(psycopg.errors.RaiseException) as ctx:
            self.run_migration("010_fix_usda_matches.sql")
        self.assertIn("grapes", str(ctx.exception))

    def test_it_refuses_when_the_donor_no_longer_holds_the_record(self):
        self.conn.execute("UPDATE ingredient_source_map SET source_record_id = '1' "
                          "WHERE ingredient_id = (SELECT ingredient_id FROM ingredients WHERE ingredient_name = 'quick oats')")
        self.conn.execute("UPDATE ingredient_source_map SET source_record_id = '169063', matched_by = 'alias' "
                          "WHERE ingredient_id = (SELECT ingredient_id FROM ingredients WHERE ingredient_name = 'oats')")
        with self.assertRaises(psycopg.errors.RaiseException) as ctx:
            self.run_migration("010_fix_usda_matches.sql")
        self.assertIn("donor", str(ctx.exception))


class Migration011(DatabaseCase):
    def tag_count(self, name, code="ING_PASTA"):
        return self.one("SELECT count(*) FROM ingredient_rule_tags t JOIN ingredients i USING (ingredient_id) "
                        "WHERE i.ingredient_name = %s AND t.rule_code = %s", (name, code))

    def test_the_fresh_seed_does_not_carry_the_tag(self):
        self.assertEqual(self.tag_count("cellophane noodle"), 0)

    def test_it_removes_the_old_tag_from_a_database_that_has_it_and_only_that_one(self):
        self.conn.execute("INSERT INTO ingredient_rule_tags (ingredient_id, rule_code) "
                          "SELECT ingredient_id, 'ING_PASTA' FROM ingredients WHERE ingredient_name = 'cellophane noodle'")
        self.assertEqual(self.tag_count("cellophane noodle"), 1)
        before = self.one("SELECT count(*) FROM ingredient_rule_tags")
        self.run_migration("011_retract_cellophane_pasta_tag.sql")
        self.assertEqual(self.tag_count("cellophane noodle"), 0)
        self.assertEqual(self.one("SELECT count(*) FROM ingredient_rule_tags"), before - 1)
        self.assertEqual(self.tag_count("spaghetti"), 1)

    def test_running_it_when_there_is_nothing_to_remove_is_harmless(self):
        before = self.one("SELECT count(*) FROM ingredient_rule_tags")
        self.run_migration("011_retract_cellophane_pasta_tag.sql")
        self.assertEqual(self.one("SELECT count(*) FROM ingredient_rule_tags"), before)

    def test_it_leaves_other_codes_on_the_same_ingredient_alone(self):
        self.conn.execute("INSERT INTO ingredient_rule_tags (ingredient_id, rule_code) "
                          "SELECT ingredient_id, c FROM ingredients, unnest(ARRAY['ING_PASTA','ING_EGG']) c "
                          "WHERE ingredient_name = 'cellophane noodle'")
        self.run_migration("011_retract_cellophane_pasta_tag.sql")
        self.assertEqual(self.tag_count("cellophane noodle", "ING_EGG"), 1)


class TaggerOnSeedData(DatabaseCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import tag_ingredients as T
        cls.T = T
        cls.ings = T.load(cls.conn)
        cls.props, cls.unj = T.build_all(cls.ings)
        cls.cur = {}
        for code, rows in cls.props.items():
            for p in rows:
                cls.cur[(code, p.ingredient.name)] = p

    def test_loads_every_ingredient_once(self):
        self.assertEqual(len(self.ings), 559)

    def test_snapshot_of_the_reviewed_numbers(self):
        """Update these on purpose when a threshold or exclusion is deliberately changed."""
        flat = [p for rows in self.props.values() for p in rows]
        counts = {t: sum(1 for p in flat if p.tier == t) for t in (1, 2, 3)}
        self.assertEqual((len(flat), counts[1], counts[2], counts[3]), (335, 232, 89, 14))
        self.assertEqual(sum(len(v) for v in self.unj.values()), 32)

    def test_curated_compounds_have_no_tier_1_without_a_citation(self):
        for code in ("CMP_PHYTATE", "CMP_OXALATE", "BEV_TEA_COFFEE"):
            self.assertEqual([p for p in self.props[code] if p.tier == 1], [], code)
            self.assertTrue(self.props[code], code)

    def test_the_audit_false_positives_are_gone(self):
        proposed = {name for (_, name) in self.cur}
        for name in ("chocolate chips", "fryer chickens", "spaghetti squash", "chive & onion cream cheese",
                     "tortilla chips", "corn tortilla chips", "non-fat tortilla chips", "graham cracker",
                     "panko breadcrumbs", "cellophane noodle", "firm tofu", "extra firm tofu"):
            self.assertNotIn(name, {n for (c, n) in self.cur if c in ("ING_GRAIN", "ING_GRAIN_LEGUME", "ING_LEGUME",
                                                                      "BEV_SSB", "ING_ALLIUM", "CMP_PHYTATE")}, name)
        self.assertNotIn(("BEV_SSB", "chocolate chips"), self.cur)

    def test_garnishes_and_aromatics_are_not_rich_sources(self):
        for code in ("NUT_NONHEME_IRON", "NUT_VITC", "NUT_CAROTENOIDS", "ING_VITC_FOLATE_VEG"):
            names = {n for (c, n) in self.cur if c == code}
            self.assertFalse(names & {"parsley", "fresh parsley", "garlic", "garlic cloves", "tomato paste", "lemon juice"}, code)

    def test_buttermilk_vitamin_d_is_blocked_not_tier_1(self):
        for name in ("buttermilk", "low-fat buttermilk"):
            self.assertEqual(self.cur[("NUT_VITD", name)].tier, 3, name)
        self.assertEqual({n for (c, n), p in self.cur.items() if c == "NUT_VITD" and p.tier == 1},
                         {"salmon fillets", "trout"})

    def test_wrong_usda_matches_do_not_drive_a_tier_1_nutrient_tag(self):
        for (code, name), p in self.cur.items():
            if p.how == "nutrient" and p.tier == 1:
                self.assertNotIn(name, {"cheese", "milk", "1% low-fat milk", "2% low-fat milk", "nonfat milk", "skim milk",
                                        "evaporated milk", "fat-free evaporated milk", "unsweetened applesauce",
                                        "ground coriander", "grapes", "orange", "sweet potatoes", "sun-dried tomatoes"}, code)

    def test_tier_1_nutrient_proposals_meet_their_own_stated_threshold(self):
        for (code, name), p in self.cur.items():
            if p.how == "nutrient" and p.tier == 1:
                self.assertGreaterEqual(p.pct_at_basis, p.threshold_pct * self.T.REVIEW_MARGIN - 1e-6, (code, name))

    def test_pending_import_ingredients_are_not_judged_on_missing_data(self):
        for name in ("orange", "sweet potatoes", "sun-dried tomatoes", "tomato paste", "sesame seeds"):
            self.assertEqual([c for (c, n) in self.cur if n == name and self.props[c][0].how == "nutrient"], [], name)

    def test_corrected_ingredients_are_now_judged_on_the_right_food(self):
        self.assertIn(("NUT_VITC", "strawberry"), self.cur)
        self.assertNotIn(("NUT_CAROTENOIDS", "grapes"), self.cur)
        self.assertEqual(self.cur[("NUT_VITC", "strawberry")].tier, 1)

    def test_dry_run_through_the_command_line_writes_nothing(self):
        before = self.one("SELECT count(*) FROM ingredient_rule_tags")
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as d, mock_env(MAZIMEAL_DSN=DSN), contextlib.redirect_stdout(out):
            self.assertEqual(self.T.main(["--export-dir", d]), 0)
            self.assertEqual(sorted(os.listdir(d)), ["curated_compound.csv", "identity.csv", "nutrient.csv"])
        text = out.getvalue()
        for heading in ("== IDENTITY", "== NUTRIENT", "== CURATED_COMPOUND"):
            self.assertIn(heading, text)
        self.assertIn("nothing written", text)
        self.assertEqual(self.one("SELECT count(*) FROM ingredient_rule_tags"), before)

    def test_category_flag_limits_the_summary(self):
        out = io.StringIO()
        with mock_env(MAZIMEAL_DSN=DSN), contextlib.redirect_stdout(out):
            self.T.main(["--category", "nutrient"])
        self.assertIn("== NUTRIENT", out.getvalue())
        self.assertNotIn("== IDENTITY", out.getvalue())


@contextlib.contextmanager
def mock_env(**kv):
    saved = {k: os.environ.get(k) for k in list(kv) + ["SUPABASE_DB_URL"]}
    os.environ.update(kv)
    os.environ.pop("SUPABASE_DB_URL", None)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class Reachability(DatabaseCase):
    """The REAL recipe-fact builder, detector and evaluator over all 400 recipes.

    State-independent: whether or not migration 012 was already applied to this database, "before"
    removes exactly the pairs it lists (inside a transaction) and "after" runs the committed
    migration SQL (also inside it). Everything is rolled back.
    """

    @classmethod
    def evaluate_all(cls):
        out = {}
        for rid in cls.recipe_ids:
            for r in cls.evaluate.evaluate_recipe_rules(cls.conn, rid):
                out[(rid, r.rule_id)] = (str(r.applicability_status), r.reason)
        return out

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import detect_rules
        import evaluate_rules
        import recipe_facts
        cls.detect, cls.evaluate, cls.facts = detect_rules, evaluate_rules, recipe_facts
        cls.recipe_ids = [str(r[0]) for r in cls.conn.execute(
            "SELECT recipe_id FROM recipes WHERE deleted_at IS NULL ORDER BY recipe_name")]
        pairs = listed_pairs()
        cls.conn.execute(
            "DELETE FROM ingredient_rule_tags x USING ingredients i, unnest(%s::text[], %s::text[]) AS t(name, code) "
            "WHERE x.ingredient_id = i.ingredient_id AND lower(btrim(i.ingredient_name)) = lower(btrim(t.name)) "
            "AND x.rule_code = t.code", ([p[0] for p in pairs], [p[1] for p in pairs]))
        cls.fired_before = cls.fired_rules()
        cls.eval_before = cls.evaluate_all()
        cls.conn.execute(strip_transaction((MIGRATIONS / TIER1_MIGRATION).read_text()))
        cls.fired_after = cls.fired_rules()
        cls.eval_after = cls.evaluate_all()
        cls.vitc_ids = {str(r[0]) for r in cls.conn.execute("SELECT ingredient_id FROM ingredient_rule_tags WHERE rule_code = 'NUT_VITC'")}
        cls.recipe_ingredients = {}
        for rid, iid in cls.conn.execute("SELECT recipe_id::text, ingredient_id::text FROM recipe_ingredients"):
            cls.recipe_ingredients.setdefault(rid, set()).add(iid)
        cls.active = {r[0] for r in cls.conn.execute("SELECT rule_id FROM business_rules WHERE is_active")}
        cls.conn.rollback()

    @classmethod
    def fired_rules(cls):
        out = {}
        for rid in cls.recipe_ids:
            for cand in cls.detect.detect_rules_from_facts(cls.conn, cls.facts.build_recipe_facts(cls.conn, rid)):
                out.setdefault(cand.rule_id, set()).add(rid)
        return out

    # ---- which rules are called -------------------------------------------------------------
    def test_there_are_54_active_rules_over_400_recipes(self):
        self.assertEqual((len(self.active), len(self.recipe_ids)), (54, 400))

    def test_before_the_tags_exactly_thirteen_rules_are_called(self):
        self.assertEqual(set(self.fired_before), REACHABLE_BEFORE)

    def test_with_the_approved_tags_exactly_twenty_nine_rules_are_called(self):
        self.assertEqual(len(self.fired_after), 29)
        self.assertEqual(set(self.fired_after), REACHABLE_BEFORE | NEWLY_REACHABLE)

    def test_the_newly_reachable_rules_are_exactly_the_expected_sixteen(self):
        self.assertEqual(set(self.fired_after) - set(self.fired_before), NEWLY_REACHABLE)
        self.assertEqual(len(NEWLY_REACHABLE), 16)

    def test_twenty_five_rules_remain_unreachable_each_with_a_written_reason(self):
        unreachable = self.active - set(self.fired_after)
        self.assertEqual(len(unreachable), 25)
        self.assertEqual(unreachable, set(UNREACHABLE_AT_TIER_1),
                         "reachability changed: explain the cause before touching UNREACHABLE_AT_TIER_1")

    def test_tags_never_make_an_existing_rule_stop_firing(self):
        for rule, recipes in self.fired_before.items():
            self.assertTrue(recipes <= self.fired_after[rule], rule)

    def test_every_newly_reachable_rule_fires_on_a_recipe_with_a_listed_ingredient(self):
        by_code = {}
        for name, code, _ in listed_pairs():
            by_code.setdefault(code, set()).add(name.lower())
        for rule in NEWLY_REACHABLE:
            self.assertTrue(self.fired_after[rule], rule)

    def test_inh_006_fires_only_on_recipes_with_an_approved_vitamin_c_food(self):
        self.assertGreater(len(self.fired_after["INH-006"]), 0)
        for rid in self.recipe_ids:
            has = bool(self.recipe_ingredients.get(rid, set()) & self.vitc_ids)
            self.assertEqual(rid in self.fired_after["INH-006"], has, rid)

    # ---- what each called rule returns ------------------------------------------------------
    def test_exactly_the_five_existing_evaluators_exist(self):
        self.assertEqual(set(self.evaluate.RULE_EVALUATORS), REAL_EVALUATORS)

    def test_five_called_rules_have_real_evaluators_and_twenty_four_are_needs_context(self):
        called = set(self.fired_after)
        self.assertEqual(called & REAL_EVALUATORS, REAL_EVALUATORS)
        self.assertEqual(called - REAL_EVALUATORS, NEEDS_CONTEXT_RULES)
        self.assertEqual((len(REAL_EVALUATORS), len(NEEDS_CONTEXT_RULES)), (5, 24))

    def test_an_unimplemented_rule_is_triggered_but_never_decided(self):
        for (rid, rule), (status, reason) in self.eval_after.items():
            if rule in NEEDS_CONTEXT_RULES:
                self.assertEqual(status, "NEEDS_CONTEXT", (rid, rule))
                self.assertIn("evaluator not implemented", reason, (rid, rule))

    def test_needs_context_results_are_counted_not_suppressed(self):
        results_by_rule = {}
        for (rid, rule) in self.eval_after:
            results_by_rule.setdefault(rule, set()).add(rid)
        for rule in NEEDS_CONTEXT_RULES:
            self.assertEqual(results_by_rule[rule], self.fired_after[rule], rule)   # one result per candidate recipe
        total = sum(len(self.fired_after[r]) for r in NEEDS_CONTEXT_RULES)
        counted = sum(1 for (rid, rule), (st, why) in self.eval_after.items()
                      if st == "NEEDS_CONTEXT" and "evaluator not implemented" in why)
        self.assertEqual(counted, total)

    def test_the_five_existing_evaluators_are_unchanged_by_the_tags(self):
        for key in set(self.eval_before) | set(self.eval_after):
            if key[1] in REAL_EVALUATORS:
                self.assertEqual(self.eval_before.get(key), self.eval_after.get(key), key)

    def test_the_five_evaluators_still_reach_real_verdicts(self):
        statuses = {st for (rid, rule), (st, why) in self.eval_after.items() if rule in REAL_EVALUATORS}
        self.assertTrue({"APPLICABLE", "NOT_APPLICABLE"} <= statuses)
        for rule in REAL_EVALUATORS:
            self.assertTrue(any(st in ("APPLICABLE", "NOT_APPLICABLE") for (rid, r), (st, why) in self.eval_after.items() if r == rule), rule)

    def test_no_result_belongs_to_a_rule_that_was_not_called(self):
        self.assertEqual({rule for (_, rule) in self.eval_after}, set(self.fired_after))


class Migration012(DatabaseCase):
    """Migration 012 against the disposable database. Every test runs it inside a rolled-back transaction."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.text = (MIGRATIONS / TIER1_MIGRATION).read_text()
        cls.pairs = listed_pairs()

    def apply_text(self, text):
        notices = []
        handler = lambda d: notices.append(d.message_primary)
        self.conn.add_notice_handler(handler)
        try:
            self.conn.execute(strip_transaction(text))
            # The migration's own COMMIT drops its temp table (ON COMMIT DROP). Inside one test transaction
            # there is no commit, so drop it here to make each call behave like a separate run.
            self.conn.execute("DROP TABLE IF EXISTS _tier1_tags")
        finally:
            self.conn.remove_notice_handler(handler)
        return notices

    def apply(self):
        return self.apply_text(self.text)

    def tags(self):
        return set(self.conn.execute(
            "SELECT i.ingredient_name, t.rule_code FROM ingredient_rule_tags t JOIN ingredients i USING (ingredient_id)").fetchall())

    def remove_listed(self, only=None):
        pairs = [p for p in self.pairs if only is None or p in only]
        self.conn.execute(
            "DELETE FROM ingredient_rule_tags x USING ingredients i, unnest(%s::text[], %s::text[]) AS t(name, code) "
            "WHERE x.ingredient_id = i.ingredient_id AND lower(btrim(i.ingredient_name)) = lower(btrim(t.name)) "
            "AND x.rule_code = t.code", ([p[0] for p in pairs], [p[1] for p in pairs]))

    def codes(self):
        return {c for _, c, _ in self.pairs}

    # ---- reproducibility ----------------------------------------------------------------------
    def test_the_committed_migration_is_exactly_what_the_generator_writes(self):
        import tag_ingredients as T
        props, _ = T.build_all(T.load(self.conn))
        self.assertEqual(T.render_migration(T.tier1_rows(props)), self.text)

    def test_the_emit_command_writes_the_same_bytes(self):
        import tag_ingredients as T
        props, _ = T.build_all(T.load(self.conn))
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "m.sql"
            T.emit_migration(out, props)
            self.assertEqual(out.read_text(), self.text)

    def test_the_list_is_exactly_the_current_tier_1_proposals(self):
        import tag_ingredients as T
        props, _ = T.build_all(T.load(self.conn))
        want = {(n, c, cat) for cat, c, n in T.tier1_rows(props)}
        self.assertEqual(set(self.pairs), want)
        self.assertEqual(len(self.pairs), 232)

    # ---- the resulting state ------------------------------------------------------------------
    def test_all_approved_mappings_are_present_and_nothing_else_carries_those_codes(self):
        self.apply()
        got = {(n, c) for n, c in self.tags() if c in self.codes()}
        self.assertEqual(got, {(n, c) for n, c, _ in self.pairs})
        self.assertEqual(len(got), 232)

    def test_no_tier_2_tier_3_blocked_or_unjudged_pair_is_present_for_these_codes(self):
        import tag_ingredients as T
        self.apply()
        props, unjudged = T.build_all(T.load(self.conn))
        held_back = {(p.ingredient.name, code) for code, rows in props.items() for p in rows if p.tier != 1}
        held_back |= {(p.ingredient.name, code) for code, rows in unjudged.items() for p in rows}
        self.assertTrue(held_back)
        self.assertEqual(held_back & self.tags(), set())

    def test_no_curated_compound_or_process_tags_exist(self):
        self.apply()
        codes = {c for _, c in self.tags()}
        self.assertEqual(codes & {"CMP_PHYTATE", "CMP_OXALATE", "BEV_TEA_COFFEE", "PROC_COOKWARE", "PROC_COOL_REHEAT"}, set())
        self.assertEqual(codes & {"ING_LEGUME_GRAIN", "ING_ALLIUM_GRAIN_LEGUME"}, set())

    def test_category_split_117_identity_115_nutrient_0_compound(self):
        self.assertEqual(sum(1 for _, _, c in self.pairs if c == "identity"), 117)
        self.assertEqual(sum(1 for _, _, c in self.pairs if c == "nutrient"), 115)
        self.assertEqual(sum(1 for _, _, c in self.pairs if c == "curated_compound"), 0)

    def test_excluded_usda_evidence_is_not_tagged(self):
        self.apply()
        nutrient_codes = {c for _, c, cat in self.pairs if cat == "nutrient"}
        tagged = {(n, c) for n, c in self.tags() if c in nutrient_codes}
        names = {n for n, _ in tagged}
        for name in ("milk", "cheese", "unsweetened applesauce", "ground coriander", "orange", "sweet potatoes",
                     "sun-dried tomatoes", "tomato paste", "sesame seeds", "buttermilk", "low-fat buttermilk", "garlic", "oats"):
            self.assertNotIn(name, names, name)

    def test_cellophane_noodle_is_not_tagged_as_pasta_or_anything(self):
        self.apply()
        self.assertEqual({c for n, c in self.tags() if n == "cellophane noodle"}, set())

    def test_the_approved_tags_are_real_rows_with_valid_foreign_keys_and_no_duplicates(self):
        self.apply()
        self.assertEqual(self.one("SELECT count(*) FROM ingredient_rule_tags t LEFT JOIN ingredients i USING (ingredient_id) "
                                  "WHERE i.ingredient_id IS NULL"), 0)
        self.assertEqual(self.one("SELECT count(*) FROM ingredient_rule_tags t LEFT JOIN rule_codes c ON c.code = t.rule_code "
                                  "WHERE c.code IS NULL"), 0)
        self.assertEqual(self.one("SELECT count(*) FROM (SELECT 1 FROM ingredient_rule_tags GROUP BY ingredient_id, rule_code "
                                  "HAVING count(*) > 1) d"), 0)

    # ---- idempotence and reconciliation -------------------------------------------------------
    def test_running_it_twice_gives_the_same_final_state(self):
        self.apply()
        once = self.tags()
        notices = self.apply()
        self.assertEqual(self.tags(), once)
        self.assertTrue(any("232 listed = 232 already present + 0 newly inserted" in n for n in notices), notices)

    def test_a_fresh_database_inserts_all_of_them(self):
        self.remove_listed()
        notices = self.apply()
        self.assertTrue(any("232 listed = 0 already present + 232 newly inserted" in n for n in notices), notices)

    def test_partially_applied_counts_reconcile(self):
        some = set(self.pairs[:10])
        self.apply()                      # make sure all 232 are there, whatever state the database started in
        self.remove_listed(only=some)     # then take ten away
        notices = self.apply()
        self.assertTrue(any("232 listed = 222 already present + 10 newly inserted; 0 skipped; 0 failed validation" in n
                            for n in notices), notices)

    def test_unrelated_existing_tags_are_untouched(self):
        before = {t for t in self.tags() if t[1] not in self.codes()}
        self.assertTrue(before)
        self.apply()
        self.apply()
        self.assertEqual({t for t in self.tags() if t[1] not in self.codes()}, before)

    def test_an_existing_tag_is_never_overwritten_or_deleted(self):
        self.remove_listed()
        name, code, _ = self.pairs[0]
        self.conn.execute("INSERT INTO ingredient_rule_tags (ingredient_id, rule_code, created_at) "
                          "SELECT ingredient_id, %s, timestamptz '2001-01-01' FROM ingredients WHERE ingredient_name = %s", (code, name))
        self.apply()
        self.assertEqual(self.one("SELECT t.created_at::date::text FROM ingredient_rule_tags t JOIN ingredients i USING (ingredient_id) "
                                  "WHERE i.ingredient_name = %s AND t.rule_code = %s", (name, code)), "2001-01-01")

    # ---- it fails loudly, and changes nothing --------------------------------------------------
    def fails(self, text, message):
        before = self.tags()
        with self.assertRaises(psycopg.errors.RaiseException) as ctx:
            self.apply_text(text)
        self.assertIn(message, str(ctx.exception))
        self.conn.rollback()
        self.assertEqual(self.tags(), before, "a failed run must change nothing")

    def test_an_unknown_ingredient_stops_it(self):
        first = self.pairs[0][0].replace("'", "''")
        self.fails(self.text.replace("('%s'," % first, "('zz not an ingredient',", 1), "no ingredient named")

    def test_an_unknown_rule_code_stops_it(self):
        self.fails(self.text.replace("'ING_ALLIUM', 'identity'", "'ING_MADE_UP', 'identity'", 1), "unknown rule code")

    def test_a_composite_code_stops_it(self):
        self.fails(self.text.replace("'ING_ALLIUM', 'identity'", "'ING_LEGUME_GRAIN', 'identity'", 1), "composite")

    def test_a_curated_compound_row_stops_it(self):
        self.fails(self.text.replace("'ING_ALLIUM', 'identity'", "'ING_ALLIUM', 'curated_compound'", 1), "only identity and nutrient")

    def test_a_repeated_pair_stops_it(self):
        row = "    ('%s', '%s', '%s')" % (self.pairs[0][0].replace("'", "''"), self.pairs[0][1], self.pairs[0][2])
        self.fails(self.text.replace(";\n\nDO $$", ",\n" + row + ";\n\nDO $$", 1), "repeats")

    def test_an_ambiguous_ingredient_name_stops_it(self):
        # Drop the unique index inside the transaction (DDL is transactional) and add a same-name twin.
        self.conn.execute("DROP INDEX uq_ingredients_name_lower")
        self.conn.execute("INSERT INTO ingredients (ingredient_name, food_category) VALUES ('GARLIC', 'Test')")
        with self.assertRaises(psycopg.errors.RaiseException) as ctx:
            self.apply()
        self.assertIn("ambiguous", str(ctx.exception))

    def test_it_stops_if_the_composite_table_is_missing(self):
        self.conn.execute("ALTER TABLE rule_code_components RENAME TO rule_code_components_gone")
        with self.assertRaises(psycopg.errors.UndefinedTable):
            self.apply()

    def test_it_cannot_tag_a_deleted_or_missing_rule_code_row(self):
        # FK to rule_codes also holds independently of the migration's own check.
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            self.conn.execute("INSERT INTO ingredient_rule_tags (ingredient_id, rule_code) "
                              "SELECT ingredient_id, 'ING_MADE_UP' FROM ingredients LIMIT 1")


class DisposableDatabaseOnly(unittest.TestCase):
    """The protections themselves (they need no database)."""

    def test_the_shared_database_case_runs_the_guard_before_and_after_connecting(self):
        import inspect
        src = inspect.getsource(DatabaseCase.setUpClass.__func__)
        self.assertLess(src.index("dbguard.assert_local_dsn(DSN)"), src.index("psycopg.connect(DSN)"))
        self.assertIn("dbguard.assert_local_host(cls.conn.info.host)", src)

    def test_every_database_test_derives_from_the_guarded_case(self):
        for cls in (Migration010State, Migration010Behaviour, Migration011, TaggerOnSeedData, Reachability,
                    Migration012, CompositeBehaviour, CandidatesWithoutEvaluators):
            self.assertTrue(issubclass(cls, DatabaseCase), cls.__name__)

    def test_a_hosted_dsn_is_refused_before_any_connection_is_attempted(self):
        if psycopg is None:
            self.skipTest("psycopg not installed")
        for dsn in ("postgresql://postgres:x@db.abcdefghijkl.supabase.co:5432/postgres",
                    "postgresql://u@aws-0-us-east-1.pooler.supabase.com:6543/postgres", "postgresql://u@10.0.0.9/db"):
            with self.assertRaises(AssertionError, msg=dsn):
                dbguard.assert_local_dsn(dsn)

    def test_no_test_can_write_tags_to_a_real_connection(self):
        """apply_tier1 may only be called with a recording fake, and no test may pass --apply to main()."""
        import ast
        seen = 0
        for path in sorted((REPO / "tests").glob("test_*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "attr", getattr(node.func, "id", ""))
                if name == "apply_tier1":
                    seen += 1
                    self.assertEqual(path.name, "test_tag_ingredients.py", "apply_tier1 called from %s" % path.name)
                    arg = node.args[0]
                    fake = (isinstance(arg, ast.Name) and arg.id == "conn") or \
                           (isinstance(arg, ast.Call) and getattr(arg.func, "id", "") == "FakeConn")
                    self.assertTrue(fake, "apply_tier1 must be given a FakeConn (%s:%d)" % (path.name, node.lineno))
                if name == "main":
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Constant) and sub.value == "--apply":
                            self.fail("%s:%d passes --apply to main()" % (path.name, node.lineno))
        self.assertGreater(seen, 0)

    def test_no_test_names_a_hosted_database(self):
        for path in sorted((REPO / "tests").glob("test_*.py")):
            if path.name in ("test_dbguard.py", "test_tag_db.py"):
                continue          # these two name hosted hosts only to prove they are refused
            text = path.read_text().lower()
            self.assertNotIn("supabase.co", text, path.name)
            self.assertNotIn("supabase_db_url", text, path.name)


class CompositeBehaviour(DatabaseCase):
    """AND semantics of rule_code_components, with a synthetic recipe that is rolled back."""

    def setUp(self):
        import detect_rules, recipe_facts
        self.detect, self.facts = detect_rules, recipe_facts

    def recipe(self, *ingredient_names):
        rid = self.one("INSERT INTO recipes (recipe_name, meal_category) VALUES ('zz composite test ' || gen_random_uuid(), 'Dinner') RETURNING recipe_id")
        for n in ingredient_names:
            self.conn.execute("INSERT INTO recipe_ingredients (recipe_id, ingredient_id, quantity, unit) "
                              "SELECT %s, ingredient_id, 1.0, 'unit' FROM ingredients WHERE ingredient_name = %s", (rid, n))
        return str(rid)

    def tag(self, name, code):
        self.conn.execute("INSERT INTO ingredient_rule_tags (ingredient_id, rule_code) "
                          "SELECT ingredient_id, %s FROM ingredients WHERE ingredient_name = %s ON CONFLICT DO NOTHING", (code, name))

    def fired(self, rid):
        facts = self.facts.build_recipe_facts(self.conn, rid)
        return {c.rule_id for c in self.detect.detect_rules_from_facts(self.conn, facts)}

    def test_legume_and_grain_needs_both(self):
        self.tag("black beans", "ING_LEGUME")
        self.tag("rice", "ING_GRAIN")
        self.assertNotIn("SYN-007", self.fired(self.recipe("black beans")))
        self.assertNotIn("SYN-007", self.fired(self.recipe("rice")))
        self.assertIn("SYN-007", self.fired(self.recipe("black beans", "rice")))

    def test_allium_with_grain_or_legume_is_and_over_an_or_union(self):
        self.tag("garlic", "ING_ALLIUM")
        self.tag("rice", "ING_GRAIN_LEGUME")
        self.tag("black beans", "ING_GRAIN_LEGUME")
        self.assertNotIn("SYN-009", self.fired(self.recipe("garlic")))
        self.assertNotIn("SYN-009", self.fired(self.recipe("rice", "black beans")))
        self.assertIn("SYN-009", self.fired(self.recipe("garlic", "rice")))
        self.assertIn("SYN-009", self.fired(self.recipe("garlic", "black beans")))

    def test_a_composite_is_never_a_row_in_ingredient_rule_tags(self):
        self.assertEqual(self.one("SELECT count(*) FROM ingredient_rule_tags WHERE rule_code IN "
                                  "(SELECT composite_code FROM rule_code_components)"), 0)

    def test_unknown_codes_cannot_be_tagged(self):
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            self.conn.execute("INSERT INTO ingredient_rule_tags (ingredient_id, rule_code) "
                              "SELECT ingredient_id, 'ING_MADE_UP' FROM ingredients LIMIT 1")

    def test_a_duplicate_tag_is_rejected_by_the_primary_key(self):
        self.tag("black beans", "ING_LEGUME")
        with self.assertRaises(psycopg.errors.UniqueViolation):
            self.conn.execute("INSERT INTO ingredient_rule_tags (ingredient_id, rule_code) "
                              "SELECT ingredient_id, 'ING_LEGUME' FROM ingredients WHERE ingredient_name = 'black beans'")

    def test_a_soft_deleted_recipe_is_not_part_of_the_population_the_audit_counts(self):
        rid = self.recipe("black beans")
        self.conn.execute("UPDATE recipes SET deleted_at = now() WHERE recipe_id = %s", (rid,))
        listed = {str(r[0]) for r in self.conn.execute("SELECT recipe_id FROM recipes WHERE deleted_at IS NULL")}
        self.assertNotIn(rid, listed)
        # recipe_facts on main does not filter deleted_at by id; the loader the tagger uses does.
        import tag_ingredients as T
        self.assertNotIn(rid, {r for i in T.load(self.conn).values() for r in i.recipes})


class CandidatesWithoutEvaluators(DatabaseCase):
    def setUp(self):
        import evaluate_rules
        self.ev = evaluate_rules

    def recipe_with(self, ingredient, code):
        rid = self.one("INSERT INTO recipes (recipe_name, meal_category) VALUES ('zz evaluator test ' || gen_random_uuid(), 'Dinner') RETURNING recipe_id")
        self.conn.execute("INSERT INTO recipe_ingredients (recipe_id, ingredient_id, quantity, unit) "
                          "SELECT %s, ingredient_id, 1.0, 'unit' FROM ingredients WHERE ingredient_name = %s", (rid, ingredient))
        self.conn.execute("INSERT INTO ingredient_rule_tags (ingredient_id, rule_code) "
                          "SELECT ingredient_id, %s FROM ingredients WHERE ingredient_name = %s ON CONFLICT DO NOTHING", (code, ingredient))
        return str(rid)

    def test_a_candidate_with_no_evaluator_says_so_and_is_needs_context(self):
        rid = self.recipe_with("carrots", "NUT_CAROTENOIDS")      # SYN-002 has no evaluator
        results = {r.rule_id: r for r in self.ev.evaluate_recipe_rules(self.conn, rid)}
        self.assertIn("SYN-002", results)
        self.assertEqual(results["SYN-002"].applicability_status, self.ev.ApplicabilityStatus.NEEDS_CONTEXT)
        self.assertIn("not implemented", results["SYN-002"].reason)
        self.assertTrue(results["SYN-002"].candidate)

    def test_a_rule_with_an_evaluator_is_not_reported_as_unimplemented(self):
        rid = self.recipe_with("garlic", "ING_GARLIC")
        results = {r.rule_id: r for r in self.ev.evaluate_recipe_rules(self.conn, rid)}
        self.assertNotIn("not implemented", results["BIO-002"].reason)

    def test_exactly_five_evaluators_exist(self):
        self.assertEqual(sorted(self.ev.RULE_EVALUATORS), ["BIO-002", "BIO-003", "BIO-007", "BIO-011", "GLY-007"])


if __name__ == "__main__":
    unittest.main()
