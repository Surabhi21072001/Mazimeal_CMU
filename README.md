# MaziMeal

Nutrition planning. A household says who it is feeding; the database holds 400
recipes, their ingredients, their nutrition, and 54 rules drawn from nutrition
research. The product's job is to match the rules to the recipe in front of a
cook — "crush the garlic and let it rest before it meets heat" — and to show
only the ones a human reviewer has approved.

Everything in the database today is test data. See
[docs/HANDOFF.md](docs/HANDOFF.md) for what is deployed, who owns what, and
what is still open.

## Layout

```
web/           React + Vite client. Hash-routed, no router dependency.
api/           FastAPI backend. Serves the screens and mounts the rules engine.
scripts/       The rules engine and the data pipeline. Imported by api/, not
               called over HTTP.
schema/        PostgreSQL DDL (numbered in load order) + migrations/ + seed/
recommender/   The recommendation database: its own schema, functions and
               scoring. The frontend calls its functions through Supabase RPC.
tests/         pytest. 519 pass without a database; the rest skip.
docs/          How the data was built, how to deploy, who can sign in
```

Four workstreams wrote this repository and the split still shows:
`web/` and `api/` are the front-and-back-end work, `scripts/` and `schema/` are
shared with the rules and data work, and `recommender/` belongs to the
recommendation work. [docs/HANDOFF.md](docs/HANDOFF.md) has the ownership map.

## Run it

Node `^20.19 || >=22.12` (stated in `web/package.json`) and Python 3.12.

```bash
# the screens, on bundled sample data, no backend needed
npm ci --prefix web
npm run dev --prefix web                      # http://localhost:5173

# the backend
python3.12 -m venv api/.venv
api/.venv/bin/pip install -r api/requirements.txt
api/.venv/bin/uvicorn app.main:app --app-dir api --reload --port 8002
```

Point the screens at the backend with `web/.env.local`:

```
VITE_API_BASE_URL=http://127.0.0.1:8002
```

The badge in the top right of each screen says which of the three you are
looking at: **Offline sample**, **Backend · sample data**, or **Live**.

Against the real database, add a DSN — see [docs/DATA.md](docs/DATA.md) for
where the connection string comes from:

```bash
set -a; . ./.env; set +a
MAZI_REPO=supabase MAZIMEAL_DSN="$SUPABASE_DB_URL" \
  api/.venv/bin/uvicorn app.main:app --app-dir api --port 8002
```

### Tests

```bash
api/.venv/bin/pip install -r requirements-dev.txt
api/.venv/bin/python -m pytest tests -q
```

519 pass, 171 skip. The skips are the tests that need Postgres; they run only
when `MAZIMEAL_TEST_DSN` points at a **local** database, and `tests/dbguard.py`
refuses anything else so a test run cannot truncate the shared one.

### Screens

| URL | What it is |
|---|---|
| `/` | The recommendations — one meal for one member, ranked by the nutrient they still need |
| `#/recipes` | The seed recipes, as an index |
| `#/cook/<recipe_id>` | The recipe: ingredients, nutrition, steps, and the rules that apply |
| `#/review` | Reviewer screen: approve, edit or reject the generated text per recipe |
| `#/review/nutrition` | Whether each recipe's numbers can be right |
| `#/admin` | The rules table, the code vocabulary, and the queue that changes them |
| `#/classic` | The original team's app shell, which still owns signing up |

## Load the schema from scratch

```bash
createdb mazimeal
for f in schema/[0-9][0-9]_*.sql; do
  psql -d mazimeal -v ON_ERROR_STOP=1 -f "$f"
done
for f in schema/migrations/*.sql; do
  psql -d mazimeal -v ON_ERROR_STOP=1 -f "$f"
done
psql -d mazimeal -f schema/99_validate.sql
```

Keep `ON_ERROR_STOP=1`. Without it psql carries on after a failure and you get
half a schema with no obvious error. The file numbers are the load order:
`03_recipe_ingredients.sql` has foreign keys into `recipes` and `ingredients`,
so those have to exist first. Seed data is in `schema/seed/`, documented in
[schema/seed/README.md](schema/seed/README.md).

`recommender/db/` is a separate schema with its own installer
(`recommender/db/install.sql`) and its own README.

## Credentials

Nothing with a password goes in the repository: not in a SQL file, not in a
comment, not temporarily. Your working copy lives in `.env` (gitignored), and
CI fails any commit that adds one.

```bash
cp .env.example .env
git check-ignore -v .env      # must print a .gitignore line
```

Two things that are *not* secret, and are committed on purpose:
`web/.env.production` holds the Supabase URL and the publishable key, because
`VITE_*` variables are compiled into the browser bundle. That key carries no
privileges of its own — row-level security is what protects the data, and the
reviewer tables have RLS enabled with no policy at all, so the browser key
cannot reach them even in principle.

## Example data

Committed on purpose, so the screens work the moment someone clones this.

| Path | What it is |
|---|---|
| `api/fixtures/*.json` | One household, five recipes, one set of recommendations |
| `web/src/shared/fixtures/` | A copy, bundled so the frontend runs with no backend. Regenerate both with `python3 api/build_fixtures.py` |
| `schema/seed/*.sql` | 400 Food.com recipes, USDA nutrition, gram weights — the inherited seed data |

Every fixture carries a `_fixture_note` field saying which of its values are
real and which are invented. In short: per-serving nutrition, ingredient names,
step text and the rules themselves are real; gram weights, step durations,
today's consumed totals and the recommendation scores are invented.

## How the generated text works

Suggestions are not written while someone waits. They are generated offline,
reviewed, and then served as data:

```bash
# writes version 1 of each recipe's review record - the baseline a reviewer
# reads a diff against, and never served to a cook on its own
api/.venv/bin/python api/pregenerate.py
```

Two guards decide whether a model's words are used at all: it may not introduce
a number the source rule did not contain, and a summary may not quietly drop a
rule it claims to cover. When either fires, the rule's own wording is used
instead and the response says so. No model runs in a deployed build —
production reports `"provider": "template"`.

A reviewer's decision is a row in `recipe_content_versions`, including
"confirmed, nothing changed", because an absence of rows cannot be told apart
from an absence of reviewers.

## Where to read next

**Read first:** [docs/HANDOFF.md](docs/HANDOFF.md) — what is deployed where,
who wrote what, what is broken, and what to do in the first week.

Then whichever of these matches the job:

| Document | What it answers |
|---|---|
| [docs/API.md](docs/API.md) | **Every endpoint**, its input, its output, what an account is needed for, and the payload shapes. The only endpoint document |
| [docs/DATA.md](docs/DATA.md) | Reaching the database, changing data safely, and where the highest-value data work is |
| [api/README.md](api/README.md) | Running the backend, its environment switches, and how the suggestion text is written and reviewed |
| [docs/deploy.md](docs/deploy.md) | Deploying the screens and the API, and the two settings that cost half a day each |
| [docs/accounts.md](docs/accounts.md) | Signing in, and how someone becomes a reviewer |
| [docs/BRANCHING.md](docs/BRANCHING.md) | Branches, PRs, and who owns which file |
| [docs/RECIPE_DATA.md](docs/RECIPE_DATA.md) | Element by element: what the recipe screens show, where it comes from, and what is still missing |

Each screen's own notes sit next to its code:
[web/src/features/home/](web/src/features/home/README.md) and
[web/src/features/recipe/](web/src/features/recipe/README.md), both with
screenshots.

### Other workstreams' documents

Kept because they describe live code, but they are reference for their own
area, not for the API or the screens:

| Document | Whose |
|---|---|
| [docs/phase2_business_rules.md](docs/phase2_business_rules.md), [phase2_recipe_facts.md](docs/phase2_recipe_facts.md), [phase2_user_nutrition.md](docs/phase2_user_nutrition.md) | The rules work: the rule tables, the code vocabulary, and the `RecipeFacts` snapshot the engine evaluates |
| [recommender/README.md](recommender/README.md), [recommender/db/README.md](recommender/db/README.md) | The recommendation work: scoring, and its own database schema |
| [schema/seed/README.md](schema/seed/README.md) | Where the 400 recipes and the USDA nutrition came from |
| [docs/Testing_Plan.md](docs/Testing_Plan.md) | A QA plan, proposed and **never executed**. Owners and test cases are in it; several of its open questions have since been answered elsewhere |

## Conventions

- `main` is what gets demoed and deployed. `dev` is day-to-day work. Pull
  before you push, and use a PR for schema files so CI checks them first.
- One owner per schema file. Ask before editing someone else's.
- Migrations are numbered and contiguous; `tests/test_tag_data.py` fails if two
  branches claim the same number, which has already happened once.
- Run `schema/99_validate.sql` after each insert batch, not just at the end.
