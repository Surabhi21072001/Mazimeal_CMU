# Synergia — Unified Database Schema

PostgreSQL implementation of `Synergia_Unified_DB_Schema.xlsx` (9 sheets, 33 tables).

Verified end to end on **PostgreSQL 16.13**: both build modes install clean, the
reference seed loads, 20 negative tests are rejected by constraints, and the RLS
policies were tested against a non-owner role.

---

## Quick start

```bash
createdb synergia
psql -d synergia -f db/install.sql            # MVP mode
psql -d synergia -f seed/00_reference.sql  # reference data
```

Scale mode:

```bash
psql -d synergia -v scale=true -f db/install.sql
```

Everything runs in one transaction. If any statement fails, nothing is created.

---

## The two build modes

Both produce the **same logical schema**. The difference is declarative
partitioning, and partitioning is not free.

| | MVP (default) | SCALE |
|---|---|---|
| Partitioned tables | 0 | 11 |
| Child partitions | 0 | 120 |
| Foreign keys enforced by the DB | 52 | 31 |
| Foreign keys you must enforce yourself | 0 | **21** |
| Indexes | 147 | 147 (+ per-partition) |
| CHECK constraints | 87 | 87 |
| RLS policies | 34 | 34 |

### Why 23 foreign keys disappear

Postgres will not let a foreign key reference a partitioned table unless it
targets a unique constraint that contains the partition key. Sheet 09 partitions
`household_members` by `household_id`, `ingredients` by `food_category`, and
`recipes` by `data_source` — none of which exist on the referencing tables. So
every FK into those three tables becomes impossible.

That means in SCALE mode the database will happily accept a
`member_conditions` row pointing at a member who does not exist. An allergy
record orphaned from its member is not a data-quality nit; it is an allergy the
recipe filter will never apply.

The gap is queryable, not buried in a comment:

```sql
SELECT * FROM v_unenforced_fks;   -- 0 rows in MVP, 23 rows in SCALE
```

**Recommendation: start in MVP mode.** The partition scheme is designed for
50M-row tables. Below roughly 10M rows a table it costs referential integrity and
buys nothing you can measure. Turn on SCALE per-table, when a table earns it.

---

## File order

| File | What it does |
|---|---|
| `00_extensions.sql` | pgcrypto, pgvector probe, `gen_ulid()`, build-mode toggles |
| `10_identity_auth.sql` | users · sessions · audit_log |
| `20_household_profile.sql` | households · household_members · member_conditions · user_allergen_map |
| `30_conditions_rules.sql` | conditions · attributes · nutrient_rules · nutrient_modifiers · documents |
| `40_nutrition_baselines.sql` | categories · nutrients_master · baselines · targets |
| `50_ingredients_nutrition.sql` | ingredients · nutrition · USDA ref · attributes |
| `60_food_science.sql` | synergy pairs · bioavailability · substitutions · glycemic index |
| `70_recipes.sql` | cultural categories · recipes · ingredients · steps · videos · rules map |
| `80_plan_tracking.sql` | meal plan · recipe history · nutrient daily log |
| `85_foreign_keys.sql` | every FK, plus the SCALE-mode gap and `v_unenforced_fks` |
| `88_vector.sql` | embedding columns + HNSW indexes (skipped if pgvector absent) |
| `90_indexes.sql` | 147 access-path indexes |
| `91_partitions.sql` | child partitions (SCALE only) |
| `93_functions.sql` | category derivation, nutrient target computation, `v_phi_columns` |
| `94_maintenance.sql` | triggers, audit logging, partition lifecycle, integrity checks |
| `95_rls.sql` | row level security for every table |
| `96_compat_weekly_plans.sql` | keeps the current MVP working; migration off it |

FKs are declared centrally rather than inline because the workbook has
cross-domain references in both directions — no table-creation order satisfies
them all.

---

## Deliberate deviations from the workbook

Each one is commented at the point it occurs.

1. **`TIMESTAMPTZ` instead of `TIMESTAMP`.** `households.country_region` spans
   US/GB/DE/CH. Naive local timestamps corrupt meal timing and any daily log
   that crosses a DST boundary.

2. **`profile_nutrient_targets` is a table, not a materialized view.** The sheet
   says "MATERIALIZED VIEW or table". A Postgres matview can only refresh in
   full; refreshing 125M rows because one member edited their profile is not
   viable. Per-member rows are recomputed by `fn_compute_member_targets()`.

3. **`users.email` uses a unique index on `lower(email)`**, plus a CHECK that the
   stored value is already lowercase. The sheet's plain `UNIQUE` would let
   `Jeff@x.com` and `jeff@x.com` both exist while the login index treats them as
   one.

4. **`ingredient_bioavailability` is unique on
   `(ingredient_id, prep_method, affected_nutrient_id)`**, not the sheet's
   `(ingredient_id, prep_method)`. Steaming changes folate *and* lycopene; the
   sheet's key allows only one row per prep method.

5. **CHECK constraints added throughout** where the sheet documented allowed
   values in prose ("mild; moderate; severe; anaphylactic"). Documented
   constraints that are not enforced are documentation, not constraints.

6. **`ck_rec_ai_flag`** ties `recipes.is_ai_generated` to
   `data_source = 'AI_generated'`. They are the partition key and a boolean
   describing the same fact; letting them disagree puts AI content in the
   reference partition.

7. **A `DEFAULT` partition on `ingredients`.** LIST partitioning requires an
   exhaustive value set, and USDA food groups are not under our control. Without
   a default, a new group in an import breaks ingestion in production.
   `fn_check_default_partitions()` reports anything that lands there.

---

## Open questions for the schema author

These block work and are not answerable from the material supplied.

1. **The Q1–Q17 questionnaire.** `household_members` columns are labelled Q1,
   Q2, Q4, Q5, Q6, Q10, Q14, Q15, Q16, Q17 — seven numbers are missing and the
   source document was not included. Without it, condition- and life-stage-driven
   nutrient modifiers cannot be mapped. `fn_compute_member_targets()` deliberately
   implements only the activity-level and goal modifiers rather than guessing;
   a wrong nutrient target is a clinical error, not a bug.

2. **The C001–C021 category mapping.** Sheet 04 sources it from "Jessica's
   spreadsheet" and gives two anchors — C001 = newborn female, C016 = early adult
   female. No ordering of age bands by sex produces both. The seed ships an
   18-row placeholder that is explicitly *not* the clinical mapping.

3. **`condition_code` collides across two meanings.** `conditions.condition_code`
   uses C001 = Type II Diabetes, while `categories.category_id` uses C001 =
   newborn female. Same format, same prefix, unrelated namespaces. This will be
   mixed up. Recommend renaming category codes to `CAT001`.

4. **`nutrient_rules.rule_id` vs `nutrient_modifiers.rule_id`** are different
   identifier spaces (`R001` vs `PROT_ACT_F_HIGH_001`) sharing a column name with
   no FK between them. Recommend renaming the latter to `modifier_id`.

5. **`cultural_categories.category_id`** (UUID) and `categories.category_id`
   (VARCHAR(10)) share a name across domains. Recommend `cultural_category_id`.

---

## Verification

Reproduce the checks that were run against this schema:

```sql
SELECT * FROM v_unenforced_fks;            -- integrity gaps; empty in MVP mode
SELECT * FROM v_phi_columns;               -- HIPAA data inventory (5 columns)
SELECT * FROM fn_check_default_partitions(); -- rows in a DEFAULT partition
SELECT * FROM fn_check_duplicate_fdc_ids();  -- USDA import duplicates
SELECT * FROM fn_check_stale_targets();      -- targets older than the profile

-- every table must have RLS enabled
SELECT relname FROM pg_class
WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'
  AND NOT relrowsecurity;
```

---

## Notes for whoever wires up the application

- **Set the acting user on every connection.** RLS resolves identity through
  `current_app_user_id()`, which reads the Supabase JWT claim if present and
  otherwise `app.user_id`. On plain Postgres: `SET LOCAL app.user_id = '<uuid>'`
  after checkout. With no identity set, every policy evaluates false and the
  client sees nothing — that is the intended failure mode.

- **Workers connect as the service role.** Target recomputation, embedding
  generation and daily-log aggregation must bypass RLS. Never ship a
  service-role key to the browser.

- **Listen for the notifications.** `member_profile_changed` and
  `member_conditions_changed` are emitted by triggers and feed the
  `nutrient-target-recompute` and `household-allergen-cache-warm` queues.
  Nothing recomputes on its own.

- **Use the documented upsert** for `nutrient_daily_log`. The
  `ON CONFLICT ... DO UPDATE SET consumed_value = consumed_value + EXCLUDED...`
  form is atomic; a read-modify-write from application code will silently lose
  concurrent meal logs.

- **Schedule `fn_ensure_time_partitions()` daily** in SCALE mode. Without it new
  rows fall into the DEFAULT partition, and once that holds data, attaching the
  correct partition requires a full scan.

- **pgvector.** Absent from a stock apt install; present on Supabase. The schema
  builds without it and skips the two embedding columns. Re-run `88_vector.sql`
  after installing it.
