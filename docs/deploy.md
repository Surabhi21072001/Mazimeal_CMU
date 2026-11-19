# Deploying

Three hosts, all on free plans, all deployed from `main`. What is currently
running and in what state is in [HANDOFF.md](HANDOFF.md); this file is how to
do the deployment, and the things about it that are easy to get wrong.

| Piece | Host | Deployed from |
|---|---|---|
| The screens | Vercel | `main`, build inside `web/` |
| The API and the rules engine | Render | `main`, `render.yaml` blueprint |
| The database and auth | Supabase | not deployed from git — see [DATA.md](DATA.md) |

AI text is written offline, reviewed, and shipped as data, so no model runs in
a deployed build and none of these hosts needs a GPU or a model key.

---

## The screens, on Vercel

Done once, in a browser, by someone with access to the GitHub repository.

1. Sign in to vercel.com with GitHub, on the account that can see
   `Surabhi21072001/Mazimeal_CMU`.
2. **Add New → Project**, import that repository.
3. **Root Directory** can be left alone. The repository root has its own
   `vercel.json` that installs and builds inside `web/` and publishes
   `web/dist`, so a default import works. Setting it to `web` also works, and
   then `web/vercel.json` applies instead.

   This is worth knowing because the front end is not at the repository root,
   which usually means the importer has to be told where it is. Here it does
   not.
4. **Leave Environment Variables empty.** Everything the build needs is in the
   repository, in `web/.env.production`, which Vite reads for `vite build`.
   Keeping it there rather than in the dashboard means the deployment can be
   rebuilt from a checkout alone, and the reasoning sits next to the values.
5. Deploy. The first build takes about a minute.

`vercel.json` also rewrites everything except `/assets/*` to `index.html`,
because the app is hash-routed and a deep link has to reach the one HTML file.

### What is in `web/.env.production`, and what is deliberately not

`VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` are set, and that is what
makes sign-in work. Both are public: every `VITE_` value is compiled into the
bundle, so nothing secret can live there. The publishable key (once called
`anon`) has no privileges of its own, and the reviewer tables have row-level
security enabled with no policy at all, so the key cannot read them even in
principle.

`VITE_API_BASE_URL` is **not** set, and unset does not mean empty:

| Value | What the screens talk to |
|---|---|
| unset | the deployed API at `https://mazimeal-api.onrender.com` |
| a URL | that API — this is what `web/.env.local` is for in development |
| `""` | nothing; the bundled fixtures, with an **Offline sample** badge |

### The project name is part of the CORS rule

The production URL is <https://mazimealcmu123.vercel.app>, and the API admits
it through `MAZI_CORS_ORIGIN_REGEX`, which is
`^https://mazimeal[a-z0-9-]*\.vercel\.app$` — any host whose name *starts
with* `mazimeal`. That is deliberately loose because Vercel names every preview
`<project>-<hash>-<account>.vercel.app`, so a fixed list cannot cover them and
each new branch would be blocked by the browser with nothing in the server log
to find. It would also admit a different Vercel project named `mazimeal*`,
which is acceptable while every endpoint is public *read*: CORS decides which
pages may read the API, not who may write to it, and writes are gated on a
verified token.

A project renamed to something not starting with `mazimeal` is refused, so the
regex and the project name have to change together.

---

## The API, on Render

The backend needs a container host rather than Vercel's serverless functions:
the recommender is expected to use an OR solver, and those packages are larger
than a function bundle allows. Render's free plan fits, with the caveat that it
sleeps when idle and the first request after that takes about 30 seconds.

`render.yaml` is a blueprint, so Render applies every variable in it on each
sync. Only the two marked `sync: false` are typed into the dashboard, because
they carry the database password.

| Variable | Set in | What it does |
|---|---|---|
| `SUPABASE_DB_URL` | dashboard | the Postgres connection string. Everything live reads it |
| `MAZIMEAL_DSN` | dashboard | the same string under the name the rules engine reads |
| `SUPABASE_URL` | `render.yaml`, optional | the project root. The API fetches `/auth/v1/.well-known/jwks.json` from it to verify a caller's token. Not sensitive — the browser bundle already carries it. Leave it out and the project is read from `SUPABASE_DB_URL` instead, which has to name the same project anyway |
| `MAZI_ADMIN_EMAILS` | `render.yaml`, optional | comma-separated, a backstop reviewer list. Reviewers normally live in the `app_admins` table, which the admin screen edits; this one cannot be changed through the API, so it is the way back in if that table is emptied |

`MAZI_ADMIN_EMAILS` lives in the environment rather than in a table on purpose.
A table the admin screen can edit is a table that whoever reaches the admin
screen can add themselves to.

No JWT secret is needed. The project signs tokens with ES256 and publishes the
matching public keys, so the API verifies them locally with nothing shared.

Two things that cost half a day each to find:

- **A blueprint change does not reach a running service on its own.** Render
  applies a new variable in `render.yaml` on the next **blueprint sync**, not on
  the code deploy a push triggers. After a push that adds one, the dashboard
  shows the blueprint as changed and waits.
- **Connect through Supabase's pooler host, not `db.*.supabase.co`.** The
  direct host is IPv6-only and unreachable from many networks, including
  Render's; it fails as "No route to host". The connection string in use is the
  session pooler, `aws-1-us-west-2.pooler.supabase.com:5432`, and the username
  on it is `postgres.<project-ref>`, not `postgres`.

Nothing in the optional half of that table has to be applied for the
deployment to work: the auth project is derived from `SUPABASE_DB_URL`, and
reviewers come from `app_admins`, whose first row is written by
`schema/migrations/004_app_admins.sql`.

---

## What does not go live, and why

- **The assistant's question box** is disabled. Answering a free question needs
  a model at request time, and we are not hosting one. The box says so.
- **Regenerate** is hidden for the same reason.
- **Reviewing** needs a signed-in reviewer, and decisions go to
  `recipe_content_versions` through the API with the reviewer taken from the
  verified token — so two people reviewing see the same thing and a cook sees
  the correction. Nutrition verdicts work the same way, in
  `recipe_nutrition_reviews`. Neither is in the browser.

---

## Branches

`main` is the deployed branch for both Vercel and Render. It was not always:
the screens were built on `front-backend` while `main` held the rules engine
alone, which is why Vercel could not build from it. `front-backend` was
fast-forwarded into `main`, so the two were identical at that point and there
is one branch to reason about.
