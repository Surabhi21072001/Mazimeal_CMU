# Database handoff for the current team repository

This contribution adds reproducible local setup, source and quantity review
tracking, nutrient-specific coverage reports, and a read-only database viewer.
It builds on `main` at `e67a499` (November 5, 2026).

**Start here, Surabhi:** review `schema/migrations/005_data_readiness.sql`, then
run the local setup below. This is an additive data-review layer. It does not
replace your mappings, rule definitions, optimizer, or Kevin's API/UI.

## What changed from Andrew's October handoff

| Earlier local implementation | This branch |
|---|---|
| Separate source tables and one nutrient source | Reuses `data_sources`, `ingredient_source_map` and `v_ingredient_nutrition` |
| 424 recipes including 24 additional sample CSV recipes | Loads the team's committed 400-recipe seed; reports default to Kevin's exact 50 CSV IDs |
| Ingredient-level readiness | Checks each nutrient's coverage, selected-source review, units, gram quantities and recipe completeness |
| Profiles deferred | Preserves the team's new profile, target and credential tables; imports no users and changes no profile logic |
| Older evaluator with local behavior changes | Keeps the current enriched evaluator unchanged; carries only database-reader fixes |

The older 424-recipe database is a separate local development copy. Do not copy
its UUIDs into the shared database. This branch does not claim to repair the
50 recipes' missing ingredients, unreliable quantities or unreviewed mappings.

## Local setup

Requires Python 3.11+ and Docker Desktop. From this repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r data_engineering/requirements.txt
.venv/bin/python data_engineering/manage.py configure
docker compose --env-file data_engineering/.env -f data_engineering/compose.yaml up -d --wait
.venv/bin/python data_engineering/manage.py bootstrap
```

`configure` generates an ignored local connection file and refuses to overwrite
it. PostgreSQL runs on **127.0.0.1:5434**, database `mazimeal_integration`, in a
separate Docker volume. Bootstrap is atomic and refuses any nonempty database
or any destination other than that dedicated local database. On later visits,
start Docker with the same command and skip configure/bootstrap.

The import uses the existing numbered `schema/` files and committed recipe,
USDA, source, estimated-gram and rule seeds. It also loads the new review
migration and records input hashes. It does **not** install `recommender/db/`,
Supabase authentication/household migrations, sample users, the old sample CSV
batch, or GraphDB. Estimated gram weights remain estimates pending review.

## Reports and demo

```bash
.venv/bin/python data_engineering/manage.py report
.venv/bin/python data_engineering/manage.py report --scope all --out data_engineering/local_results/all
.venv/bin/python data_engineering/manage.py recipe --recipe-id ACTUAL_DATABASE_UUID
.venv/bin/python data_engineering/viewer.py
```

Open http://127.0.0.1:7211 for the read-only viewer. Keep its terminal running.
The viewer only exposes recipe/data-review tables, not user profiles or login
credentials. It is local to your computer and reads fresh data on each request.

Reports go to ignored `data_engineering/local_results/`:

- `recipe_ids.csv`: current database IDs, Food.com IDs and recipe readiness.
- `mapping_review.csv`: source matches and review status for the selected recipes.
- `quantity_review.csv`: ingredient lines whose gram quantities still need review.
- `nutrient_coverage.csv`: per-nutrient coverage and nullable reviewed totals.
- `nutrition_review_queue.json`: latest existing UI verdicts, when that table is
  installed; no reviewer identity is exported. These are prioritization evidence,
  not approval of quantities or ingredient matches.
- `summary.json`: scope, missing seed IDs and candidate-rule coverage.

The default scope reads the same CSV and external IDs as `api/app/seed_list.py`.
It reports missing IDs explicitly. `--scope all` is clearly labeled separately.
Both report and recipe commands use read-only, repeatable-read transactions.
Generated reports contain database-specific IDs and notes; do not commit them.

## Simple data dictionary

| Table or view | Purpose |
|---|---|
| Existing `recipes`, `recipe_ingredients`, `recipe_steps` | Recipe identity, ingredient amounts and instructions |
| Existing `ingredient_source_map` | The upstream food selected for an ingredient |
| Existing `v_ingredient_nutrition` | One nutrient value per ingredient, selected by source precedence |
| `de_mapping_reviews` | Human approval of a specific ingredient-to-source match |
| `de_line_reviews` | Human review of a line's quantity and gram conversion |
| `de_recipe_reviews` | Source-backed review of ingredient-list completeness, preparation and servings |
| `de_line_provenance` | Optional original source text and list positions; never invented from database order |
| `de_recipe_readiness` | Recipe-level coverage and unresolved quantity counts |
| `de_recipe_nutrient_readiness` | Whether a particular nutrient can be calculated from fully reviewed inputs |
| `de_dataset_releases` | Local import identity and source-file hashes |

Missing review rows mean pending. Changing a mapping resets its approval;
changing quantities, ingredients, servings or cooking steps invalidates the
affected reviews. An unrelated update does not clear them. Re-running the
migration preserves existing approvals and IDs.

`recipe_nutrition_reviews` remains Kevin's separate plausibility/history table.
Its `plausible` verdict never auto-approves the new detailed checks. Similarly,
`sequence_order` keeps its existing eating-order meaning. Source list positions
have separate optional fields and start empty.

## Integration contract

The existing `RecipeFacts -> candidate rules -> evaluations` API still works.
The standalone `recipe_packet(conn, recipe_id)` adds `data_readiness`,
`ingredient_details` and `nutrient_readiness` to the current team output. Its
wrapper version is **2.0**; this is not a change to the deployed HTTP API.

For a given recipe and nutrient, read:

```sql
SELECT nutrient_id, unit, ingredient_lines, lines_with_nutrient,
       lines_ready, recipe_reviewed, ready, verified_per_serving
FROM de_recipe_nutrient_readiness
WHERE recipe_id = :recipe_id;
```

Only `ready=true` exposes a numeric `verified_per_serving`. It requires a
source-backed recipe review, positive aligned and reviewed grams on every line,
a reviewed mapping for each nutrient's **selected** source, complete coverage,
and consistent units. Otherwise the value is NULL, not zero or a partial total.
True source zeros stay zero. No nutrient-source duplicates are summed.
Readiness means these data checks passed; it is not clinical validation or an
allergy-safety decision. A requested nutrient absent from this view is unknown.

**Kevin's current API is not switched to these checks by this branch.** He can
join this view when deciding how to label or suppress derived values. Published
recipe values stay separate. Surabhi/Guy-Georges retain responsibility for rule
conditions and automation limits. New ingredient tags need review before insertion.

## Applying to an existing database

Use a staging copy of the current team `schema/` database first. Do not run
bootstrap there, and do not reload the team's seeds over edited live records.
The migration expects the existing multi-source columns and
`v_ingredient_nutrition`; it is not an upgrade for the archived October database.

```bash
psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f schema/migrations/005_data_readiness.sql
MAZIMEAL_DSN="$SUPABASE_DB_URL" .venv/bin/python data_engineering/manage.py report
```

Only a database owner/backend role should manage these reviews. New review
tables have RLS enabled with no browser policies, and the views use invoker
security. No browser grants are added. Review backend role permissions in the
staging environment. Removing this layer requires reverting dependent API
changes first; keep a normal database backup before deploying any migration.

## Validation

```bash
.venv/bin/python -m unittest discover -s tests -v
MAZIMEAL_RUN_DB_TESTS=1 .venv/bin/python -m unittest discover -s data_engineering -v
```

Database tests refuse connections outside local `mazimeal_integration` and roll
back their writes. They cover all 50 recipe packets, the current API adapter,
multiple sources, missing nutrients, real zero values, mixed units, invalidated
reviews, migration re-runs and preservation of the team's profile/target tables.
The existing workbook-dependent tests skip when the workbook is not in the repo.

Next data work: review source quantities and food matches for selected demo
recipes, capture the evidence, then extend reviewed rule tags with the rules
team. No shared/live database was changed while preparing this branch.
