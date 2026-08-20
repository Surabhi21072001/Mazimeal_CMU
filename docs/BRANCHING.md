# Branching strategy

Task 2. Three developers, one repo, one week. Deliberately small — a strategy
nobody follows is worse than no strategy.

---

## Branches

| Branch | What it is | Who writes to it |
|---|---|---|
| `main` | Last known-good state. Demoed on Friday. | Nobody directly — only merges from `dev` |
| `dev` | Integration branch. Everything meets here first. | Only merges from `feature/*` |
| `feature/*` | Your work in progress. | You |

Nobody pushes to `main` or `dev` directly. Everything arrives through a pull
request, including small changes.

### Why `dev` exists at all

We are writing four DDL files in parallel and inserting 400 recipes in three
batches. If everything lands straight on `main`, the first broken DDL breaks
everyone's local database and the Friday demo is whatever happened to be merged
last. `dev` gives us somewhere to find that out on Thursday instead.

---

## Naming

```
feature/<area>-<short-description>
```

| Example | For |
|---|---|
| `feature/schema-recipes-ddl` | Task 11 |
| `feature/schema-nutrition-rules-ddl` | Task 11 |
| `feature/data-breakfast-lunch-batch1` | Task 17 |
| `fix/recipes-check-constraint` | A fix to something already merged |
| `docs/readme-setup-steps` | Task 3 |

Lowercase, hyphens, no personal names. `feature/schema-recipes-ddl` tells the
next person what it contains; `zihan-work` does not.

---

## The flow

```bash
# start from the latest dev
git checkout dev
git pull origin dev
git checkout -b feature/schema-recipes-ddl

# ... work ...
git add schema/01_recipes.sql
git commit -m "Add recipes table DDL with meal_category and duplicate guard"
git push -u origin feature/schema-recipes-ddl
```

Then open a PR into `dev`, not `main`. One reviewer approves (task 15), then
squash-merge and delete the branch.

At the end of the week, after the demo passes on `dev`, one PR merges `dev` into
`main` (task 16).

---

## Rebase before you open the PR

```bash
git checkout dev && git pull origin dev
git checkout feature/my-branch
git rebase dev
```

Resolving conflicts on your own branch is your problem. Resolving them inside a
merge on `dev` is everyone's problem.

---

## Schema files: one owner each

The four DDL files are separate on purpose. Nobody edits a file they do not own,
so three people can write DDL simultaneously without a single conflict.

| File | Owner | Load order |
|---|---|---|
| `schema/01_recipes.sql` | Zihan | 1 |
| `schema/02_ingredients.sql` | Swetha | 2 |
| `schema/03_recipe_ingredients.sql` | Kate | 3 |
| `schema/04_nutrition_rules.sql` | Zihan | 4 |
| `schema/99_validate.sql` | shared | last |

The numbers are the load order, and it matters: `recipe_ingredients` has foreign
keys into `recipes` and `ingredients`, so it cannot load first.

If you need a change in someone else's file, ask them — don't edit it. Two people
editing one DDL file is how a table ends up with two definitions of the same
column.

---

## Commits

Present tense, says what changed and why if the why is not obvious.

```
Add recipes table DDL with meal_category and duplicate guard

meal_category is not in the workbook — sheet 07 has no meal slot on the
recipe itself. Without it the batch plan has nowhere to record that a
recipe is breakfast.
```

Not `update`, `fix`, `changes`, or `asdf`.

---

## Never commit

- `.env` or any file with credentials
- Database passwords, connection strings with passwords, API keys
- `node_modules/`, `__pycache__/`, `dist/`
- `.DS_Store`

Database credentials live in SharePoint (task 7). If you find yourself pasting a
password into a file inside the repo, stop — that is what SharePoint and your
local `.env` are for.

If a credential does get committed, say so immediately in the group chat. It is
a five-minute fix on the day and a genuinely bad one a month later, after
everyone has cloned the history.

---

## Confirming access (task 4)

Each developer runs this once, on the day they get the invite:

```bash
git clone https://github.com/<org>/<repo>.git
cd <repo>
git checkout dev
git checkout -b test/<yourname>-access
echo "<yourname> - access confirmed $(date)" >> docs/ACCESS_CHECK.md
git add docs/ACCESS_CHECK.md
git commit -m "Confirm repo access for <yourname>"
git push -u origin test/<yourname>-access
```

Push succeeds → write access works. Open a PR into `dev` so the review flow gets
tested too, then merge it and delete the branch. Three lines in
`docs/ACCESS_CHECK.md` is the evidence that task 4 is done.

---

## One note on branch protection

Protected branches are not available on private repositories under GitHub Free —
they need Pro, Team or Enterprise. Until the org is on a paid plan, none of the
above is enforced by GitHub. It is enforced by us remembering.

CI still runs on every pull request and its result is visible; it just cannot
block a merge. So: read the CI result before approving.
