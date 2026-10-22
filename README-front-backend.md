# MaziMeal — front end and back end

This branch holds the recipe screens, the recommendation screen, the reviewer
screen, and the small backend behind them. Everything else in the repository is
inherited from the original MaziMeal team and is kept because our work builds on
it: the database schema, the seed data, and the existing app shell.

**Nothing here talks to a production database yet.** The screens run on example
data so the whole flow can be used and demonstrated today, and each piece is
replaced independently as the other workstreams deliver.

---

## Run it

```bash
# the screens, on example data, no backend needed
npm install --prefix web
npm run dev --prefix web          # http://localhost:5173

# with the backend (recommended: the reviewer screen and the assistant need it)
python3.12 -m venv api/.venv
api/.venv/bin/pip install -r api/requirements.txt
cd api && .venv/bin/uvicorn app.main:app --reload --port 8002
```

Point the screens at the backend by creating `web/.env.local`:

```
VITE_API_BASE_URL=http://127.0.0.1:8002
```

The badge in the top right of each screen says which of the two you are looking
at: **Offline sample**, **Backend · sample data**, or **Live**.

### Screens

| URL | What it is |
|---|---|
| `#/recommend` | One meal for one member, ranked by the nutrient they still need |
| `#/cook/<recipe_id>` | The recipe: ingredients, nutrition, steps, and the rules that apply |
| `#/review` | Reviewer screen: edit the AI text, correct the rules, keep a history |
| anything else | The original team's app, untouched |

---

## What is example data

Everything below is **illustrative**. It is committed on purpose, so that the
screens work the moment someone clones this, and so a reviewer can see the whole
flow without running a model. None of it is a measurement to be trusted or a
decision anyone has signed off.

| Path | What it is | Replaced by |
|---|---|---|
| `api/fixtures/*.json` | One household, five recipes, one set of recommendations | The database, and the recommender the team is building |
| `web/src/shared/fixtures/` | A copy of the above, bundled so the front end runs with no backend | Same; regenerate with `python3 api/build_fixtures.py` |
| `api/content/*.json` | AI text that a reviewer approved | Real reviewed content, stored in the database |
| `schema/seed/*.sql` | 400 Food.com recipes, USDA nutrition, gram weights | Inherited from the original team; this is their real seed data |

Inside the fixtures, what is real and what is invented is marked in a
`_fixture_note` field on every file. In short:

- **Real**: per-serving nutrition, ingredient names, step text, Maya's iron
  target of 27 mg against an 18 mg baseline, and the rules themselves — rule
  ids, evidence tiers, automation status and source links all come from the
  client's own rules workbook (`docs/IN WORK - MaziMeal Recipe Optimization
  Rules.xlsx`).
- **Invented**: gram weights, ingredient units, step titles and durations,
  today's consumed totals, and the recommendation scores.

The recommendation scores are invented in a specific way worth knowing: they
assume the nutrient weighting the recommender does not do yet, so the list is
what the product should produce, not what today's engine produces.

---

## The parts, and what each depends on

| Part | Where | Waiting on |
|---|---|---|
| Recipe and recommendation screens | `web/src/features/` | Nothing; they work on fixtures |
| Reviewer screen | `web/src/features/review/` | Nothing; decisions are stored per browser until the database exists |
| Backend | `api/app/` | Nothing to run; `MAZI_REPO=supabase` is not written yet |
| Rule matches on a recipe | fixtures | The rules workstream: links with the position they hit |
| Ranked recommendations | fixtures | The recommender workstream: a Python function we wrap |
| AI text | generated locally | Nothing, but it needs a model on the machine |

The contract between these is `api/SPEC.md`. It is the thing to read before
changing a payload.

---

## The AI text

Suggestions are not written while someone waits. They are generated offline
against the rules, checked, reviewed, and then served as data:

```bash
# generate for the example recipes, using a local model
api/.venv/bin/python -m mlx_lm.server --model mlx-community/gemma-3-4b-it-4bit --port 8081
MAZI_PROVIDER=local MAZI_LLM_URL=http://127.0.0.1:8081/v1 \
  MAZI_LLM_MODEL=mlx-community/gemma-3-4b-it-4bit \
  api/.venv/bin/python api/pregenerate.py
```

Two guards decide whether a model's words are used at all: it may not introduce
a number the source rule did not contain, and a summary may not quietly drop a
rule it claims to cover. When either fires, the rule's own wording is used
instead and the response says so. See `api/README.md` for what the models did on
the example recipes.

No model runs in a deployed build. The text it produced is data by then.
