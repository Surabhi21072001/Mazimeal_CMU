# API reference

Every HTTP surface this product has, what it takes, what it returns, and what
an account is needed for. Written for whoever changes one of them next — in
particular the recipe-optimizer work, which owns the rules engine mounted at
`/rules`.

Production: `https://mazimeal-api.onrender.com` (Render, free plan, so the
first request after idle takes ~30 s to wake).
Health: `GET /api/health` → `{"status":"ok","repo":"supabase","provider":"template","rules_engine":"/rules","model":null}`

This is the only endpoint document. **Payload shapes** follow the endpoint
tables, with a real response for each.

---

## Three things serve the browser, not one

| Who | How it is reached | What it owns |
|---|---|---|
| `api/app/` | `https://mazimeal-api.onrender.com/api/*` | Recipes with their matched rules, the suggestion text, the review records, the rules admin |
| `scripts/api.py` | the same host, under `/rules/*` | The rules engine's own API. A separate FastAPI app mounted into the same process |
| Supabase | the browser calls PostgREST directly with the publishable key | The household tables, the planner, and the recommender's functions |

One process serves the first two. `api/app/main.py` mounts the second with
`app.mount("/rules", rules_api.app)`, which means one cold start instead of two
and no network hop when this app asks the engine a question — it imports
`recipe_facts`, `detect_rules` and `evaluate_rules` and calls them with a
psycopg connection.

**If you change the engine's function signatures, the backend breaks silently
at import time, not in a test.** The three it calls in-process are:

```python
recipe_facts.facts_for(conn, recipe_id, ...)
detect_rules.detect(conn, facts, ...)
evaluate_rules.evaluate(conn, ...)
```

Keep their keyword arguments defaulted and new return keys additive, and
nothing here has to change.

---

## `/api/*` — this repository's backend

**Auth** is one of three:

- **open** — no token. Reading the rules and the recipes needs no account:
  they are published research with their sources, already on every screen.
- **signed-in** — a verified Supabase access token in `Authorization: Bearer`.
  Fails with 401 and `{"error":"no_token"}` or a signature/expiry error.
- **reviewer** — signed in *and* on the reviewer list. A signed-in non-reviewer
  gets **403** `{"error":"not_an_admin","email":…}`, not 401, so retrying with
  a fresh login is pointless. The list is `MAZI_ADMIN_EMAILS` (environment,
  which no request can change) ∪ the `app_admins` table (which the admin
  screen edits). It is keyed by email and checked per request, so a grant can
  precede the person's signup.

🍽 marks the endpoints whose output changes when the rules engine changes.

### Recipes and generated text

| | Endpoint | Auth | Input | Returns |
|---|---|---|---|---|
| 🍽 | `GET /api/recipes/{recipe_id}` | open | — | The recipe: ingredients, `nutrition_per_serving`, steps, and `matched_rules` — each with `rule_id`, `status`, `applies_to`, evidence tier and source. Plus `source` (`supabase` or `fixtures`). 404 `recipe_not_found` |
| 🍽 | `POST /api/recipes/{recipe_id}/suggestions` | open | `{member_id?, rule_ids?}`, `?refresh=true` to rewrite | `{suggestions[], summary, source, model, generated_in_ms, disclaimer}`. `source` is `reviewed`, `cache`, `local` or `template`. Reviewed text wins over anything a model would write now |
| 🍽 | `GET /api/recipes/{recipe_id}/review` | open | — | `{recipe_id, version}` — the reviewed version a cook should see, or `version: null`. Open on purpose: a correction only its author can see is the thing this replaced |
| 🍽 | `POST /api/recipes/{recipe_id}/evaluate` | signed-in | `EvaluateBody`: `member_id?`, `meal_context?`, `conditions?`, `medications?`, `supplements?`, `goals?`, `activity_level?`, `life_stage?`, `equipment?` | The rules that fire for this recipe *for this person and meal*. All fields optional; an empty body evaluates the recipe alone. `null` and `[]` differ on purpose: `null` is "did not say", `[]` is "there are none" |
| | `POST /api/recipes/{recipe_id}/ask` | open | `{question, member_id?}` | A grounded answer about one recipe, refused when the question strays. Not cached, not reviewed |
| | `GET /api/seed-recipes` | open | — | The recipe list the team works against |
| | `GET /api/household` | open | — | One household and its members with their nutrient targets |
| | `GET /api/recommendations` | open | `?member_id&meal&target_nutrient&limit` | Ranked meals for one member |
| | `GET /api/health` | open | — | Which repo, provider and model are live |
| | `POST /api/cache/clear` | open | — | Drops the suggestion cache. Exists for the model comparison. Unauthenticated, which is worth closing before there is anything expensive behind it |

### Content review — the reviewer's decisions

A decision is an append-only row in `recipe_content_versions`, **including
"confirmed, nothing changed"**, because an absence of rows cannot be told apart
from an absence of reviewers.

| | Endpoint | Auth | Input | Returns |
|---|---|---|---|---|
| 🍽 | `GET /api/review/content/{recipe_id}` | reviewer | — | `{record, payload, fingerprint, reviewer}`. Writes version 1 if the recipe has never been opened, from the same payload the suggestions endpoint serves — the server produces the baseline rather than accepting one, because it is what every later diff is read against |
| 🍽 | `POST /api/review/content/{recipe_id}` | reviewer | `{outcome, suggestions?, summary?, rules_removed?, status_overrides?, position_overrides?, headline_rule_id?, not_optimizable?, tags[], note?}` | `{record, reviewer}`. `outcome` is one of `confirmed_unchanged`, `edited`, `rejected`, `reverted_to_original`. **Every other field is optional and a field left out is inherited from the current version, not cleared** — two reviewers on one recipe must not undo each other by omission. No `reviewer` field: it comes from the token |
| | `GET /api/review/content-stats` | reviewer | — | How many recipes have been reviewed, and the unchanged rate |

`rules_removed` means "this rule does not apply to **this** recipe". It never
touches the rule itself, which belongs to the research database and applies to
400 other recipes.

### Nutrition review — whether the numbers can be right

| Endpoint | Auth | Input | Returns |
|---|---|---|---|
| `GET /api/review/nutrition` | open | — | The queue, with each recipe's disagreement between stored and computed values |
| `GET /api/review/nutrition/{recipe_id}/history` | open | — | Every verdict recorded for one recipe |
| `POST /api/review/nutrition/{recipe_id}` | signed-in | `{verdict, reason?}` | The row written. Neither the ratio nor the reviewer comes from the body: both are taken from the database and the token, so a verdict always records what was actually on screen and who actually decided |

### Rules admin

Reading is open — published research. Proposing a change needs an account.
Approving one needs to be a reviewer.

| | Endpoint | Auth | Input | Returns |
|---|---|---|---|---|
| 🍽 | `GET /api/admin/rules` | open | `?q&category&status&reach=reachable\|unreachable&active&limit` | `{count, items, categories}`. `reach` is the useful one: `unreachable` lists the rules that can never fire because no ingredient carries their trigger code |
| 🍽 | `GET /api/admin/rules/{rule_id}` | open | — | One rule in full. 404 `no_such_rule` |
| | `GET /api/admin/rules/summary` | open | — | Counts by category, status and reach |
| | `GET /api/admin/rules/next-id` | open | `?category` | The next free `rule_id`; the prefix follows the category |
| 🍽 | `GET /api/admin/codes` | open | `?field=trigger_code\|target_code\|action_code&q` | The code vocabulary with what each code reaches |
| 🍽 | `POST /api/admin/codes` | signed-in | `{code, code_type?, display_name, description?}` | A new word for the vocabulary. Safe to be unreviewed: no ingredient carries the new code yet, so no rule naming it can fire |
| | `GET /api/admin/rule-requests` | reviewer | `?status&limit` | The queue of proposed rule changes |
| | `POST /api/admin/rule-requests` | signed-in | `{kind, rule_id, proposed, note?}` | A proposal. No `submitted_by`: the author comes from the token. A client-supplied author on an audit record is not an author |
| 🍽 | `POST /api/admin/rule-requests/{request_id}/decide` | reviewer | `{approve, note?}` | Approving writes the change to `business_rules`, which changes what fires on every recipe |

### Accounts

| Endpoint | Auth | Input | Returns |
|---|---|---|---|
| `GET /api/admin/me` | signed-in | — | Who the server thinks is calling, and whether they are a reviewer. The admin page asks before it renders |
| `GET /api/profile/me` | signed-in | — | The signed-in person's own profile, keyed on the token rather than a uuid in a query string |
| `GET /api/admin/people` | reviewer | — | The reviewer list, both sources, and which entries can be revoked |
| `POST /api/admin/people` | reviewer | `{email, note?}` | Grants review access. No `granted_by`: it comes from the token |
| `DELETE /api/admin/people/{email}` | reviewer | — | Revokes it. An address in `MAZI_ADMIN_EMAILS` cannot be revoked by a request |

---

## Payload shapes

Four shapes carry almost everything. Every example below is a real response,
trimmed; `api/fixtures/*.json` holds complete ones you can read offline.

### A matched rule

The important field is `applies_to`. A rule list alone is not enough: without
it the cook screen cannot highlight the ingredient inside a step, cannot put
the "Key Step" badge on the right row, and cannot show a synergy card against
the pair that caused it.

```json
{
  "rule_id": "BIO-002",
  "name": "Crush garlic and rest before heating",
  "status": "not_satisfied",
  "automation_status": "recipe_safe",
  "evidence_tier": "B",
  "target_code": "CMP_ALLICIN",
  "target_nutrient": "allicin formation",
  "applies_to": {
    "type": "ingredients",
    "line_ids": ["1921a006-3773-4a15-811e-61ef1e077d69"],
    "step_numbers": [2]
  },
  "engine_action": "When garlic is cooked, place crushing/mincing before a short rest, then add later or cook gently.",
  "why": "Tissue disruption lets alliinase convert alliin to allicin; heat can inactivate alliinase",
  "source_url": "https://pubmed.ncbi.nlm.nih.gov/11160543/"
}
```

`status` is what the recipe already does about the rule — `not_satisfied` is a
change worth making, `satisfied` is something already working in the cook's
favour, and the suggestion text orders them that way. `line_ids` are
`recipe_ingredients.line_id` uuids, not positions.

`step_numbers` is **approximate**: a rule marks the steps whose text names the
ingredient it fired on, and marks nothing when the method never names it
("remaining marinade ingredients"). A wrong mark costs more than a missing one.
The exact version needs the engine to say which step it means.

### A nutrition number

Every one of them carries where it came from, because that is this project's
answer to the client's worry about invented numbers:

```json
{
  "nutrient": "Energy",
  "label": "Calories",
  "value": 464.2,
  "unit": "kcal",
  "source": "published",
  "confidence": 1.0,
  "published_value": 464.2,
  "derived_value": 183.4,
  "derived_over_published": 0.4,
  "pct_of_target": null,
  "top_sources": []
}
```

`published` is the value the dataset states for the recipe; `derived` is
computed from ingredient grams times USDA values per 100 g. Both are kept
because disagreement between them is the signal: the 0.4 above says the
ingredients account for well under half the stated calories, which is a
gram-weight problem rather than a calorie one. Energy is the only nutrient with
both values for every recipe, which is why the nutrition review queue is built
on that one ratio.

### A recommendation

```json
{
  "recipe_id": "souvlaki-002",
  "name": "Chicken Souvlaki",
  "meal": "Lunch",
  "kcal_per_serving": 811.8,
  "time_min": 60,
  "tags": ["weeknight"],
  "score": 91.2,
  "nutrient_contribution": {
    "nutrient": "Iron", "per_serving": 11.1, "unit": "mg",
    "pct_of_remaining_need": 46, "source": "derived", "confidence": 0.6
  },
  "matched_rule_ids": ["SYN-002"],
  "why": "Most iron of the lunches that fit her day, and it is already a Mediterranean dish she likes.",
  "blocked_by": null
}
```

`GET /api/recommendations` returns these under `results`, plus a `blocked`
list of the ones the filter removed, each with
`blocked_by: {"reason": "household allergen", "detail": "peanut butter"}`.
The screens show a few on purpose: a recommender that visibly refuses food is
more convincing than one that only shows winners.

**`score` and `why` are not yet produced by a recommender.** The response
carries a `_fixture_note` saying so: the scores assume an iron weighting the
engine does not do. Treat this shape as the contract and the numbers as
illustrative.

### A household member

```json
{
  "member_id": "maya", "name": "Maya", "age": 31, "sex": "F",
  "conditions": ["iron_deficiency"],
  "preferences": {"allergies": ["peanut"], "dislikes": ["mushroom"],
                  "dietary_patterns": [], "cuisines": ["Mediterranean"]},
  "targets": [
    {"nutrient": "Iron", "unit": "mg", "target": 27.0, "baseline": 18.0,
     "consumed": 3.1, "remaining": 23.9, "upper_limit": 45.0,
     "adjusted_by": ["IRON_COND_ANY_C002_001"]}
  ]
}
```

`baseline` is the DRI for the member's age and sex; `target` is that baseline
after the condition rules in `adjusted_by` have been applied, which is why both
are kept. `remaining` is what the recommender ranks on.

### The suggestion response

```json
{
  "recipe_id": "falafel-001",
  "suggestions": [
    {"rule_id": "BIO-002", "headline": "Crush garlic and rest before heating",
     "body": "When garlic is cooked, place crushing/mincing before a short rest …",
     "evidence_tier": "B", "source_url": "https://pubmed.ncbi.nlm.nih.gov/11160543/",
     "status": "not_satisfied"}
  ],
  "summary": {"text": "Worth doing: … Already working in your favour: …"},
  "source": "template", "model": null, "generated_in_ms": 2,
  "disclaimer": "…"
}
```

Every suggestion names the rule it came from and that rule's source, so a cook
can follow any sentence back to the research. `source` is `reviewed`, `cache`,
`local` or `template`.
---

## `/rules/*` — the rules engine's own API

Owned by the recipe-optimizer work (`scripts/api.py`). Mounted into the same
process, keeping its own paths so its Postman collection still works.

| Endpoint | Returns |
|---|---|
| `GET /rules/api/recipes` | The recipe list, with filters |
| `GET /rules/api/recipes/{recipe_id}` | One recipe |
| `GET /rules/api/recipes/{recipe_id}/evaluate` | The rules that fire, evaluated on the recipe alone. `?user_id=` also takes a seeded demo profile into account |
| `POST /rules/api/login` | The engine's own login, predating Supabase auth |
| `GET /rules/health` | Its own health |

Two things worth knowing before changing these:

1. `/rules/api/recipes/{id}/evaluate` is a **GET**; this repository's
   `/api/recipes/{id}/evaluate` is a **POST** that also takes the member and
   the meal. They are different endpoints with the same name, not two versions
   of one.
2. `POST /rules/api/login` issues its own credential and is unrelated to the
   Supabase token every `/api/*` write is checked against. Nothing in the
   frontend calls it.

---

## What the browser reads straight from Supabase

Not everything goes through the API. The frontend holds the publishable key
and calls PostgREST directly for:

| Call | Used by | State in production |
|---|---|---|
| `from("recipes")`, `from("recipe_steps")`, `from("recipe_nutrition")` | the recipe detail screen | works |
| `from("households")`, `from("household_members")`, `from("member_conditions")` | sign-up and the profile screens | works |
| `rpc("fn_home")` | the home dashboard | **404 — not installed.** The page falls back to `homeSnapshot.json` and reports `source: "snapshot"` |
| `rpc("fn_recipe_nutrition")` | the recipe detail nutrition panel | **404 — not installed** |
| `rpc("fn_log_meal")` | logging a meal | **404 — not installed** |
| `from("weekly_plans")` | saving the planner | **404 — the table does not exist** |

Those four come from `recommender/db/`, which has never been installed into the
live project. See [HANDOFF.md](HANDOFF.md).

The publishable key carries no privileges of its own. Row-level security
decides what it can reach, and `app_admins`, `recipe_content_versions`,
`recipe_nutrition_reviews` and `rule_change_requests` all have RLS enabled with
**no policy at all**, so the browser key cannot read them even in principle —
every reviewer write goes through the API with a verified token.

---

## Getting a token to try a closed endpoint

```bash
# sign in and keep the access token
TOKEN=$(curl -s -X POST "$SUPABASE_URL/auth/v1/token?grant_type=password" \
  -H "apikey: $SUPABASE_ANON_KEY" -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"…"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

curl -s https://mazimeal-api.onrender.com/api/admin/me -H "Authorization: Bearer $TOKEN"
```

The API verifies signature, expiry and audience against the project's published
ES256 keys (`<SUPABASE_URL>/auth/v1/.well-known/jwks.json`), so no shared secret
is involved. A token minted for another audience — a service key, say — fails
at `aud`.

---

## Errors

| Status | Body | When |
|---|---|---|
| 400 | `{"error":"empty_question"}` | `/ask` with nothing in it |
| 401 | `{"error":"no_token"}` | a closed endpoint with no `Authorization` header |
| 401 | a signature or expiry error | a token this project did not issue, or an expired one |
| 403 | `{"error":"not_an_admin","email":…}` | signed in, but not on the reviewer list |
| 404 | `{"error":"recipe_not_found","recipe_id":…}` | unknown recipe |
| 404 | `{"error":"no_such_rule","rule_id":…}` | unknown rule |

Every successful payload carries `source`, so the frontend can say whether it
is looking at the live database, a fixture, a cache or reviewed text. The badge
in the top right of each screen is reading that field.
