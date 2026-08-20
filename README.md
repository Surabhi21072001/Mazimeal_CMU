# Mazimeal

Personalised nutrition planning: recipes, ingredients, and the clinical rules
that connect them to a household's needs.

---

## What is here

```
web/        React + Vite client (the shared sample-main code)
docs/       Schema workbook, branching strategy, access log
schema/     PostgreSQL DDL — arrives during week 1
```

`docs/Synergia_Unified_DB_Schema.xlsx` is the source of truth for the database.
Where a DDL file differs from it, the file says so in a comment.

---

## Setup

### 1 · Requirements

- Node 20 or newer
- PostgreSQL client (`psql`) 14 or newer
- Access to the shared PostgreSQL instance — see credentials below

### 2 · Clone and install

```bash
git clone https://github.com/<owner>/mazimeal.git
cd mazimeal
git checkout dev          # dev is the default; branch from here
npm install --prefix web
```

### 3 · Get the credentials

**Credentials are in SharePoint. They are never in this repository.**

Ask Swetha for the SharePoint link if you do not have it. You need the Supabase
URL and anon key for the frontend, and the host, port, database, username and
password for the shared PostgreSQL instance.

### 4 · Create your local `.env`

```bash
cp .env.example .env
```

Fill it in from the SharePoint entry. Then confirm it is ignored **before your
first commit**:

```bash
git check-ignore -v .env      # must print a .gitignore line
```

If that prints nothing, stop and fix `.gitignore` before committing anything.

### 5 · Run the client

```bash
npm run dev --prefix web
```

### 6 · Load the schema (once DDL files land in `schema/`)

```bash
createdb mazimeal
for f in schema/[0-9][0-9]_*.sql; do
  psql -d mazimeal -v ON_ERROR_STOP=1 -f "$f"
done
psql -d mazimeal -f schema/99_validate.sql
```

`ON_ERROR_STOP=1` matters — without it psql continues after a failure and you
end up with half a schema and no error on screen.

The file numbers are the load order and they matter: `recipe_ingredients` has
foreign keys into `recipes` and `ingredients`, so it cannot load first.

### 7 · Connect to the shared instance

```bash
psql "postgresql://$PGUSER:$PGPASSWORD@$PGHOST:$PGPORT/$PGDATABASE" \
     -c "SELECT current_database(), current_user;"
```

If this fails, post the exact error in the group chat — a firewall or SSL-mode
problem on one machine is usually the same on all three, and documenting
connection issues is its own task.

---

## Credential storage

1. **Never in git.** Not in a SQL file, not in a comment, not in a commit
   message, not temporarily.
2. **SharePoint is the store** for shared credentials, as agreed.
3. **Your working copy lives in `.env`**, which is gitignored. CI rejects any
   commit that adds one.
4. **If a credential is ever committed**, say so in the group chat immediately.
   Rotating a key the same day is routine; finding it in month-old history after
   everyone has cloned is not.

Note on the Supabase keys specifically: `VITE_`-prefixed variables are compiled
into the browser bundle and are public by design. The anon key is not a secret —
row level security is what protects the data. That makes the database policies
worth reviewing before real user data goes in.

A note for later, not this week: a single shared database login makes an audit
log useless, because every change looks like it came from the same person. When
the database holds anything real, each developer should get their own role. For
a dev database of test recipes, shared is fine.

---

## Branching

`main` is the last known-good state. `dev` is where everything integrates.
Branch from `dev`, open a pull request into `dev`, one reviewer approves.
Nobody pushes to `main` or `dev` directly.

Full detail, including naming and the per-file ownership rules, in
`docs/BRANCHING.md`.

---

## Notes on the imported code

`web/` is the shared `sample-main` folder. Two things were left out:

- **`.env`** — it contained live Supabase credentials and the original
  `.gitignore` did not exclude it. The key should be rotated, since the file has
  been sitting in a shared drive.
- **`VeriSnap ios app/`** — a Flutter scaffold from an unrelated project, with a
  hardcoded path `/Users/navi/my-react-app` and nothing referencing it.
  Confirmed with the team as out of scope for Mazimeal.

One more, for whoever picks up the frontend: `package.json` pins
`vite: ^8.0.0-beta.13` through `overrides`. The web build in CI is advisory
until that moves to a stable release.

---

## Working agreements

- Branch from `dev`, PR into `dev`. See `docs/BRANCHING.md`.
- One owner per schema file. Do not edit a file you do not own — ask.
- Run `schema/99_validate.sql` after every insert batch, not only at the end.
- Read the CI result before approving. On our plan it cannot block a merge, so
  it only helps if someone looks at it.
