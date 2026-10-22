# Phase 2 — Recipe Optimization Business-Rules Layer

This is the first version of the MaziMeal business-rules layer. It stores the
approved recipe-optimization rules, gives them a semantic code vocabulary, maps
existing ingredients to those codes, and provides deterministic detection of
which rules apply to a recipe.

It does **not** modify recipes, resolve conflicts, optimize nutrition, or call
an LLM. That is the next phase. This phase only proves the stored rules can be
matched against existing recipe data.

## Source of truth

All rules come from the approved workbook in the repo root:

```
IN WORK - MaziMeal Recipe Optimization Rules (1).xlsx
```

Rule sheets: **Bioavailability**, **Food Synergies**, **Inhibitors**,
**Glycemic Behaviors**. The **Codebook** sheet is currently empty, which is why
code metadata is auto-derived and flagged for review (see below). The **Read Me**
sheet is informational.

## 1. Existing MaziMeal tables reused (unchanged)

| Table | Why it's used here |
|---|---|
| `recipes` (`recipe_id` UUID) | the recipe being inspected |
| `ingredients` (`ingredient_id` UUID) | tagged with semantic codes; matched by name |
| `recipe_ingredients` (`recipe_id`, `ingredient_id`) | links a recipe to its ingredients |
| `ingredient_nutrition`, `recipe_nutrition` | **not touched** — USDA data stays where it is |

The business-rule layer references semantic concepts (`NUT_IRON`, `ING_GARLIC`)
rather than copying any per-100 g USDA nutrition values. The optimization layer
keeps relying on the existing nutrition tables.

## 2. New tables created and why

| File | Table | Purpose |
|---|---|---|
| `schema/10_business_rules.sql` | `business_rules` | the 54 approved optimization rules |
| `schema/11_rule_codes.sql` | `rule_codes` | controlled vocabulary of the 121 semantic codes |
| `schema/12_ingredient_rule_tags.sql` | `ingredient_rule_tags` | many-to-many ingredient ↔ code mapping |

Design choices tied to the real data:

- **`rule_id` is `TEXT` PK** (`BIO-001`, `SYN-002` …), matching the existing
  `nutrient_rules` readable-id convention rather than a UUID.
- **CHECK constraints only where the workbook is genuinely enumerated**:
  `automation_status` (`recipe_safe`, `conditional`, `instruction_only`,
  `do_not_automate`) and `evidence_tier` (`A`/`B`/`C`). `rule_type` (14 values)
  and `source_type` (22 values) are free text, so they are **not** constrained.
- **`conditions_and_limits` and `population_scope` are `TEXT`**, because the
  workbook stores prose there, not structured JSON.
- **`rule_category`** is derived from the source sheet.
- `business_rules` is separate from the existing `nutrient_rules` (clinical and
  food-safety rules). The two can be joined later; they were kept apart so this
  phase does not alter an owned table.

## 3. How the Excel maps into `business_rules`

The four rule sheets share an identical 20-column header on row 3. Those columns
map 1:1 to `business_rules`, with two derived additions:

| Workbook column | `business_rules` column |
|---|---|
| rule_id | rule_id |
| rule_name | rule_name |
| *(sheet name)* | **rule_category** (derived) |
| rule_type | rule_type |
| trigger_food_or_pattern | trigger_food_or_pattern |
| trigger_code | trigger_code |
| target_nutrient_or_outcome | target_nutrient_or_outcome |
| target_code | target_code |
| action | action |
| action_code | action_code |
| mechanism | mechanism |
| recipe_engine_instruction | recipe_engine_instruction |
| conditions_and_limits | conditions_and_limits |
| population_scope | population_scope |
| evidence_tier | evidence_tier |
| evidence_summary | evidence_summary |
| automation_status | automation_status |
| source_title | source_title |
| source_type | source_type |
| source_url | source_url |
| review_date | review_date |
| *(always TRUE on import)* | **is_active** (derived) |

`scripts/import_rules.py` reads the workbook, normalizes blank cells to `NULL`,
normalizes dates, validates required/enumerated fields, detects duplicate
`rule_id`s, and writes idempotent UPSERT SQL. It does not touch a database
(same pattern as `scripts/csv_to_sql.py`).

Counts imported: Bioavailability 15, Food Synergies 12, Inhibitors 12,
Glycemic Behaviors 15 → **54 total**, no duplicate ids.

## 4. How `rule_codes` works

Every distinct `trigger_code` / `target_code` / `action_code` in the workbook
becomes a row in `rule_codes`. There are **121** of them, grouped by prefix
family (`code_type`): `ING_`, `NUT_`, `CMP_`, `MACRO_`, `PROC_`, `PAIR_`,
`BEV_`, `SEP_`, `SUB_`, `MITIGATE_`, `OUT_`, and others discovered in the data.

Because the workbook's Codebook sheet is empty, `display_name` and
`description` are auto-derived (humanized from the code) and every row is
flagged **`needs_review = TRUE`**. The companion report
`schema/seed/rule_codes_review.csv` lists all 121 codes for a human to confirm.
Re-running the seed only updates `code_type`, so any human-edited
`display_name`/`description` survives a reload.

## 5. How `ingredient_rule_tags` works

This maps existing ingredients to codes so a recipe's ingredient list becomes a
set of trigger codes.

Key constraint: ingredients are seeded **by name** (no fixed UUIDs), so the tag
seed resolves `ingredient_id` through a case-insensitive name lookup that
matches the existing `uq_ingredients_name_lower` index. If an ingredient isn't
present, the insert simply affects zero rows — no error.

Only confident mappings are seeded. Matching uses a curated keyword map with
explicit exclusions to avoid false positives seen in the real data
(`corn syrup`, `cornstarch`, `eggplant`, `garlic powder`, `peanut butter`,
`spaghetti squash`, …). Anything a keyword touches but an exclusion rejects goes
to `schema/seed/ingredient_rule_tags_review.csv` for a human, rather than being
inserted. The composite primary key `(ingredient_id, rule_code)` makes
re-seeding idempotent.

## 6. How deterministic rule detection works

`scripts/detect_rules.py` provides `detect_rules(conn, recipe_id)`. It accepts
any DB-API connection (psycopg2/psycopg3 for Postgres, sqlite3 in tests). It:

1. loads the recipe's ingredients,
2. looks up `ingredient_rule_tags` for those ingredients,
3. builds the set of trigger codes present,
4. selects **active** `business_rules` whose `trigger_code` is in that set,
5. returns `rule_id`, `rule_name`, `automation_status`, `trigger_code`, and a
   human-readable reason naming the ingredient that triggered it.

### Flow

```
Existing Recipe
    -> recipe_ingredients          (which ingredients it contains)
    -> ingredient_rule_tags        (codes tagged on those ingredients)
    -> trigger codes               (the set of codes present)
    -> business_rules              (active rules whose trigger_code matches)
    -> detected applicable rules
```

### Example output (seeded Food.com recipes)

```
Recipe: Creamy Swiss Chard Pasta
  BIO-002  [recipe_safe]  Crush garlic and rest before heating
      Reason: recipe contains ingredient tagged ING_GARLIC (garlic cloves)
  BIO-003  [recipe_safe]  Cook tomatoes with oil
      Reason: recipe contains ingredient tagged ING_TOMATO (tomatoes)
  BIO-005  [recipe_safe]  Cook spinach for carotenoid release
      Reason: recipe contains ingredient tagged ING_LEAFY_GREEN (swiss chard)
  GLY-007  [recipe_safe]  Use al dente pasta
      Reason: recipe contains ingredient tagged ING_PASTA (fettuccine pasta)
  SYN-011  [conditional]  Fermented dairy cultures with lactose
      Reason: recipe contains ingredient tagged ING_YOGURT (plain yogurt)

Recipe: Healthy Bean Soup With Kale
  BIO-002, BIO-003, BIO-004, BIO-005, BIO-006, BIO-007, INH-007  (garlic, tomato,
  carrot, kale as crucifer + leafy green)

Recipe: To Die for Crock Pot Roast
  (no applicable rules)
```

## 7. What requires human review

- **All 121 rule codes** — metadata auto-derived because the Codebook sheet is
  empty. See `schema/seed/rule_codes_review.csv`.
- **Ambiguous ingredient matches** — keyword-matched but excluded as likely
  false positives. See `schema/seed/ingredient_rule_tags_review.csv` (e.g.
  `eggplant`→ING_EGG, `garlic powder`→ING_GARLIC, `corn syrup`→ING_CORN).
- The curated `INGREDIENT_CODE_MAP` in `scripts/import_rules.py` covers the
  common ingredient-level codes. Group codes that need judgement (e.g.
  `ING_LEGUME` across beans/tofu/soy derivatives) were intentionally kept
  conservative and can be widened after review.

## 8. How this connects to the future optimization / LLM layer

`detect_rules()` returns the applicable rules with their `automation_status`.
The next phase consumes that:

- `recipe_safe` rules can be applied automatically,
- `conditional` rules apply when a population/condition matches,
- `instruction_only` rules surface as guidance without modifying the recipe,
- `do_not_automate` rules are left to a human.

The `recipe_engine_instruction` column holds the plain-language instruction the
LLM/optimization step would act on. None of that is built yet.

## 9. Why this layer stays in PostgreSQL for now

- MaziMeal already runs on PostgreSQL/Supabase.
- Existing recipes and USDA nutrition already live there, so detection is a
  plain join — no data movement.
- It avoids introducing a second datastore before it is needed.
- A graph database can be evaluated later if relationship traversal
  (multi-hop synergies/inhibitors) becomes complex enough to justify it.

## Running it

```bash
# 1. create the tables
psql -d mazimeal -v ON_ERROR_STOP=1 -f schema/10_business_rules.sql
psql -d mazimeal -v ON_ERROR_STOP=1 -f schema/11_rule_codes.sql
psql -d mazimeal -v ON_ERROR_STOP=1 -f schema/12_ingredient_rule_tags.sql

# 2. (re)generate the seeds from the workbook
python3 scripts/import_rules.py

# 3. load the seeds (idempotent — safe to re-run)
psql -d mazimeal -v ON_ERROR_STOP=1 -f schema/seed/rule_codes.sql
psql -d mazimeal -v ON_ERROR_STOP=1 -f schema/seed/business_rules.sql
psql -d mazimeal -v ON_ERROR_STOP=1 -f schema/seed/ingredient_rule_tags.sql

# 4. detect rules for a recipe
python3 scripts/detect_rules.py --dsn "dbname=mazimeal" <recipe_id>

# 5. run tests (no DB or extra deps needed)
python3 -m unittest tests.test_rules -v
```
