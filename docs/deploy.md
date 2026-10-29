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
- **Reviewer decisions are per browser.** They move to a database when there
  is one; until then two people reviewing see different things.

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
4. Leave Environment Variables empty. The screens default to the deployed
   backend at `https://mazimeal-api.onrender.com`, so there is nothing to set.

   `VITE_API_BASE_URL` overrides that default when it is needed — a local URL
   while developing, or an empty string to force the bundled fixtures and run
   with no backend at all. Unset and empty mean different things here, on
   purpose.

   The other five `VITE_` variables the repository reads
   (`VITE_SUPABASE_*`, `VITE_EMAILJS_*`) belong to the original app's login and
   signup email, and are deliberately left unset: this Supabase project holds
   recipes and rules, not the recommender schema those features expect, so
   pointing them at it would break more confusingly than leaving them off.
   Those features disable themselves when the variables are missing.
5. Deploy. The first build takes about a minute.

The production URL serves the original app; the screens are at `/#/recommend`
and `/#/cook/falafel-001`.

### After that

Every push to `front-backend` gets its own preview URL, and whichever branch
is set as Production gets the main one. Pick the Production branch
deliberately in **Settings → Git**: `main` currently holds the rules engine
without any of these screens.

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
