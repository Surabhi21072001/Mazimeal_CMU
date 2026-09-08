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

What lands where:

| dataset | table |
|---|---|
| Name, Description, RecipeCategory, PrepTime, CookTime, RecipeServings | `recipes` |
| RecipeIngredientParts + Quantities | `ingredients`, `recipe_ingredients` |
| RecipeInstructions | `recipe_steps` |
| Calories, Protein, Fat, Carbs, Fiber, Sugar, Sodium, Cholesterol, Sat. fat | `recipe_nutrition` |
| everything, untouched | `foodcom_recipes_raw` (optional: add `--raw-csv raw.csv`, the script prints the `\copy` command) |

Two things the dataset doesn't give us: ingredient **units** (quantities are
bare numbers, so `recipe_ingredients.unit` is `unit`), and a clean meal type.
Meal type comes from RecipeCategory first, then Keywords; "Lunch/Snacks"
recipes under 250 kcal a serving count as Snack. Worth spot-checking.

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
