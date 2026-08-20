# Branching

## Branches

- `main` — what we demo. Only updated by merging `dev`.
- `dev` — where work comes together. Only updated by merging feature branches.
- `feature/*` — your work in progress.

Don't push straight to `main` or `dev`. Open a PR.

We have `dev` so that a broken DDL file gets caught before Friday instead of on Friday.

## Branch names

`feature/<area>-<what-it-does>`, lowercase, hyphens:

```
feature/schema-recipes-ddl
feature/data-breakfast-lunch-batch1
fix/recipes-check-constraint
docs/readme-setup-steps
```

Don't name branches after yourself.

## Workflow

```bash
git checkout dev
git pull origin dev
git checkout -b feature/schema-recipes-ddl

# work

git add schema/01_recipes.sql
git commit -m "Add recipes DDL with meal_category column"
git push -u origin feature/schema-recipes-ddl
```

Open the PR against `dev`. One person reviews, then squash-merge and delete the
branch.

At the end of the week we merge `dev` into `main`.

## Rebase before opening a PR

```bash
git checkout dev && git pull origin dev
git checkout feature/my-branch
git rebase dev
```

## Who owns which file

One owner per schema file so we're never editing the same one:

| File | Owner |
|---|---|
| `schema/01_recipes.sql` | Zihan |
| `schema/02_ingredients.sql` | Swetha |
| `schema/03_recipe_ingredients.sql` | Kate |
| `schema/04_nutrition_rules.sql` | Zihan |
| `schema/99_validate.sql` | shared |

The numbers are the load order. `03_recipe_ingredients.sql` has foreign keys
into `recipes` and `ingredients`, so those have to exist first.

Need something changed in a file you don't own? Ask the owner.

## Commit messages

Say what changed:

```
Add recipes DDL with meal_category column
```

Not `update`, `fix`, or `changes`.

## Don't commit

- `.env`, passwords, API keys, connection strings
- `node_modules/`, `__pycache__/`, `dist/`
- `.DS_Store`

Database credentials are in SharePoint. If something does get committed by
accident, post in the group chat right away so we can rotate it.

## Confirming your access

Run this once when you get the invite:

```bash
git clone https://github.com/mazimeal/platform.git
cd platform
git checkout dev
git checkout -b test/<yourname>-access
echo "| <yourname> | $(date +%Y-%m-%d) |" >> docs/ACCESS_CHECK.md
git add docs/ACCESS_CHECK.md
git commit -m "Confirm repo access for <yourname>"
git push -u origin test/<yourname>-access
```

If the push works, you have write access. Open a PR into `dev` and merge it so
we've tested the review flow too.

Clone somewhere outside OneDrive or Dropbox. Sync clients and git both try to
manage the folder and you end up with duplicate files inside `.git/`.

## Branch protection

GitHub Free doesn't support protected branches on private repos, so none of the
above is enforced automatically — `main` and `dev` are open. CI runs on every PR
but can't block a merge, so check it before approving.
