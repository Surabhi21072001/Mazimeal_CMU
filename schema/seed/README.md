# Recipe seed data

## The 400 recipes come from Food.com

Per Vidya, recipes come from a public dataset rather than being written by us.
We're using the Food.com recipes dataset (about 500K recipes, with ingredients,
steps and per-serving nutrition). Two ways to get the file:

**Kaggle** (needs a free account): [Food.com Recipes and Reviews](https://www.kaggle.com/datasets/irkaal/foodcom-recipes-and-reviews),
download and unzip, you want `recipes.csv` (or `recipes.parquet`).

**HuggingFace** (no account):

```bash
pip install datasets pyarrow
python3 -c "from datasets import load_dataset; load_dataset('AkashPS11/recipes_data_food.com', split='train').to_parquet('recipes.parquet')"
```

Then, from the repo root:

```bash
python3 scripts/import_foodcom.py recipes.parquet --dry-run     # see what it would pick
python3 scripts/import_foodcom.py recipes.parquet -o schema/seed/foodcom_400.sql
psql -d mazimeal -v ON_ERROR_STOP=1 -f schema/seed/foodcom_400.sql
psql -d mazimeal -c "select * from validate_week1();"
```

It picks the best-reviewed recipes for each bucket (Breakfast 80, Lunch 80,
Dinner 100, Snack 60), then adds 80 special-diet recipes on top, 400 in all.
Desserts, drinks, sauces, plain bread loaves and non-food categories are
skipped. Adjust with `--targets`, `--special`, `--min-reviews`,
`--include-desserts`.

`foodcom_400.sql` in this folder is the output of that run, so you can load it
without downloading the dataset.

## Ingredient nutrition from USDA

Food.com only gives calories and macros per recipe. For iron, calcium,
vitamins and the rest, each ingredient is matched to USDA FoodData Central
(SR Legacy) and its per-100 g values go into `ingredient_nutrition`.

Get the data: [FoodData Central downloads](https://fdc.nal.usda.gov/download-datasets),
"SR Legacy" CSV, unzip. Then:

```bash
python3 scripts/ingredient_names.py > /tmp/names.txt
python3 scripts/match_usda.py <unzipped folder> --names /tmp/names.txt --dry-run   # see the weak matches
python3 scripts/match_usda.py <unzipped folder> --names /tmp/names.txt \
    --review schema/seed/usda_matches.csv -o schema/seed/usda_nutrition.sql
psql -d mazimeal -v ON_ERROR_STOP=1 -f schema/seed/usda_nutrition.sql
```

`usda_matches.csv` lists every ingredient with the USDA entry it was matched
to and a score. Worth a scan; the matching is fuzzy plus a list of aliases for
recipe wording ("green onions" is "Onions, spring or scallions" in USDA). When
a match is wrong, add an alias to `ALIASES` in `scripts/match_usda.py` and
rerun. Anything under the score cutoff is left out of the SQL.

`usda_nutrition.sql` is the output for the current 400 recipes, so again you
can load it without the download. Loads into both the week-1 schema and the
recommender's.

What lands where:

| dataset | table |
|---|---|
| Name, Description, RecipeCategory, PrepTime, CookTime, RecipeServings | `recipes` |
| RecipeIngredientParts + Quantities | `ingredients`, `recipe_ingredients` |
| RecipeInstructions | `recipe_steps` |
| Calories, Protein, Fat, Carbs, Fiber, Sugar, Sodium, Cholesterol, Sat. fat | `recipe_nutrition` |
| everything, untouched | `foodcom_recipes_raw` (optional: add `--raw-csv raw.csv`, the script prints the `\copy` command) |
| ingredient names, matched to USDA | `ingredient_nutrition` (second step, below) |

Two things the dataset doesn't give us: ingredient **units** (quantities are
bare numbers, so `recipe_ingredients.unit` is `unit`), and a clean meal type.
Meal type comes from RecipeCategory first, then Keywords; "Lunch/Snacks"
recipes under 250 kcal a serving count as Snack. Worth spot-checking.

The quantities are also not reliably attached to the right ingredient. In
most recipes the dataset's quantity list is longer than its ingredient list
(it dropped some ingredient names but kept their numbers), so the number
next to an ingredient may belong to another one. Only 114 of the 400 line
up. `recipe_ingredients.quantity_aligned` says which.

## Grams per ingredient line

Nutrition is calculated as grams x per-100 g values, so every line needs
grams. With no units in the dataset, this is an estimate: each ingredient
gets a default household measure (flour: cup, olive oil: tbsp, egg: each,
garlic: clove, ground beef: lb) and the weight of that measure comes from
USDA `food_portion` for the matched food, or a fallback constant when USDA
has none. Every USDA measure is also stored in `ingredient_measures`, so a
line can later be switched to "2 tbsp" and recalculated.

```bash
python3 scripts/ingredient_grams.py <unzipped SR Legacy folder> --parquet recipes.parquet \
    --review schema/seed/ingredient_measures.csv -o schema/seed/ingredient_grams.sql
psql -d mazimeal -v ON_ERROR_STOP=1 -f schema/seed/ingredient_grams.sql
```

`ingredient_measures.csv` shows the measure chosen per ingredient, the grams
and whether USDA or a fallback supplied them. When one is wrong, add it to
`OVERRIDES` in the script and rerun. `--parquet` is optional; it fills
`quantity_aligned` for databases loaded before the importer wrote it.

## Where each value came from

`data_sources` has one row per upstream database (USDA SR Legacy now; the
Canadian, Australian and Finnish ones later) with its licence and the
attribution text to show. Every row in `ingredient_nutrition` and
`ingredient_measures` carries a `source_id`, and `ingredient_source_map`
records which USDA record each ingredient was matched to, with the match
score. When a second database is added, its values sit beside USDA's under
their own `source_id`; `v_ingredient_nutrition` picks one value per
nutrient by `data_sources.precedence`, and everything that calculates
nutrition reads that view.

```bash
python3 scripts/ingredient_sources.py --review schema/seed/usda_matches.csv -o schema/seed/ingredient_sources.sql
psql -d mazimeal -v ON_ERROR_STOP=1 -f schema/seed/ingredient_sources.sql
```

Each line records how its grams were arrived at (`grams_source`): `measure`
for number x measure weight, `assumed` when the source had no number and one
measure was assumed, `manual` when someone entered grams, `none` when
unknown. Unknown stays NULL.

The dataset is scraped from Food.com. Fine for development; check the terms
before anything ships to real users.

## Hand-written batches (if we ever need them)

Recipes go in as CSV, get validated, and come out as SQL you load with psql.

```bash
python3 scripts/csv_to_sql.py schema/seed/recipes.csv schema/seed/recipe_ingredients.csv -o schema/seed/batch1.sql
psql -d mazimeal -v ON_ERROR_STOP=1 -f schema/seed/batch1.sql
psql -d mazimeal -c "select * from validate_week1();"
```

If the CSV has a problem the script says what and where and writes nothing.
The SQL it produces is safe to run more than once.

## recipes.csv

| column | required | notes |
|---|---|---|
| recipe_name | yes | must be unique, case doesn't matter |
| meal_category | yes | Breakfast, Lunch, Dinner or Snack |
| dietary_tags | | pipe separated: `vegan\|gluten_free` |
| prep_time_min | | whole minutes |
| cook_time_min | | whole minutes |
| difficulty_level | | Easy, Medium or Hard |
| servings | | defaults to 4 |
| calories_per_serving | | |
| regional_origin | | Mediterranean, Asian, etc |
| description | | |
| steps | | pipe separated. Goes into the description for now since there's no steps table yet |

## recipe_ingredients.csv

One row per ingredient per recipe.

| column | required | notes |
|---|---|---|
| recipe_name | yes | must match a row in recipes.csv |
| ingredient_name | yes | reused across recipes by name, case doesn't matter |
| quantity | yes | number greater than 0 |
| unit | yes | g, ml, tsp, tbsp, cup, whole, cloves, etc |
| preparation_note | | chopped, minced, rested 10 min |
| is_optional | | true or false, defaults to false |
| food_category | | used only when the ingredient is new. Defaults to Uncategorized |

Ingredients are created the first time they're seen and reused after that, so
spell them the same way across batches. "Tomato" and "tomatoes" become two
different ingredients.

## What's already here

`recipes.csv` and `recipe_ingredients.csv` hold the 25 recipes pulled from the
frontend by `scripts/salvage_frontend_recipes.py`. Only one of them had real
quantities; the other 116 ingredient lines are marked `unit=portion` and need
quantities filled in by hand. They're a starting point, not finished data.
