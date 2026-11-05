"""Database-reader regressions; preserve the team's enriched rule responses."""
import sqlite3
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from recipe_facts import build_recipe_facts, RecipeNotFound
from detect_rules import detect_rules_from_facts


class ReaderRegressionTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        self.conn.executescript('''
            CREATE TABLE recipes(recipe_id TEXT,recipe_name TEXT,deleted_at TEXT);
            CREATE TABLE ingredients(ingredient_id TEXT,ingredient_name TEXT);
            CREATE TABLE recipe_ingredients(recipe_id TEXT,ingredient_id TEXT);
            CREATE TABLE ingredient_rule_tags(ingredient_id TEXT,rule_code TEXT);
            CREATE TABLE business_rules(rule_id TEXT,rule_name TEXT,automation_status TEXT,trigger_code TEXT,is_active BOOLEAN);
            CREATE TABLE recipe_steps(recipe_id TEXT,step_number INTEGER,instruction TEXT);
        ''')
        self.conn.execute("INSERT INTO recipes VALUES ('recipe','Pending edit',NULL)")
        self.conn.execute("INSERT INTO ingredients VALUES ('ingredient','pasta')")
        self.conn.execute("INSERT INTO recipe_ingredients VALUES ('recipe','ingredient')")
        self.conn.execute("INSERT INTO ingredient_rule_tags VALUES ('ingredient','ING_PASTA')")
        self.conn.execute("INSERT INTO business_rules VALUES ('GLY-007','Use al dente pasta','recipe_safe','ING_PASTA',TRUE)")

    def test_minimal_schema_reads_keep_pending_transaction(self):
        facts = build_recipe_facts(self.conn,'recipe')
        self.assertEqual(facts.recipe_name,'Pending edit')
        self.assertEqual(detect_rules_from_facts(self.conn,facts)[0].rule_id,'GLY-007')
        self.assertTrue(self.conn.in_transaction)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM recipes').fetchone()[0],1)

    def test_deleted_recipe_is_not_loaded(self):
        self.conn.execute("UPDATE recipes SET deleted_at='2026-11-05'")
        with self.assertRaises(RecipeNotFound):
            build_recipe_facts(self.conn,'recipe')

    def test_instruction_evidence_keeps_original_step_numbers(self):
        self.conn.executemany('INSERT INTO recipe_steps VALUES (?,?,?)',
            [('recipe',2,'Boil water.'),('recipe',5,'Cook pasta al dente.')])
        self.assertEqual(build_recipe_facts(self.conn,'recipe').instructions,
            '2. Boil water.\n5. Cook pasta al dente.')
