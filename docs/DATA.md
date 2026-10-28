# Working with the database

For whoever is changing recipe, ingredient or rule data. It covers the live
database, how to change it without breaking the screens, and where the
highest-value work currently is.

[schema/seed/README.md](../schema/seed/README.md) explains where the data came
from and how to regenerate it. This file is about changing what is already
loaded.

---

## What is running

| | Where | State |
|---|---|---|
| Database | Supabase, project `vvoxzwktnalrodukachl`, region us-west-2 | 400 recipes, loaded and validated |
| Backend | `https://mazimeal-api.onrender.com` | Reads the database live |
| Rules engine | Same service, under `/rules` | The endpoints in the Postman collection |
| Front end | Vercel | Not deployed yet, waiting on repo access |

The backend reads the database on every request. **A change you make is live
within seconds** — there is no deploy step and no cache in front of the recipe
data. That is convenient and it is also the reason for the "after every change"
section below.

Two things worth checking when you want to know if the backend is healthy:

```bash
curl https://mazimeal-api.onrender.com/api/health
# {"status":"ok","repo":"supabase","provider":"template","rules_engine":"/rules","model":null}

curl https://mazimeal-api.onrender.com/api/recipes/falafel-001
```

`repo: supabase` means it is reading the real database. If it says `fixture`,
the connection string is wrong and the screens are showing committed sample
data instead.

The service is on a free plan, so it sleeps after about 15 minutes of no
traffic and the first request after that takes 30-60 seconds. It is not broken.

---

## Getting access

Ask An-Chien to add you to the Supabase project (Dashboard → Project Settings →
Team). You then have the dashboard, which is enough for most work, plus a
connection string under Project Settings → Database.

**Do not put the connection string in git.** It contains the database password
and it grants full write access, including dropping tables. Keep it in a local
`.env`, which this repo already ignores.

---

## Connecting

Through the dashboard: **SQL Editor** runs anything, **Table Editor** is a
spreadsheet view for one-off edits.

From a terminal, use the **pooler** host, not `db.<ref>.supabase.co`:

```bash
psql "postgresql://postgres.vvoxzwktnalrodukachl:<password>@aws-1-us-west-2.pooler.supabase.com:5432/postgres?sslmode=require"
```

Three details that each cost an hour if you get them wrong:

- The direct `db.*.supabase.co` host is **IPv6 only** and unreachable from many
  networks, including campus wifi. It fails as "No route to host". Use the
  pooler.
- The username is `postgres.<project-ref>`, not `postgres`.
- If your password contains `@`, percent-encode it as `%40`, or everything
  after it is parsed as the hostname.

Port 5432 is the session pooler and is what the backend uses. Port 6543 is the
transaction pooler; it does not support prepared statements, which breaks
psycopg, so stay on 5432 unless you know you need otherwise.

---

## What the app actually reads

Changing a table in the left column changes what appears on screen. The rest
of the schema is upstream data that nothing serves yet.

| Table | Read by | Shows up as |
|---|---|---|
| `recipes` | both | name, meal, servings, prep + cook time, dietary tags |
| `recipe_ingredients` | both | the ingredient list; `quantity_g` also drives derived nutrition |
| `ingredients` | both | ingredient names |
| `recipe_steps` | ours | the numbered method |
| `recipe_nutrition` | ours | per-serving figures labelled `published` |
| `v_ingredient_nutrition` | ours | per-serving figures labelled `derived`, for nutrients Food.com does not publish |
| `business_rules` | both | the rule cards: name, mechanism, evidence tier, source link |
| `rule_codes` | both | the code vocabulary rules and ingredients are matched on |
| `ingredient_rule_tags` | both | **which rules fire on which recipe** |

"ours" is [api/app/supabase_repo.py](../api/app/supabase_repo.py), "both" means
the rules engine reads it too.

Read `v_ingredient_nutrition`, never `ingredient_nutrition` underneath it. The
view picks one value per nutrient by `data_sources.precedence`. The moment a
second source sits beside USDA, the raw table has two rows per nutrient and
anything summing it counts the ingredient twice.

`ingredient_rule_tags` is the highest-leverage table in the database. It is two
columns, and it decides whether a recipe shows four rule cards or none.

---

## Changing data

Three routes. The difference between them is what survives a rebuild.

### 1. Table Editor, for a handful of rows

Fine for fixing one recipe's servings or a misspelt ingredient. Fast, no SQL,
and **not recorded anywhere** — if the database is ever rebuilt from the seed
files, your edit is gone.

### 2. SQL Editor, for anything repeatable

Write the statement, run it, and **paste it into a file under
`schema/seed/`** so it is part of the repo. Anything you would be annoyed to
redo belongs here.

Write statements that can run twice without doing damage:

```sql
INSERT INTO ingredient_rule_tags (ingredient_id, rule_code)
SELECT ingredient_id, 'ING_LEGUME'
FROM ingredients
WHERE ingredient_name ~* '(chickpea|garbanzo|lentil|black bean|kidney bean)'
ON CONFLICT DO NOTHING;
```

The primary key is `(ingredient_id, rule_code)`, so `ON CONFLICT DO NOTHING`
makes that safe to rerun.

### 3. Regenerate a seed file, for derived data

Anything a script produced — USDA matches, gram weights, the Food.com import —
is changed by **editing the script and rerunning it**, not by patching rows.
The scripts have override tables for exactly this: `ALIASES` in
[scripts/match_usda.py](../scripts/match_usda.py) for a wrong USDA match,
`OVERRIDES` in [scripts/ingredient_grams.py](../scripts/ingredient_grams.py)
for a wrong household measure. See
[schema/seed/README.md](../schema/seed/README.md) for each command.

Patch a row by hand and the next regeneration overwrites it, with no warning.

---

## After every change

```sql
SELECT * FROM validate_week1();
```

Defined in [schema/99_validate.sql](../schema/99_validate.sql), safe to run any
time. It reports PASS / FAIL / WARN / PENDING / SKIP per check and catches the
things that are easy to do by accident: duplicate recipe names, duplicate
ingredients after normalising punctuation, recipes with no ingredient lines,
ingredient lines pointing at a recipe that no longer exists, missing servings.

Treat any FAIL as yours to fix before you move on.

Then check a recipe through the API, because `validate_week1()` does not know
what the screens need:

```bash
curl -s https://mazimeal-api.onrender.com/api/recipes/falafel-001 | python3 -m json.tool | head -40
```

---

## Loading in bulk: use COPY

The initial load ran the seed files as line-by-line `INSERT` over the network.
Measured: `usda_nutrition.sql` took **30 minutes**, `foodcom_400.sql` **10
minutes**. The statements are fine; the round trips are what cost.

For anything large, stream it instead:

```bash
psql "$SUPABASE_DB_URL" -c "\copy ingredient_rule_tags (ingredient_id, rule_code) FROM 'tags.csv' WITH (FORMAT csv, HEADER)"
```

Same work, one to two orders of magnitude faster. Worth it the moment you are
loading more than a few hundred rows.

---

## Where the work is, highest value first

### 1. Twelve rules can never fire

A rule matches a recipe when some ingredient in it carries the rule's
`trigger_code`. These twelve have a trigger code that **no ingredient in the
database carries**, so they are dead weight — the rule exists, is written up,
cites evidence, and can never appear on a screen:

| Rule | Needs the code | |
|---|---|---|
| BIO-008 | `ING_LEGUME` | Soak and cook legumes |
| BIO-012 | `ING_LEGUME` | Pressure-cook or boil legumes fully |
| BIO-009 | `ING_GRAIN_LEGUME` | Germinate grains or legumes |
| BIO-010 | `ING_GRAIN_LEGUME` | Ferment grain or legume matrix |
| GLY-008 | `ING_GRAIN_LEGUME` | Keep grains and legumes structurally intact |
| SYN-007 | `ING_LEGUME_GRAIN` | Complete limiting amino acids across the day |
| SYN-009 | `ING_ALLIUM_GRAIN_LEGUME` | Allium with iron/zinc-rich grains or legumes |
| BIO-014 | `ING_SEED` | Grind seeds before use |
| BIO-015 | `ING_VITC_FOLATE_VEG` | Avoid prolonged boiling of water-soluble vitamins |
| GLY-006 | `ING_COOKED_STARCH` | Cool cooked starch to form resistant starch |
| GLY-013 | `ING_RIPE_FRUIT` | Choose less-ripe fruit when acceptable |
| INH-005 | `ING_RAW_EGG_WHITE` | Raw egg white with biotin |

The ingredients are already in the database, just untagged. Rough counts by
name matching:

- legumes (bean, chickpea, garbanzo, lentil, pea, soy, tofu): **26 ingredients
  across 64 recipes**
- grains (rice, oat, quinoa, barley, wheat, bulgur, millet): **22 ingredients
  across 34 recipes**
- seeds (seed, sesame, flax, chia, sunflower): **14 ingredients across 17
  recipes**

Tagging legumes alone would bring four rules to life across 64 recipes. That is
the single biggest improvement available to the product right now, and it is
data entry, not engineering.

### 2. Only 73 of 559 ingredients are tagged at all

75 tag rows, 73 distinct ingredients, 11 codes in use:

```
ING_TOMATO 17   ING_CRUCIFER 11   ING_PASTA 11   ING_LEAFY_GREEN 8
ING_CORN 6      ING_GARLIC 6      ING_YOGURT 5   ING_MUSHROOM 4
ING_EGG 3       ING_CARROT 2      ING_TURMERIC 2
```

130 of the 400 recipes contain no tagged ingredient whatsoever, so they show no
rules at all. The untagged ingredients appearing in the most recipes:

| Ingredient | Recipes | Rule-relevant? |
|---|---|---|
| salt | 201 | no |
| butter | 110 | yes — fat, for fat-soluble vitamin absorption |
| sugar | 82 | no |
| onion | 69 | yes — allium |
| olive oil | 66 | yes — fat |
| flour | 63 | no |
| milk | 61 | yes — calcium, which inhibits iron |
| baking powder | 59 | no |
| water | 58 | no |
| pepper | 55 | yes if it means black pepper — piperine |
| garlic powder | 45 | yes — allium |
| parmesan cheese | 37 | yes — calcium |
| black pepper | 31 | yes — piperine, pairs with turmeric |
| sour cream | 28 | yes — calcium |
| cheddar cheese | 26 | yes — calcium |

The "no" rows are worth noting as deliberately skipped, so nobody re-reviews
them later.

### 3. The code vocabulary is unconfirmed

All **121 of 121** rows in `rule_codes` still have `needs_review = true`, and
their descriptions read "auto-derived; confirm meaning". The codes were
generated from the rules workbook, not written by a person. Until someone
confirms them, every tag is being attached to a label whose meaning is assumed.

`AVOID_OXALATE_CALCIUM_CREDIT` is a good example of one that needs a human to
say what it actually means.

### 4. Ingredient names split the same food into several rows

A tag applies to one `ingredient_id`, so tagging `oats` does not tag
`old fashioned oats`. Existing splits include:

```
oats / old fashioned oats / Old mill oats
beef / ground beef
rice / cooked brown rice
chicken broth / condensed chicken broth / reduced-sodium chicken broth
grapes / red seedless grapes / green seedless grapes
blueberries / frozen blueberries
```

`validate_week1()` does not catch these — it normalises punctuation and case,
not extra words. Decide per case whether to merge the rows or tag both; prefer
tagging both, since merging breaks the recipe lines that point at them.

### 5. Quantities are attached to the wrong ingredient in most recipes

Only **937 of 3063** ingredient lines have `quantity_aligned = true`. In the
Food.com data the quantity list is often longer than the ingredient list, so a
number may belong to a different ingredient than the one it sits next to.

Gram weights are nearly complete (**3058 of 3063** lines have `quantity_g`),
but where `quantity_aligned` is false the grams rest on a misaligned number,
which means the `derived` nutrition figures for that recipe are soft. They are
labelled `derived` with confidence 0.6 on screen for this reason. Published
figures from Food.com cover all 400 recipes and are unaffected.

---

## How to tag an ingredient

Find it, tag it, confirm it reached a screen.

```sql
-- 1. what is actually in there, and is it tagged already
SELECT i.ingredient_id, i.ingredient_name,
       (SELECT array_agg(rule_code) FROM ingredient_rule_tags t
         WHERE t.ingredient_id = i.ingredient_id) AS tags,
       count(DISTINCT ri.recipe_id) AS recipes
FROM ingredients i LEFT JOIN recipe_ingredients ri USING (ingredient_id)
WHERE i.ingredient_name ~* 'chickpea|garbanzo'
GROUP BY i.ingredient_id, i.ingredient_name;

-- 2. the code must exist in rule_codes first (foreign key)
SELECT code, code_type, display_name FROM rule_codes WHERE code = 'ING_LEGUME';

-- 3. tag
INSERT INTO ingredient_rule_tags (ingredient_id, rule_code)
SELECT ingredient_id, 'ING_LEGUME' FROM ingredients
WHERE ingredient_name ~* 'chickpea|garbanzo|lentil'
ON CONFLICT DO NOTHING;

-- 4. which rules can now fire, and on how many recipes
SELECT br.rule_id, br.rule_name, count(DISTINCT ri.recipe_id) AS recipes
FROM business_rules br
JOIN ingredient_rule_tags t ON t.rule_code = br.trigger_code
JOIN recipe_ingredients ri USING (ingredient_id)
WHERE br.trigger_code = 'ING_LEGUME'
GROUP BY br.rule_id, br.rule_name;
```

Then look at a recipe that should have changed:

```bash
curl -s https://mazimeal-api.onrender.com/api/recipes/falafel-001 \
  | python3 -c "import sys,json; [print(r['rule_id'], r['status'], r['name']) for r in json.load(sys.stdin)['matched_rules']]"
```

A tag makes a rule a *candidate*. The engine then decides whether the recipe
already satisfies it, so a new tag can legitimately show up as `satisfied`
rather than as advice. That is working correctly, not a missing suggestion.

---

## Things that will break the screens

- **Do not change a `recipe_id`.** Everything joins on it, and the front end
  links to five of them by name. Changing one orphans its ingredients, steps
  and nutrition.
- **Do not rename an ingredient to merge two rows.** The tags and nutrition
  belong to the `ingredient_id`, not the name. Repoint `recipe_ingredients`
  first, or just tag both rows.
- **Do not delete a recipe outright.** `recipes.deleted_at` exists for this and
  `validate_week1()` respects it. A hard delete cascades.
- **Do not drop and recreate a table to reload it.** The foreign keys from
  `ingredient_rule_tags`, `recipe_ingredients` and `ingredient_source_map`
  cascade, so you lose work that was never in a seed file.
- **Watch the two `10_` files.** `schema/` has both `10_business_rules.sql` and
  `10_ingredient_sources.sql`. Applying the directory in filename order makes
  their relative order depend on the shell's sort, which is not a property
  anyone should rely on. Worth renaming one.
- **Adding a nutrition source is not a drop-in.** A second `source_id` in
  `ingredient_nutrition` needs a `data_sources` row with a `precedence` before
  `v_ingredient_nutrition` returns one value per nutrient again.

---

## Open questions for the rules team

- `matched_on.ingredients[].line_id` in the evaluate response, so a rule can
  highlight the exact ingredient line on screen rather than the whole meal.
  See [docs/rules_api_contract.md](rules_api_contract.md).
- Whether `NEEDS_CONTEXT` is meant to reach a cook. Right now it renders as
  advisory text.
- Nutrient units: `recipe_nutrition.unit` is trusted as-is. Nobody has
  confirmed it is consistent across all 3600 rows.
