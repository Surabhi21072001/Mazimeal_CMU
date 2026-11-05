"""Integration tests run only on explicitly enabled, disposable local PostgreSQL.

All test writes roll back. Never run against a shared or production database.
"""
import contextlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from manage import bootstrap, connection_settings, execute_sql_file, MIGRATION, recipe_packet, report, external_ids
from recipe_facts import build_recipe_facts, RecipeNotFound


@unittest.skipUnless(os.environ.get('MAZIMEAL_RUN_DB_TESTS')=='1','Set MAZIMEAL_RUN_DB_TESTS=1 for the disposable database')
class PostgresIntegration(unittest.TestCase):
    def setUp(self):
        self.conn = psycopg.connect(connection_settings())
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)
        if self.conn.info.host not in ('127.0.0.1','localhost','::1') or self.conn.info.dbname != 'mazimeal_integration':
            self.fail('Refusing tests outside local mazimeal_integration')

    def scalar(self, query, params=()):
        return self.conn.execute(query,params).fetchone()[0]

    def fixture(self):
        """Two completely known ingredients, 100 g each, two servings."""
        rid=self.scalar("INSERT INTO recipes(recipe_name,meal_category,servings) VALUES ('Data test fixture','Dinner',2) RETURNING recipe_id")
        for name in ['Data test one','Data test two']:
            ing=self.scalar("INSERT INTO ingredients(ingredient_name,food_category) VALUES (%s,'Test') RETURNING ingredient_id",(name,))
            self.conn.execute("INSERT INTO ingredient_source_map(ingredient_id,source_id,source_record_id) VALUES (%s,'usda_sr_legacy','test')",(ing,))
            self.conn.execute("INSERT INTO ingredient_nutrition(ingredient_id,nutrient_id,value_per_100g,unit) VALUES (%s,'Iron',2,'mg')",(ing,))
            self.conn.execute("INSERT INTO de_mapping_reviews(ingredient_id,source_id,review_status,reviewed_by,reviewed_at) VALUES (%s,'usda_sr_legacy','approved','test',now())",(ing,))
            line=self.scalar("INSERT INTO recipe_ingredients(recipe_id,ingredient_id,quantity,unit,quantity_g,grams_source,quantity_aligned) VALUES (%s,%s,100,'g',100,'manual',true) RETURNING line_id",(rid,ing))
            self.conn.execute("INSERT INTO de_line_reviews(line_id,quantity_review_status,reviewed_by,reviewed_at) VALUES (%s,'approved','test',now())",(line,))
        self.conn.execute("INSERT INTO de_recipe_reviews(recipe_id,review_status,source_reference,reviewed_by,reviewed_at) VALUES (%s,'approved','Test source','test',now())",(rid,))
        return rid

    def nutrient(self,rid,nutrient='Iron'):
        return self.conn.execute('SELECT ready,verified_per_serving,lines_with_nutrient FROM de_recipe_nutrient_readiness WHERE recipe_id=%s AND nutrient_id=%s',(rid,nutrient)).fetchone()

    def test_current_seed_and_multi_source_schema(self):
        self.assertEqual(self.scalar('SELECT count(*) FROM recipes'),400)
        self.assertEqual(self.scalar('SELECT count(*) FROM business_rules'),54)
        self.assertEqual(self.scalar('SELECT count(*) FROM user_profile'),0)
        self.assertEqual(self.scalar('SELECT count(*) FROM de_recipe_nutrient_readiness WHERE ready'),0)

    def test_report_uses_exact_shared_seed_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            result=report(self.conn,Path(directory))
            self.assertEqual(result['recipes_reported'],50)
            self.assertEqual(result['missing_seed_external_ids'],[])
            self.assertEqual(result['ingredient_lines'],469)
            self.assertEqual(result['ready_nutrient_rows'],0)

    def test_all_fifty_recipe_packets_keep_enriched_team_contract(self):
        ids=self.conn.execute('SELECT recipe_id FROM recipes WHERE external_source_id=ANY(%s)',(external_ids(),)).fetchall()
        self.assertEqual(len(ids),50)
        for (rid,) in ids:
            packet=recipe_packet(self.conn,str(rid))
            self.assertEqual(packet['contract_version'],'2.0')
            for evaluation in packet['evaluations']:
                self.assertIn('matched_on',evaluation)
                self.assertIn('evidence_tier',evaluation)
            self.assertTrue(all(n['verified_per_serving'] is None for n in packet['nutrient_readiness']))

    def test_complete_reviewed_recipe_computes_without_double_counting(self):
        rid=self.fixture()
        ing=self.scalar('SELECT ingredient_id FROM recipe_ingredients WHERE recipe_id=%s LIMIT 1',(rid,))
        self.conn.execute("INSERT INTO ingredient_nutrition(ingredient_id,nutrient_id,value_per_100g,unit,source_id) VALUES (%s,'Iron',999,'mg','mazi_estimate')",(ing,))
        ready,value,covered=self.nutrient(rid)
        self.assertTrue(ready)
        self.assertEqual(float(value),2)
        self.assertEqual(covered,2)

    def test_missing_nutrient_is_not_zero_or_partial_total(self):
        rid=self.fixture()
        ing=self.scalar('SELECT ingredient_id FROM recipe_ingredients WHERE recipe_id=%s LIMIT 1',(rid,))
        self.conn.execute("DELETE FROM ingredient_nutrition WHERE ingredient_id=%s AND nutrient_id='Iron'",(ing,))
        ready,value,covered=self.nutrient(rid)
        self.assertFalse(ready)
        self.assertIsNone(value)
        self.assertEqual(covered,1)

    def test_true_zero_remains_zero(self):
        rid=self.fixture()
        self.conn.execute("UPDATE ingredient_nutrition SET value_per_100g=0 WHERE ingredient_id IN (SELECT ingredient_id FROM recipe_ingredients WHERE recipe_id=%s)",(rid,))
        self.assertTrue(self.nutrient(rid)[0])
        self.assertEqual(float(self.nutrient(rid)[1]),0)

    def test_mixed_units_block_total(self):
        rid=self.fixture()
        ing=self.scalar('SELECT ingredient_id FROM recipe_ingredients WHERE recipe_id=%s LIMIT 1',(rid,))
        self.conn.execute("UPDATE ingredient_nutrition SET unit='mcg' WHERE ingredient_id=%s",(ing,))
        self.assertFalse(self.nutrient(rid)[0])
        self.assertIsNone(self.nutrient(rid)[1])

    def test_higher_precedence_source_needs_its_own_review(self):
        rid=self.fixture()
        ing=self.scalar('SELECT ingredient_id FROM recipe_ingredients WHERE recipe_id=%s LIMIT 1',(rid,))
        self.conn.execute("INSERT INTO data_sources(source_id,source_name,precedence) VALUES ('test_source','Test',1)")
        self.conn.execute("INSERT INTO ingredient_nutrition(ingredient_id,nutrient_id,value_per_100g,unit,source_id) VALUES (%s,'Iron',10,'mg','test_source')",(ing,))
        self.assertFalse(self.nutrient(rid)[0])
        self.assertIsNone(self.nutrient(rid)[1])

    def test_mapping_edit_resets_approval(self):
        rid=self.fixture()
        self.conn.execute("UPDATE ingredient_source_map SET source_record_id='different' WHERE ingredient_id IN (SELECT ingredient_id FROM recipe_ingredients WHERE recipe_id=%s)",(rid,))
        self.assertFalse(self.nutrient(rid)[0])

    def test_ingredient_rename_invalidates_mapping_and_recipe_review(self):
        rid=self.fixture()
        ing=self.scalar('SELECT ingredient_id FROM recipe_ingredients WHERE recipe_id=%s LIMIT 1',(rid,))
        self.conn.execute("UPDATE ingredients SET ingredient_name='Changed identity' WHERE ingredient_id=%s",(ing,))
        self.assertFalse(self.nutrient(rid)[0])
        self.assertEqual(self.scalar('SELECT review_status FROM de_mapping_reviews WHERE ingredient_id=%s',(ing,)),'pending_review')

    def test_source_provenance_change_requires_new_review(self):
        rid=self.fixture()
        line=self.scalar('SELECT line_id FROM recipe_ingredients WHERE recipe_id=%s LIMIT 1',(rid,))
        self.conn.execute("INSERT INTO de_line_provenance(line_id,raw_quantity_text) VALUES (%s,'2 cups')",(line,))
        self.assertFalse(self.nutrient(rid)[0])

    def test_plausible_ui_review_does_not_approve_nutrients(self):
        # Stand-in only for migration 001's UUID helper, rolled back with this test.
        self.conn.execute('CREATE FUNCTION public.gen_ulid() RETURNS uuid LANGUAGE sql AS $$ SELECT gen_random_uuid() $$')
        execute_sql_file(self.conn,'schema/migrations/003_nutrition_reviews.sql')
        rid=self.scalar('SELECT recipe_id FROM recipes WHERE external_source_id=%s',(external_ids()[0],))
        self.conn.execute("INSERT INTO recipe_nutrition_reviews(recipe_id,verdict,reviewer) VALUES (%s,'plausible','private-test-identity')",(rid,))
        with tempfile.TemporaryDirectory() as directory:
            report(self.conn,Path(directory))
            export=(Path(directory)/'nutrition_review_queue.json').read_text()
            self.assertIn('plausible',export)
            self.assertNotIn('private-test-identity',export)
        self.assertFalse(self.nutrient(rid)[0])

    def test_line_edit_resets_line_and_recipe_review(self):
        rid=self.fixture()
        self.conn.execute('UPDATE recipe_ingredients SET quantity_g=200 WHERE recipe_id=%s',(rid,))
        self.assertFalse(self.nutrient(rid)[0])
        self.assertEqual(self.scalar('SELECT review_status FROM de_recipe_reviews WHERE recipe_id=%s',(rid,)),'pending_review')
        self.assertEqual(self.scalar("SELECT count(*) FROM de_line_reviews lr JOIN recipe_ingredients ri USING(line_id) WHERE ri.recipe_id=%s AND lr.quantity_review_status='approved'",(rid,)),0)

    def test_serving_and_instruction_changes_invalidate_recipe_review(self):
        rid=self.fixture()
        self.conn.execute('UPDATE recipes SET servings=3 WHERE recipe_id=%s',(rid,))
        self.assertFalse(self.nutrient(rid)[0])
        self.conn.execute("UPDATE de_recipe_reviews SET review_status='approved',reviewed_by='test',reviewed_at=now() WHERE recipe_id=%s",(rid,))
        self.conn.execute("INSERT INTO recipe_steps(recipe_id,step_number,instruction) VALUES (%s,1,'Cook ingredients.')",(rid,))
        self.assertFalse(self.nutrient(rid)[0])

    def test_deleting_ingredient_does_not_make_recipe_look_complete(self):
        rid=self.fixture()
        line=self.scalar('SELECT line_id FROM recipe_ingredients WHERE recipe_id=%s LIMIT 1',(rid,))
        self.conn.execute('DELETE FROM recipe_ingredients WHERE line_id=%s',(line,))
        self.assertFalse(self.nutrient(rid)[0])

    def test_unknown_alignment_blocks_even_with_reviews(self):
        rid=self.fixture()
        self.conn.execute('UPDATE recipe_ingredients SET quantity_aligned=NULL WHERE recipe_id=%s',(rid,))
        self.conn.execute("UPDATE de_line_reviews SET quantity_review_status='approved',reviewed_by='test',reviewed_at=now() WHERE line_id IN (SELECT line_id FROM recipe_ingredients WHERE recipe_id=%s)",(rid,))
        self.conn.execute("UPDATE de_recipe_reviews SET review_status='approved',reviewed_by='test',reviewed_at=now() WHERE recipe_id=%s",(rid,))
        self.assertFalse(self.nutrient(rid)[0])

    def test_rerun_preserves_reviews_ids_and_team_profile(self):
        rid=self.fixture()
        user=self.scalar("INSERT INTO user_profile(name,age_years,sex) VALUES ('Integration fixture',30,'other') RETURNING user_id")
        self.conn.execute("INSERT INTO user_nutrient_targets(user_id,nutrient_id,daily_target,unit) VALUES (%s,'Iron',8,'mg')",(user,))
        execute_sql_file(self.conn,MIGRATION)
        self.assertTrue(self.nutrient(rid)[0])
        self.assertEqual(self.scalar('SELECT daily_target FROM user_nutrient_targets WHERE user_id=%s',(user,)),8)

    def test_readiness_views_are_invoker_security(self):
        options=self.scalar("SELECT reloptions FROM pg_class WHERE oid='de_recipe_nutrient_readiness'::regclass")
        self.assertIn('security_invoker=true',options)
        self.assertTrue(self.scalar("SELECT relrowsecurity FROM pg_class WHERE oid='de_recipe_reviews'::regclass"))

    def test_current_backend_adapter_reads_seed_recipes(self):
        from app import supabase_repo
        @contextlib.contextmanager
        def connect():
            yield self.conn
        with patch.object(supabase_repo,'_connect',connect):
            adapter=supabase_repo.SupabaseRepo(None)
            self.assertEqual(adapter.seed_recipes()['in_database'],50)
            rid=str(self.scalar('SELECT recipe_id FROM recipes WHERE external_source_id=%s',(external_ids()[0],)))
            recipe=adapter.recipe(rid)
            self.assertEqual(recipe['db_recipe_id'],rid)
            self.assertIn('provenance',recipe)
            self.assertIn('matched_rules',recipe)

    def test_bootstrap_refuses_existing_database(self):
        with self.assertRaisesRegex(ValueError,'EMPTY'):
            bootstrap(self.conn)
