#!/usr/bin/env python3
"""Static data tests for the USDA corrections, the generated tag seed and the migrations.

No database: the SQL files are parsed as text (and, for the VALUES lists, executed in
an in-memory SQLite table so quoting is handled by a real SQL parser).

    python3 -m unittest tests.test_tag_data -v
"""
from __future__ import annotations

import ast
import csv
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SEED = REPO / "schema" / "seed"
MIGRATIONS = REPO / "schema" / "migrations"
sys.path.insert(0, str(REPO / "scripts"))

import import_rules  # noqa: E402
import tag_config as C  # noqa: E402
import tag_ingredients as T  # noqa: E402


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def alias_pairs() -> list[tuple[str, str]]:
    """Every (key, value) written in match_usda.ALIASES, without importing the module
    (it needs pandas/rapidfuzz and a USDA download)."""
    tree = ast.parse(read(REPO / "scripts" / "match_usda.py"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "ALIASES":
            return [(k.value, v.value) for k, v in zip(node.value.keys, node.value.values)]
    raise AssertionError("ALIASES not found in scripts/match_usda.py")


def fix_rows() -> list[dict]:
    """The VALUES list of migration 010, parsed by SQLite."""
    text = read(MIGRATIONS / "010_fix_usda_matches.sql")
    stmt = re.search(r"INSERT INTO _usda_fix VALUES(.*?);\n", text, re.S).group(1)
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE f (ingredient_name, expected_record, new_record, new_description, new_category, donor_name)")
    db.execute("INSERT INTO f VALUES" + stmt)
    cols = ["ingredient_name", "expected_record", "new_record", "new_description", "new_category", "donor_name"]
    return [dict(zip(cols, r)) for r in db.execute("SELECT * FROM f")]


def rule_trigger_codes() -> set[str]:
    """trigger_code of every rule in the generated business_rules seed (executed in SQLite)."""
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE business_rules (rule_id, rule_name, rule_category, rule_type, trigger_food_or_pattern, "
               "trigger_code, target_nutrient_or_outcome, target_code, action, action_code, mechanism, "
               "recipe_engine_instruction, conditions_and_limits, population_scope, evidence_tier, evidence_summary, "
               "automation_status, source_title, source_type, source_url, review_date, is_active)")
    for block in read(SEED / "business_rules.sql").split("INSERT INTO business_rules")[1:]:
        db.execute("INSERT INTO business_rules" + block.split("\nON CONFLICT")[0].replace("now()", "''"))
    return {r[0] for r in db.execute("SELECT trigger_code FROM business_rules WHERE trigger_code IS NOT NULL")}


def seeded_rule_codes() -> set[str]:
    return set(re.findall(r"VALUES \('([A-Z_0-9]+)', '", read(SEED / "rule_codes.sql")))


def composites() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    sql = read(MIGRATIONS / "009_composite_trigger_codes.sql")
    block = sql.split("INSERT INTO rule_code_components", 1)[1]
    for comp, part in re.findall(r"\('([A-Z_]+)',\s+'([A-Z_]+)'\)", block):
        out.setdefault(comp, set()).add(part)
    return out


def codes_added_by_009() -> set[str]:
    sql = read(MIGRATIONS / "009_composite_trigger_codes.sql")
    head = sql.split("CREATE TABLE IF NOT EXISTS rule_code_components")[0]
    return set(re.findall(r"\('(ING_[A-Z_]+)',\s*'ING'", head))


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9%\-]+", text.lower()))



def tier1_rows() -> list[tuple[str, str, str]]:
    """(ingredient_name, rule_code, category) from migration 012's VALUES list, parsed by SQLite."""
    text = read(MIGRATIONS / "012_apply_tier1_ingredient_tags.sql")
    stmt = re.search(r"INSERT INTO _tier1_tags \(ingredient_name, rule_code, category\) VALUES(.*?);\n", text, re.S).group(1)
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE t (ingredient_name, rule_code, category)")
    db.execute("INSERT INTO t VALUES" + stmt)
    return [tuple(r) for r in db.execute("SELECT * FROM t")]


# ---------------------------------------------------------------------------
class UsdaAliases(unittest.TestCase):
    def test_no_key_maps_to_two_different_values(self):
        seen: dict[str, str] = {}
        for k, v in alias_pairs():
            if k in seen:
                self.assertEqual(seen[k], v, "alias %r is defined twice with different values; the later one wins silently" % k)
            seen[k] = v

    def test_keys_are_lowercase_and_values_non_empty(self):
        for k, v in alias_pairs():
            self.assertEqual(k, k.lower(), k)
            self.assertTrue(v.strip(), k)

    OATS = "cereals oats regular and quick not fortified dry"

    def test_every_oat_name_points_at_the_cereal_not_the_breakfast_bar(self):
        d = dict(alias_pairs())
        for k in ("oats", "rolled oats", "quick oats", "old fashioned oats", "robin hood oats", "old mill oats",
                  "oatmeal", "quick-cooking oatmeal", "oats, rolled, dry"):
            self.assertEqual(d[k], self.OATS, k)

    def test_milk_names_the_whole_milk_record_not_buttermilk(self):
        d = dict(alias_pairs())
        self.assertIn("3.25%", d["milk"])
        self.assertIn("3.25%", d["whole milk"])
        self.assertNotIn("buttermilk", d["milk"])
        self.assertEqual(d["buttermilk"], "milk buttermilk fluid")

    def test_each_corrected_food_has_an_explicit_alias(self):
        d = dict(alias_pairs())
        self.assertEqual(d["tomato paste"], "tomato products canned paste without salt added")
        self.assertIn("unprepared", d["sweet potatoes"])
        self.assertIn("unprepared", d["sweet potato"])
        for k in ("grapes", "orange", "strawberry", "sun-dried tomatoes", "parsley flakes", "dried parsley flakes"):
            self.assertIn(k, d)
        self.assertNotIn("leaves", d["grapes"])
        self.assertNotIn("bars", d["oats"])

    def test_migration_010_descriptions_contain_every_word_of_the_alias(self):
        """The alias that would regenerate a match and the migration that corrects the data must agree."""
        aliases = dict(alias_pairs())
        checked = 0
        for row in fix_rows():
            alias = aliases.get(row["ingredient_name"].lower())
            if alias is None:
                continue
            checked += 1
            missing = tokens(alias) - tokens(row["new_description"])
            self.assertEqual(missing, set(), "%s: alias words not in %r" % (row["ingredient_name"], row["new_description"]))
        self.assertGreaterEqual(checked, 12)


class Migration010(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = fix_rows()
        cls.text = read(MIGRATIONS / "010_fix_usda_matches.sql")

    def test_fifteen_ingredients_nine_distinct_corrections(self):
        self.assertEqual(len(self.rows), 15)
        self.assertEqual(len({r["new_record"] for r in self.rows}), 9)

    def test_names_are_unique(self):
        names = [r["ingredient_name"] for r in self.rows]
        self.assertEqual(len(names), len(set(names)))

    def test_every_row_changes_something_and_ids_are_numeric(self):
        for r in self.rows:
            self.assertTrue(r["expected_record"].isdigit() and r["new_record"].isdigit(), r)
            self.assertNotEqual(r["expected_record"], r["new_record"], r["ingredient_name"])

    def test_one_record_has_one_description_and_one_category(self):
        by_record: dict[str, set] = {}
        for r in self.rows:
            by_record.setdefault(r["new_record"], set()).add((r["new_description"], r["new_category"]))
        for rec, variants in by_record.items():
            self.assertEqual(len(variants), 1, rec)

    def test_the_seven_oat_names_share_one_record_and_one_donor(self):
        oats = [r for r in self.rows if r["new_record"] == "173904"]
        self.assertEqual(len(oats), 7)
        self.assertEqual({r["donor_name"] for r in oats}, {"quick oats"})
        self.assertEqual({r["expected_record"] for r in oats}, {"169063"})  # 'Breakfast bars, oats, sugar, raisins'

    def test_donor_rows_copy_data_that_exists_pending_rows_have_no_donor(self):
        pending = {r["ingredient_name"] for r in self.rows if r["donor_name"] is None}
        self.assertEqual(pending, {"orange", "sweet potatoes", "sun-dried tomatoes", "tomato paste", "sesame seeds"})

    def test_a_donor_is_never_itself_corrected(self):
        corrected = {r["ingredient_name"] for r in self.rows}
        for r in self.rows:
            if r["donor_name"]:
                self.assertNotIn(r["donor_name"], corrected)

    def test_the_wrong_records_are_the_ones_the_audit_found(self):
        wrong = {r["ingredient_name"]: r["expected_record"] for r in self.rows}
        self.assertEqual(wrong["grapes"], "168575")        # Grape leaves, raw
        self.assertEqual(wrong["orange"], "170502")        # Tomatoes, orange, raw
        self.assertEqual(wrong["strawberry"], "173045")    # Guavas, strawberry, raw
        self.assertEqual(wrong["sweet potatoes"], "169303")  # Sweet potato leaves, raw
        self.assertEqual(wrong["tomato paste"], "170460")  # canned puree
        self.assertEqual(wrong["sesame seeds"], "167557")  # rice cake (migration 007 fixed only usda_fdc_id)

    def test_new_descriptions_say_what_the_ingredient_is(self):
        want = {"grapes": "grapes", "orange": "oranges", "strawberry": "strawberries", "sweet potatoes": "sweet potato",
                "sun-dried tomatoes": "sun-dried", "tomato paste": "paste", "parsley flakes": "parsley",
                "sesame seeds": "sesame"}
        for r in self.rows:
            if r["ingredient_name"] in want:
                self.assertIn(want[r["ingredient_name"]], r["new_description"].lower(), r["ingredient_name"])
        for r in self.rows:
            self.assertNotIn("leaves", r["new_description"].lower())

    def test_it_fails_loudly_rather_than_guessing(self):
        self.assertIn("RAISE EXCEPTION", self.text)
        self.assertIn("already corrected", self.text)       # idempotent
        self.assertTrue(self.text.rstrip().endswith("COMMIT;"))
        self.assertIn("BEGIN;", self.text)

    def test_it_types_no_nutrient_number(self):
        # Values are copied from a record already loaded, or left for the import. Never written here.
        self.assertNotRegex(self.text, r"INSERT INTO ingredient_nutrition\s*\([^)]*\)\s*VALUES")
        self.assertIn("SELECT v_id, nutrient_id, value_per_100g", self.text)

    def test_unique_fdc_id_constraint_is_respected(self):
        self.assertIn("ingredients.usda_fdc_id is unique where set", self.text)
        self.assertRegex(self.text, r"THEN NULL ELSE r\.new_record::bigint END")

    def test_sources_it_does_not_change_are_documented(self):
        for word in ("milk", "cheese", "applesauce", "blueberries"):
            self.assertIn(word, self.text)


class Migration011(unittest.TestCase):
    def setUp(self):
        self.text = read(MIGRATIONS / "011_retract_cellophane_pasta_tag.sql")

    def test_it_deletes_exactly_one_pair(self):
        self.assertEqual(len(re.findall(r"\bDELETE\b", self.text)), 1)
        self.assertIn("ingredient_name = 'cellophane noodle'", self.text)
        self.assertIn("rule_code = 'ING_PASTA'", self.text)

    def test_it_is_guarded_and_transactional(self):
        self.assertIn("nothing to do", self.text)
        self.assertIn("BEGIN;", self.text)
        self.assertTrue(self.text.rstrip().endswith("COMMIT;"))

    def test_it_never_touches_other_tables(self):
        self.assertNotRegex(self.text, r"\b(UPDATE|TRUNCATE|DROP|ALTER)\b")


class MigrationNumbering(unittest.TestCase):
    def test_no_two_migrations_share_a_number(self):
        numbers = [p.name.split("_", 1)[0] for p in MIGRATIONS.glob("*.sql")]
        self.assertEqual(len(numbers), len(set(numbers)), sorted(numbers))

    def test_numbers_are_contiguous(self):
        nums = sorted(int(p.name.split("_", 1)[0]) for p in MIGRATIONS.glob("*.sql"))
        self.assertEqual(nums, list(range(1, len(nums) + 1)))


class GeneratedTagSeed(unittest.TestCase):
    def test_cellophane_noodle_is_no_longer_tagged_as_pasta(self):
        seed = read(SEED / "ingredient_rule_tags.sql")
        self.assertNotIn("cellophane", seed.lower())

    def test_it_moved_to_the_review_list_with_the_reason(self):
        with open(SEED / "ingredient_rule_tags_review.csv", encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        hit = [r for r in rows if r and r[0] == "cellophane noodle"]
        self.assertEqual(len(hit), 1)
        self.assertEqual(hit[0][1], "ING_PASTA")
        self.assertIn("cellophane", hit[0][2])

    def test_real_pasta_is_still_tagged(self):
        seed = read(SEED / "ingredient_rule_tags.sql")
        for name in ("spaghetti", "elbow macaroni", "orzo pasta", "fettuccine"):
            self.assertIn("lower(btrim('%s'))" % name, seed, name)

    def test_the_map_excludes_cellophane_and_squash(self):
        self.assertIn("cellophane", import_rules.INGREDIENT_CODE_MAP["ING_PASTA"]["exclude"])
        self.assertIn("squash", import_rules.INGREDIENT_CODE_MAP["ING_PASTA"]["exclude"])

    def test_match_ingredients_sends_cellophane_to_review_not_to_the_tag_list(self):
        confident, review = import_rules.match_ingredients(
            ["cellophane noodle", "spaghetti", "spaghetti squash"], {"ING_PASTA"})
        self.assertEqual(confident, [("spaghetti", "ING_PASTA")])
        self.assertEqual({r[0] for r in review}, {"cellophane noodle", "spaghetti squash"})

    def test_every_statement_is_idempotent(self):
        body = "\n".join(l for l in read(SEED / "ingredient_rule_tags.sql").splitlines() if not l.startswith("--"))
        inserts = body.count("INSERT INTO ingredient_rule_tags")
        self.assertEqual(inserts, body.count("ON CONFLICT (ingredient_id, rule_code) DO NOTHING"))
        self.assertEqual(inserts, 95)  # was 96 before cellophane noodle was removed

    def test_seed_is_exactly_what_the_generator_writes(self):
        """The file says 'GENERATED ... Do not edit by hand'. Regenerating it from the committed
        inputs must give the committed bytes, which proves it was regenerated and not hand-edited."""
        names = import_rules.load_ingredient_names(SEED)
        confident, review = import_rules.match_ingredients(names, seeded_rule_codes())
        with tempfile.TemporaryDirectory() as d:
            sql, review_csv = Path(d) / "tags.sql", Path(d) / "review.csv"
            import_rules.write_ingredient_tags(confident, review, sql, review_csv)
            self.assertEqual(read(sql), read(SEED / "ingredient_rule_tags.sql"))
            self.assertEqual(read(review_csv), read(SEED / "ingredient_rule_tags_review.csv"))

    def test_every_tagged_code_exists_in_rule_codes(self):
        used = set(re.findall(r"SELECT i\.ingredient_id, '([A-Z_0-9]+)'", read(SEED / "ingredient_rule_tags.sql")))
        self.assertEqual(used - seeded_rule_codes(), set())


class TriggerCodeAccounting(unittest.TestCase):
    """Every trigger code the rules use is tagged by exactly one mechanism, is a composite, or is refused."""

    @classmethod
    def setUpClass(cls):
        cls.triggers = rule_trigger_codes()
        cls.imported = set(import_rules.INGREDIENT_CODE_MAP)
        cls.tagger = set(C.NUTRIENT_CODES) | set(T.BY_NAME)
        cls.composite = set(composites())
        cls.refused = set(T.REFUSED)

    def test_the_seed_has_fifty_four_rules_over_forty_four_trigger_codes(self):
        self.assertEqual(len(self.triggers), 44)

    def test_each_trigger_code_is_accounted_for_exactly_once(self):
        # A composite is also listed in REFUSED ("never tagged directly"); count it once, as a composite.
        buckets = {"imported": self.imported, "tagger": self.tagger, "composite": self.composite,
                   "refused": self.refused - self.composite}
        for code in sorted(self.triggers):
            owners = [name for name, codes in buckets.items() if code in codes]
            self.assertEqual(len(owners), 1, "%s is owned by %s" % (code, owners))

    def test_the_mechanisms_do_not_overlap(self):
        self.assertEqual(self.imported & self.tagger, set())
        self.assertEqual(self.tagger & self.refused, set())
        self.assertEqual(self.tagger & self.composite, set())
        self.assertLessEqual(self.composite, self.refused, "a composite must never be tagged directly")
        self.assertEqual(self.refused - self.composite - self.triggers, set(),
                         "a refused code that no rule triggers on is dead weight")

    def test_composites_are_defined_by_taggable_components(self):
        taggable = self.tagger | self.imported
        for comp, parts in composites().items():
            self.assertGreaterEqual(len(parts), 2, comp)
            self.assertLessEqual(parts - taggable, set(), "%s has a component nothing tags" % comp)

    def test_every_tagger_code_exists_in_rule_codes(self):
        known = seeded_rule_codes() | codes_added_by_009()
        self.assertEqual(self.tagger - known, set())

    def test_nutrient_codes_only_use_nutrients_the_seed_actually_stores(self):
        seed = read(SEED / "usda_nutrition.sql")
        for code, cfg in C.NUTRIENT_CODES.items():
            for n in cfg.nutrients:
                self.assertIn("'%s'" % n, seed, "%s needs %s, which usda_nutrition.sql never mentions" % (code, n))


class Migration012Static(unittest.TestCase):
    """The approved tier-1 set, as committed. No database needed."""

    NAME = "012_apply_tier1_ingredient_tags.sql"
    EXPECTED_BY_CODE = {
        "ING_ALLIUM": 19, "ING_GRAIN": 34, "ING_GRAIN_LEGUME": 47, "ING_LEGUME": 13, "ING_SEED": 4,
        "ING_VITC_FOLATE_VEG": 25, "NUT_CAROTENOIDS": 10, "NUT_NONHEME_IRON": 10, "NUT_PROVITAMIN_A": 10,
        "NUT_VITC": 33, "NUT_VITD": 2, "NUT_VITK": 25,
    }

    @classmethod
    def setUpClass(cls):
        cls.rows = tier1_rows()
        cls.text = read(MIGRATIONS / cls.NAME)

    def test_exact_approved_count_and_category_split(self):
        self.assertEqual(len(self.rows), 232)
        cats = {c: sum(1 for r in self.rows if r[2] == c) for c in ("identity", "nutrient", "curated_compound")}
        self.assertEqual(cats, {"identity": 117, "nutrient": 115, "curated_compound": 0})

    def test_the_two_fewer_than_234_are_exactly_the_buttermilk_vitamin_d_pair(self):
        # 234 tier-1 proposals were reviewed; two were then excluded because the review never confirmed
        # that fortified vitamin D in buttermilk is acceptable (tag_config.PAIR_EXCLUSIONS).
        self.assertEqual(234 - len(self.rows), len(C.PAIR_EXCLUSIONS))
        listed = {(n, c) for n, c, _ in self.rows}
        for (code, name) in C.PAIR_EXCLUSIONS:
            self.assertNotIn((name, code), listed)

    def test_per_code_counts(self):
        got = {}
        for _, code, _ in self.rows:
            got[code] = got.get(code, 0) + 1
        self.assertEqual(got, self.EXPECTED_BY_CODE)

    def test_no_curated_compound_tags(self):
        compound = {c for c, cat in C.CODE_CATEGORY.items() if cat == C.COMPOUND}
        self.assertEqual({code for _, code, _ in self.rows} & compound, set())
        self.assertEqual({code for _, code, _ in self.rows} & {"CMP_PHYTATE", "CMP_OXALATE", "BEV_TEA_COFFEE"}, set())

    def test_every_code_is_a_taggable_ingredient_code_in_its_own_category(self):
        for name, code, cat in self.rows:
            self.assertEqual(C.category_of(code), cat, (name, code))
            self.assertIn(cat, ("identity", "nutrient"))

    def test_no_composite_refused_or_process_code(self):
        codes = {code for _, code, _ in self.rows}
        self.assertEqual(codes & set(composites()), set())
        self.assertEqual(codes & set(T.REFUSED), set())
        self.assertEqual({c for c in codes if c.startswith(("PROC_", "BEH_", "MED_", "MACRO_", "MEAL_"))}, set())

    def test_every_code_exists_in_rule_codes(self):
        known = seeded_rule_codes() | codes_added_by_009()
        self.assertEqual({code for _, code, _ in self.rows} - known, set())

    def test_no_duplicate_pairs_and_the_order_is_fixed(self):
        keys = [(n.lower().strip(), code) for n, code, _ in self.rows]
        self.assertEqual(len(keys), len(set(keys)))
        order = {c: i for i, c in enumerate(C.CATEGORIES)}
        sort_keys = [(order[cat], code, n.lower(), n) for n, code, cat in self.rows]
        self.assertEqual(sort_keys, sorted(sort_keys))

    def test_excluded_usda_evidence_is_absent_from_every_nutrient_tag(self):
        nutrient = [(n, code) for n, code, cat in self.rows if cat == "nutrient"]
        names = {n for n, _ in nutrient}
        self.assertEqual(names & set(C.EVIDENCE_EXCLUDED), set(), "an excluded USDA match drives a nutrient tag")
        self.assertEqual(names & {"orange", "sweet potatoes", "sun-dried tomatoes", "tomato paste", "sesame seeds"}, set(),
                         "an ingredient still awaiting USDA values drives a nutrient tag")
        for code in ("milk", "1% low-fat milk", "2% low-fat milk", "nonfat milk", "skim milk", "evaporated milk",
                     "fat-free evaporated milk", "cheese", "unsweetened applesauce", "ground coriander"):
            self.assertNotIn(code, names)

    def test_no_nutrient_tag_for_foods_with_no_defensible_reference_amount(self):
        # Brussels sprouts are an ordinary vegetable (85 g); only true sprouts have no reference amount.
        nutrient_names = [n.lower().replace("brussels sprouts", "") for n, _, cat in self.rows if cat == "nutrient"]
        self.assertIn("brussels sprouts", [n.lower() for n, _, cat in self.rows if cat == "nutrient"])
        for word in ("oat", "garlic", "couscous", "zest", "rind", "peel", "sprout", "pie filling", "tahini"):
            self.assertEqual([n for n in nutrient_names if word in n], [], word)

    def test_excluded_pairs_are_absent(self):
        listed = {(n, code) for n, code, _ in self.rows}
        self.assertNotIn(("buttermilk", "NUT_VITD"), listed)
        self.assertNotIn(("low-fat buttermilk", "NUT_VITD"), listed)
        self.assertEqual([r for r in self.rows if "buttermilk" in r[0]], [])

    def test_cellophane_noodle_is_not_tagged_at_all(self):
        self.assertEqual([r for r in self.rows if "cellophane" in r[0].lower()], [])

    def test_tier_2_examples_are_absent(self):
        listed = {(n, code) for n, code, _ in self.rows}
        for pair in (("flour", "ING_GRAIN"), ("all-purpose flour", "ING_GRAIN_LEGUME"), ("couscous", "ING_GRAIN"),
                     ("tahini", "ING_SEED"), ("potato", "NUT_VITC"), ("rice", "NUT_NONHEME_IRON"),
                     ("firm tofu", "ING_LEGUME"), ("instant coffee granules", "BEV_TEA_COFFEE")):
            self.assertNotIn(pair, listed)

    def test_identity_tags_do_not_depend_on_usda_values(self):
        # sesame seeds has no nutrition until the import runs; as an identity tag it is still correct.
        self.assertIn(("sesame seeds", "ING_SEED", "identity"), self.rows)
        self.assertIn(("garlic", "ING_ALLIUM", "identity"), self.rows)
        self.assertIn(("oats", "ING_GRAIN", "identity"), self.rows)

    def test_header_counts_agree_with_the_rows(self):
        self.assertIn("232 (ingredient, rule code) pairs", self.text)
        self.assertRegex(self.text, r"identity\s+117\s+what the food IS")
        self.assertRegex(self.text, r"nutrient\s+115\s+a measured value")

    def test_it_never_overwrites_or_deletes_and_is_atomic(self):
        self.assertNotRegex(self.text, r"\b(DELETE|UPDATE|TRUNCATE|ALTER)\b")
        self.assertNotRegex(self.text, r"(?<!COMMIT )\bDROP\b")
        self.assertEqual(self.text.count("ON CONFLICT (ingredient_id, rule_code) DO NOTHING"), 1)
        self.assertEqual(self.text.count("BEGIN;"), 1)
        self.assertTrue(self.text.rstrip().endswith("COMMIT;"))

    def test_ingredients_are_selected_by_name_not_by_a_hard_coded_id(self):
        self.assertNotRegex(self.text, r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
        self.assertIn("lower(btrim(i.ingredient_name)) = lower(btrim(t.ingredient_name))", self.text)

    def test_it_is_the_next_migration_after_every_branch(self):
        numbers = sorted(int(p.name.split("_", 1)[0]) for p in MIGRATIONS.glob("*.sql"))
        self.assertEqual(numbers[-1], 12)
        self.assertEqual(self.NAME.split("_", 1)[0], "012")


class GrainLegumeMeaning(unittest.TestCase):
    """ING_GRAIN_LEGUME is 'grain OR legume'; the AND meaning is a separate composite code."""

    @classmethod
    def setUpClass(cls):
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE b (rule_id,rule_name,rule_category,rule_type,trigger_food_or_pattern,trigger_code,"
                   "target_nutrient_or_outcome,target_code,action,action_code,mechanism,recipe_engine_instruction,"
                   "conditions_and_limits,population_scope,evidence_tier,evidence_summary,automation_status,source_title,"
                   "source_type,source_url,review_date,is_active)")
        for block in read(SEED / "business_rules.sql").split("INSERT INTO business_rules")[1:]:
            db.execute("INSERT INTO b" + block.split("\nON CONFLICT")[0].replace("now()", "''"))
        cls.food = {r[0]: (r[1], r[2]) for r in db.execute(
            "SELECT rule_id, trigger_code, trigger_food_or_pattern FROM b WHERE trigger_code LIKE '%GRAIN%' OR trigger_code LIKE '%LEGUME%'")}

    def test_every_rule_on_the_union_code_is_worded_with_or(self):
        for rule in ("BIO-009", "BIO-010", "GLY-008"):
            code, food = self.food[rule]
            self.assertEqual(code, "ING_GRAIN_LEGUME", rule)
            self.assertRegex(food, r"\bor\b", rule)
            self.assertNotRegex(food, r"\band\b", rule)

    def test_the_and_meaning_has_its_own_composite_code(self):
        code, food = self.food["SYN-007"]
        self.assertEqual(code, "ING_LEGUME_GRAIN")
        self.assertIn("and", food)
        self.assertEqual(composites()["ING_LEGUME_GRAIN"], {"ING_LEGUME", "ING_GRAIN"})

    def test_even_the_allium_composite_uses_the_union_as_its_or_component(self):
        code, food = self.food["SYN-009"]
        self.assertEqual(code, "ING_ALLIUM_GRAIN_LEGUME")
        self.assertIn("grain or legume", food)
        self.assertEqual(composites()["ING_ALLIUM_GRAIN_LEGUME"], {"ING_ALLIUM", "ING_GRAIN_LEGUME"})

    def test_the_union_code_is_tagged_per_ingredient_and_the_composite_never_is(self):
        self.assertIn("ING_GRAIN_LEGUME", T.BY_NAME)
        self.assertNotIn("ING_LEGUME_GRAIN", T.BY_NAME)
        self.assertNotIn("ING_ALLIUM_GRAIN_LEGUME", T.BY_NAME)

    def test_the_union_contains_both_families_and_nothing_else(self):
        spec = T.BY_NAME["ING_GRAIN_LEGUME"]
        self.assertEqual(set(spec["include"]), set(T.BY_NAME["ING_LEGUME"]["include"]) | set(T.BY_NAME["ING_GRAIN"]["include"]))


if __name__ == "__main__":
    unittest.main()
