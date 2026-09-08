# Branching

## Branches

- `main` is what we demo. Only updated by merging `dev` at the end of the week.
- `dev` is where day to day work goes.
- `feature/*` for anything you want checked before it lands.

Never push to `main` directly.

Pushing straight to `dev` is fine for docs and small changes. For schema files
or anything others depend on, use a branch and a PR so CI runs on it first.

Pull before you push, every time:

```bash
git pull --rebase origin dev
```

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
| `schema/04_nutrient_rules.sql` | Zihan |
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
echo "| <yourname> | $(date +%Y-%m-%d) |" >> docs/ACCESS_CHECK.md
git add docs/ACCESS_CHECK.md
git commit -m "Confirm repo access for <yourname>"
git push origin dev
```

If the push works, you have write access.

Clone somewhere outside OneDrive or Dropbox. Sync clients and git both try to
manage the folder and you end up with duplicate files inside `.git/`.

## Branch protection

GitHub Free doesn't support protected branches on private repos, so none of the
above is enforced automatically. CI runs on every push and PR but can't block a
merge, so check it.
