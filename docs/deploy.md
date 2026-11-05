# Deploying the screens

The first deployment is the front end only: a static site on Vercel's free
tier, serving the example data that is committed with it. No database, no
server, no model, nothing to pay for, nothing with a key in it.

That is not a compromise for the demo — it is how the product is meant to
work. AI text is written offline, reviewed, and shipped as data, so a live
site never needs a model.

---

## What goes live

| Screen | URL | Where its data comes from |
|---|---|---|
| Recommendations | `/#/recommend` | `web/src/shared/fixtures/` |
| Recipe | `/#/cook/falafel-001` | same |
| Reviewer | `/#/review` | same; decisions are saved in the visitor's own browser |
| The original app | `/` | unchanged |

Every screen shows **Offline sample** in the top right, because nothing is
calling a backend. That badge is honest and should stay.

The recipe screen carries the text Gemma 3 4B wrote and a reviewer approved —
it is baked into the fixtures at build time by `api/build_fixtures.py`, from
whatever is `approved` in `api/content/`.

## What does not go live, and why

- **The assistant's question box** is disabled. Answering a free question needs
  a model at request time, and we are not hosting one. The box says so.
- **Regenerate** is hidden for the same reason.
- **Reviewer decisions on suggestion text are per browser.** They move to a
  database when there is one; until then two people reviewing see different
  things. Nutrition-plausibility verdicts are not like this - they go to
  `recipe_nutrition_reviews` through the API, with the reviewer taken from the
  verified token, so everyone sees the same ones.

---

## Deploy it

Everything below is done once, in a browser, by someone with access to the
GitHub repository.

1. Sign in to vercel.com with GitHub, on the account that can see
   `Surabhi21072001/Mazimeal_CMU`.
2. **Add New → Project**, import that repository.
3. **Root Directory** can be left alone. The repository root has its own
   `vercel.json` that installs and builds inside `web/` and publishes
   `web/dist`, so a default import works. Setting it to `web` also works, and
   then `web/vercel.json` applies instead.

   This is worth knowing because the front end is not at the repository root,
   which usually means the importer has to be told where it is. Here they do
   not.
4. Leave Environment Variables empty. Everything the build needs is in the
   repository, in `web/.env.production`, which Vite reads for `vite build`.
   Keeping it there rather than in the dashboard means the deployment can be
   rebuilt from a checkout alone, and the reasoning sits next to the values.

   That file sets `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`, which is
   what makes sign-in work. Both are public: every `VITE_` value is compiled
   into the bundle, so nothing secret can live there. The publishable key
   (once called `anon`) has no privileges of its own, and the two tables
   behind the admin and review writes have row-level security enabled with no
   policy at all, so the key cannot read them even in principle.

   It deliberately does not set `VITE_API_BASE_URL`. Unset means the deployed
   backend at `https://mazimeal-api.onrender.com`; a local URL points a dev
   build at a local API; an empty string forces the bundled fixtures and runs
   with no backend at all. Unset and empty mean different things here, on
   purpose — which is why a local `web/.env.local` sets it and the committed
   production file does not.

   `VITE_EMAILJS_*` stay unset: they are the original app's signup email, and
   that feature disables itself when they are missing.
5. Deploy. The first build takes about a minute.

The production URL serves the original app; the screens are at `/#/recommend`
and `/#/cook/falafel-001`.

### After that

`main` is the deployed branch, for both Vercel and Render. It was not always:
the screens were built on `front-backend` while `main` held the rules engine
alone, which is why Vercel could not build from it. `front-backend` was
fast-forwarded into `main`, so the two were identical at that point and there
is one branch to reason about.

Every push to another branch still gets its own preview URL. The CORS pattern
on the backend covers those hosts, so a preview can call the API like
production can.

---

## When the backend joins

Nothing about the front end changes. It reads `VITE_API_BASE_URL`, and the
badge switches from **Offline sample** to **Backend · sample data**, then to
**Live** when the repository behind the API is a real database.

The backend needs a container host rather than Vercel's serverless functions:
the recommender is expected to use an OR solver, and those packages are larger
than a function bundle allows. Render's free tier fits, with the caveat that
it sleeps when idle and the first request after that waits about a minute.

The database is Supabase. It is not needed for this deployment and is best
left until the backend is ready to use it, since a free project pauses after
about a week of no traffic.

### Environment on the API host

`render.yaml` is a blueprint, so Render applies every variable in it on each
sync. Only the two marked `sync: false` are typed into the dashboard, because
they carry the database password.

| Variable | Set in | What it does |
|---|---|---|
| `SUPABASE_DB_URL` | dashboard | the Postgres connection string. Everything live reads it. |
| `MAZIMEAL_DSN` | dashboard | the same string under the name the rules engine reads. |
| `SUPABASE_URL` | `render.yaml` | the project root. The API fetches `/auth/v1/.well-known/jwks.json` from it to verify the caller's token. Not sensitive — the browser bundle already carries it. Without it, admin and review writes answer 503 and nothing else changes. |
| `MAZI_ADMIN_EMAILS` | `render.yaml` | comma-separated, who may approve a rule change. Anyone signed in may propose one; only an address on this list may approve it. |

`MAZI_ADMIN_EMAILS` lives in the environment rather than in a table on
purpose. A table the admin screen can edit is a table that whoever reaches the
admin screen can add themselves to.

No JWT secret is needed. The project signs tokens with ES256 and publishes the
matching public keys, so the API verifies them locally with nothing shared.
