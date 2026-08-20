# Mazimeal

Nutrition planning: recipes, ingredients, and the rules that match them to a
household's needs.

## Layout

```
web/        React + Vite client
docs/       Schema workbook, branching guide, access log
schema/     PostgreSQL DDL
```

`docs/Synergia_Unified_DB_Schema.xlsx` is the source of truth for the database.
Where a DDL file differs from it, there's a comment in the file saying why.

## Setup

You'll need Node 20+ and `psql` 14+.

### Clone

```bash
git clone https://github.com/mazimeal/platform.git
cd platform
git checkout dev
npm install --prefix web
```

Clone somewhere outside OneDrive or Dropbox. Sync clients and git both try to
manage the folder and you end up with duplicate files inside `.git/`.

### Credentials

Credentials live in SharePoint, not in this repo.

You'll need the Supabase URL and anon key for the frontend, and the host, port,
database, username and password for the shared PostgreSQL instance.

```bash
cp .env.example .env
```

Fill it in, then check it's ignored before you commit anything:

```bash
git check-ignore -v .env      # should print a .gitignore line
```

If that prints nothing, fix `.gitignore` first.

### Run the client

```bash
npm run dev --prefix web
```

### Load the schema

```bash
createdb mazimeal
for f in schema/[0-9][0-9]_*.sql; do
  psql -d mazimeal -v ON_ERROR_STOP=1 -f "$f"
done
psql -d mazimeal -f schema/99_validate.sql
```

Keep `ON_ERROR_STOP=1`. Without it psql carries on after a failure and you get
half a schema with no obvious error.

The file numbers are the load order. `03_recipe_ingredients.sql` has foreign
keys into `recipes` and `ingredients`, so those have to exist first.

### Connect to the shared database

```bash
psql "postgresql://$PGUSER:$PGPASSWORD@$PGHOST:$PGPORT/$PGDATABASE" \
     -c "SELECT current_database(), current_user;"
```

If it fails, post the error in the group chat. A firewall or SSL-mode problem on
one machine is usually the same on all three.

## Credentials

Nothing with a password goes in the repo: not in a SQL file, not in a comment,
not temporarily. Shared credentials live in SharePoint, your working copy lives
in `.env`, and CI rejects any commit that adds one.

If something does get committed, say so in the group chat so we can rotate it.

Two notes:

The Supabase `VITE_` variables are compiled into the browser bundle, so the anon
key is public by design. Row level security is what actually protects the data,
which makes those policies worth reviewing before real user data goes in.

We're using one shared database login for now, which is fine for test recipes.
Once there's real data in there, everyone should have their own role so the
audit trail means something.

## Branching

`main` is what we demo, `dev` is where work comes together. Branch from `dev`,
PR into `dev`, one person reviews. Details in `docs/BRANCHING.md`.

## About the imported code

`web/` is the `sample-main` folder we were given. Two things aren't in it:

`.env` had live Supabase credentials and the original `.gitignore` didn't
exclude it. That key should be rotated since the file sat in a shared drive.

`VeriSnap ios app/` is a Flutter scaffold from a different project, with a
hardcoded path to someone's home directory and nothing referencing it.

Also worth knowing: `package.json` pins `vite: ^8.0.0-beta.13` through
`overrides`, so the web build in CI is advisory until that moves to a stable
release.

## Conventions

- Branch from `dev`, PR into `dev`.
- One owner per schema file. Ask before editing someone else's.
- Run `schema/99_validate.sql` after each insert batch, not just at the end.
- Check CI before approving a PR. It can't block a merge on our plan.
