# Handoff

What is running, who wrote what, and what is still open. Everything in here was
checked against the live systems rather than remembered; where a thing is
broken it says so, and where something is a judgement call it says who made it.

Last verified: 2026-11-19.

---

## Where it runs

| Piece | Host | Address | Notes |
|---|---|---|---|
| Frontend | Vercel | `https://mazimealcmu123.vercel.app` | Static build. `vercel.json` builds `web/` and rewrites everything except `/assets/*` to `index.html`, because the app is hash-routed |
| API | Render | `https://mazimeal-api.onrender.com` | Free plan: it sleeps, so the first request after idle takes ~30 s. `render.yaml` is a blueprint — every setting is in the repo except the two that carry the database password |
| Database | Supabase | project `vvoxzwktnalrodukachl`, region us-west-2 | Postgres. Also the auth provider |

Render deploys branch `main`. The API connects through Supabase's pooler host
(`aws-1-us-west-2.pooler.supabase.com:5432`) — the direct `db.*.supabase.co`
host is IPv6-only and unreachable from many networks, which is a half-day to
rediscover.

### The repository exists twice, and one of them is the real one

```
Surabhi21072001/Mazimeal_CMU   canonical. Vercel and Render build from this.
mazimeal/platform              the original starting point. Not maintained.
```

`Mazimeal_CMU` is the one to transfer. `mazimeal/platform` is where the project
started and is where to look if a piece of history seems to be missing, but
nothing deploys from it.

Three pieces of work never made the crossing, and they are worth a decision
rather than a shrug — this was checked commit by commit, not assumed:

| On `mazimeal/platform` | What it is |
|---|---|
| `dev` → PR #11, merged 2026-11-11 | ~4,000 lines of the recommendation and data work: `recommender/db/{93_functions,96_member_logs,98_home,98_member,98_fills}.sql`, migrations 007–011, `schema/seed/recipe_content.sql` (1,513 lines), `schema/seed/recipe_fills.sql`, two generator scripts, and the "live home page" frontend changes |
| `recipes-results-v2`, unmerged | 1,452 lines: recommender v2, `98_targets.sql`, migrations 012–014, a rules→SQL loader, and a new Results screen. Its `features/recipes/RecipesPage.jsx` is a different file with the same path as the one on `Mazimeal_CMU`, so this one genuinely collides |
| `user_module_sign_out`, unmerged | "Add real sign out", two files |

**PR #11 is the one that matters.** It is not that `Mazimeal_CMU` has no
recommender functions — it has `fn_home`, `fn_recipe_nutrition` and
`fn_log_meal`, they were simply never installed into the live project. It is
that PR #11 holds a *newer* `98_home.sql` and `93_functions.sql`, plus five
files and five migrations that `Mazimeal_CMU` does not have at all:
`fn_member_day`, `fn_member_streak`, `fn_log_hydration`, `fn_log_sleep`,
`fn_toggle_favorite`, `fn_compute_member_targets`, `fn_fill_recipe_derived`
and the allergen map. Installing from `Mazimeal_CMU` gives you a working but
older schema. It would merge cleanly apart from two files: `.gitignore`, and
`HomeDashboardClassic.jsx` where both sides changed (114 lines added there
against 11 removed here).

Whether to port it belongs to the recommendation workstream, not to whoever
reads this first. But nobody should install `recommender/db/` from
`Mazimeal_CMU` without knowing that a newer version of those files exists.

---

## What the data is

**There is no real data in this database. No real person has an account, and
nothing in it is a measurement anyone has signed off.**

| Table | Rows | What it is |
|---|---|---|
| `recipes` | 400 | From the public Food.com dataset |
| `ingredients` | 559 | Names normalised from those recipes |
| `recipe_ingredients` | 3,063 | The lines, with gram weights derived from USDA household measures |
| `recipe_steps` | 3,158 | Step text |
| `ingredient_nutrition` | 15,278 | USDA FoodData Central values |
| `business_rules` | 54 | The client's own rules workbook — rule ids, evidence tiers, automation status and source links are real |
| `rule_codes` | 123 | The vocabulary rules are written in |
| `ingredient_rule_tags` | 505 | Which ingredients carry which codes. This is what decides whether a rule can fire at all |
| `app_admins` | 2 | The reviewer list |
| `rule_change_requests` | 1 | One test proposal |
| `recipe_content_versions` | 0 | Reviewer decisions on generated text. Empty: deliberately cleared after testing, so the first real review is the first row |
| `recipe_nutrition_reviews` | 0 | Verdicts on whether the numbers can be right |
| `auth.users` | 3 | Two test accounts and the incoming owner's |

24 tables, 2 views, 9 functions in `public`.
[docs/DATA.md](DATA.md) is the guide to changing any of it safely, and its
"Where the work is" section ranks what is actually wrong with the data — the
most useful page in this repository for anyone picking up the rules work.

A deliberate non-action worth knowing: the one piece of text a reviewer had
approved under the old file-based store was **not** backfilled as a review
version. That format never recorded whether the reviewer had edited the
wording, so importing it under either outcome would have corrupted the
unchanged rate — the number the review process exists to produce.

---

## Who wrote what

Four workstreams, and the split still shows in the directory layout.

| Directory | Written mostly by | What it is |
|---|---|---|
| `web/` | front-and-back-end work | The screens. `src/features/synergia-light/` is the inherited app shell (6,900 lines) and still owns sign-up; everything under `src/features/{cook,recipes,recommend,review,admin}/` is newer |
| `api/` | front-and-back-end work | The backend, the review records, the generated text and its guards |
| `scripts/` | rules work + data work | The rules engine (`recipe_facts`, `detect_rules`, `evaluate_rules`, `engine_rules`, `evaluation_context`) **and** the one-off data pipeline that built the seed data (`import_foodcom`, `match_usda`, `ingredient_grams`, `fill_ingredient_nutrition`, `tag_ingredients`, …). Both live here; the first group is imported by `api/`, the second is run by hand and documented in [schema/seed/README.md](../schema/seed/README.md) |
| `schema/` | data work + others | DDL in load order, then `migrations/` in number order, then `seed/` |
| `recommender/` | recommendation work | A separate database schema with its own installer and scoring. **Never installed into the live project** — see below |
| `tests/` | rules work + front-and-back-end work | pytest |

[docs/BRANCHING.md](BRANCHING.md) has the per-file ownership rules the team
worked under.

---

## What is broken or unfinished

Ordered by how likely it is to surprise someone.

### 1. The recommender's schema was never installed

`recommender/db/` defines `fn_home`, `fn_recipe_nutrition`, `fn_log_meal` and
the `weekly_plans` table. None of them exists in the live project. Verified by
calling each one with the publishable key:

```
rpc/fn_home              404 PGRST202
rpc/fn_recipe_nutrition  404 PGRST202
rpc/fn_log_meal          404 PGRST202
weekly_plans             404 PGRST205 (no such table)
```

Consequences in production today:

- The home dashboard catches the failure and falls back to
  `web/src/features/home/homeSnapshot.json`, reporting `source: "snapshot"`.
  It looks right and is not live.
- The recipe detail nutrition panel falls back the same way.
- **Logging a meal and saving the planner do not persist.** Nothing tells the
  person; the write just fails.

Fixing it means running `recommender/db/install.sql` against the project, which
is the recommendation work's own call to make — their README documents the
order and the pgvector prerequisite. Read the repository note above first:
newer versions of several of these files, and five they do not include at all,
are sitting on `mazimeal/platform`'s `dev` branch and have never been merged
here. Installing the copy in this repository works; it is just not the latest
the team wrote.

### 2. Email confirmation is turned OFF

This is the one to reverse first.

Supabase's built-in mail service sends **2 emails per hour project-wide** and
delivers only to addresses on the project team. A signup that hits that limit
returns HTTP 429 and **creates no user row**, after which a sign-in attempt
reports `Invalid login credentials` — which reads as "wrong password" and sent
the incoming owner round in circles for a week.

The temporary unblock was to turn off *Authentication → Sign In / Providers →
Email → Confirm email*. That works, and it means **anyone can register any
address without owning it**. Configure custom SMTP (SendGrid, Resend, SES) and
turn confirmation back on before anyone outside the team signs up.

### 3. One migration is committed but not applied

`schema/migrations/013_recipe_equipment.sql` has never been run against the
live database. This is safe — `scripts/recipe_facts.py` guards the table with
`_table_exists` and skips that path when it is missing — but until it is run,
equipment-dependent rules (cast iron, and the rest of SYN-012's family) cannot
fire. It belongs to the rules work.

Migration numbers must stay contiguous and unique; `tests/test_tag_data.py`
fails otherwise. It already caught two branches both claiming `013`.

### 4. Two endpoints are more open than they should be

| Endpoint | Today | Should be |
|---|---|---|
| `POST /api/cache/clear` | no token | reviewer, or removed — it exists for a model comparison that is finished |
| `POST /api/admin/codes` | signed-in | arguably reviewer. It is defensible as-is: a new code reaches no ingredient, so no rule naming it can fire |

Everything that writes a reviewer decision or a rule change is already gated on
a verified token, with the author taken from the token and never from the
request body.

### 5. Frontend lint debt, deliberately left

`npm run lint --prefix web` reports 5 errors, all
`react-hooks/set-state-in-effect`, all in the inherited app shell. Each is a
real pattern — `setState` called synchronously inside an effect — and fixing
them means changing how those screens hold state. That is a refactor, not a
cleanup, so they were left alone rather than silenced.

### 6. npm advisories: 5, one root cause, build tooling only

`picomatch` has a ReDoS advisory whose range covers **every published version
including the latest**, reached through vite's globbing. npm's suggested "fix"
is to downgrade vite to 6, which is worse. Nothing in the shipped browser
bundle is affected. The other nine advisories were cleared with non-major
updates, including `ws` 8.23.0 — the only one that was in the production
dependency tree, and even that is never bundled, because browsers use their own
WebSocket.

---

## Security as it stands

What is already right, so nobody undoes it by accident:

- **The connection string is not in the repository**, in any form, and CI fails
  any commit that adds one. It lives in `.env` (gitignored) and in the Render
  dashboard as a `sync: false` variable.
- **`web/.env.production` is committed on purpose.** `VITE_*` variables are
  compiled into the browser bundle, so nothing secret can live there. The
  publishable key carries no privileges of its own.
- **Four tables have RLS enabled with no policy at all** — `app_admins`,
  `recipe_content_versions`, `recipe_nutrition_reviews`, `rule_change_requests`.
  Neither the anonymous nor the authenticated browser key can reach them even
  in principle. Every reviewer write goes through the API with a verified
  token.
- **No policy grants `anon` a write** anywhere in the project (checked against
  `pg_policy`). An earlier `web/supabase-schema.sql` did exactly that for
  `weekly_plans` with `USING (true)`; it has been deleted, and
  `recommender/db/95_rls.sql` exists to replace it.
- **Reviewer and author always come from the verified token**, never from the
  request body. A list of who may approve changes is worth nothing if the
  browser fills in who authorised each entry.
- **`tests/dbguard.py` refuses any non-local DSN**, so a test run cannot
  truncate the shared database. Proven by pointing `MAZIMEAL_TEST_DSN` at
  Supabase and watching it refuse.

What is not done: the team ran on one shared database login, and nobody has
their own role, so the audit trail in Postgres means little. Fix that before
real data goes in. [docs/accounts.md](accounts.md) covers sign-in and the
reviewer list; test-account passwords are deliberately not in the repository.

---

## CI

`.github/workflows/ci.yml`, four jobs, all blocking:

| Job | What it does |
|---|---|
| `secrets` | Fails if `.env` is tracked or a password-shaped string is committed |
| `web build` | `npm ci && npm run build` on Node 22 |
| `python tests` | `pytest tests -q` — 519 pass, 171 skip, no database needed |
| `schema loads` | Loads every `schema/[0-9][0-9]_*.sql` into a clean Postgres 16 and runs `99_validate.sql` |

The `schema` job does not load `schema/migrations/*.sql`. Worth adding: the
numbering test catches collisions, but nothing proves the migrations still
apply in order to a fresh database.

---

## A first week, in order

1. **Transfer `Mazimeal_CMU`** — the canonical copy, and the one both hosts
   build from. Decide separately what happens to the three stranded branches
   on `mazimeal/platform` above; PR #11 is the one worth porting.
2. **Take over the three accounts** — Vercel, Render, Supabase — and rotate the
   database password, which means updating the two `sync: false` variables in
   Render.
3. **Configure custom SMTP and turn email confirmation back on.** Until then
   anyone can register any address.
4. **Install `recommender/db/`** or decide the home dashboard stays on its
   snapshot, and make the planner's failure visible instead of silent.
5. **Run `schema/migrations/013_recipe_equipment.sql`**, then re-check that the
   equipment rules fire.
6. Read [docs/DATA.md](DATA.md)'s "Where the work is" section. Twelve rules can
   never fire as the data stands, and only a fraction of the 559 ingredients
   are tagged at all. That is where the product's quality actually lives, and
   it is data work rather than code work.

### Watching one rule change reach a recipe

The thing most worth seeing on day one, and the honest limit of it:

```bash
# 1. a rule, as the admin screen shows it. SYN-005 is picked because it is
#    one of the 19 that fire on the recipe in step 2
curl -s https://mazimeal-api.onrender.com/api/admin/rules/SYN-005 | python3 -m json.tool

# 2. the same rule firing on a recipe
curl -s https://mazimeal-api.onrender.com/api/recipes/falafel-001 \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);print([r["rule_id"] for r in d["matched_rules"]])'

# 3. the text a cook reads, and whether a reviewer has approved it
curl -s https://mazimeal-api.onrender.com/api/recipes/falafel-001/review | python3 -m json.tool
```

Edit that rule in `#/admin`, approve the request, and step 2 changes — rule to
recipe is live and end-to-end. Rule to *recommendation* is not: the
recommender does not yet weight by the nutrient a member still needs, so the
ranked list is what the product should produce rather than what today's engine
produces. The fixtures' recommendation scores are invented in exactly that way,
and say so in their `_fixture_note`.
