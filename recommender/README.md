# Recommender

Baseline recipe recommender for Mazimeal. Rule-based, explainable, no ML.
Lives in the database as SQL functions so the frontend can call it directly
through Supabase (`supabase.rpc('fn_recommend', {...})`) with no backend.

## Setup

Needs its own database. It uses the full schema from the design doc (members,
targets, nutrition per ingredient), not the four week-1 tables.

```bash
createdb mazimeal_full
psql -d mazimeal_full -f recommender/db/install.sql
psql -d mazimeal_full -f recommender/seed/00_reference.sql
psql -d mazimeal_full -f recommender/seed/01_demo_household.sql
psql -d mazimeal_full -f schema/seed/foodcom_400.sql
```

The last line is the 400 Food.com recipes. Same file the week-1 schema uses;
both schemas accept it.

Then:

```bash
cd recommender
python3 recommend.py members
python3 recommend.py for Maya
python3 recommend.py for Jeff --meal Dinner
python3 recommend.py for Jeff --explain salmon
python3 recommend.py household --meal Snack
```

## How it scores

For one member on one day:

1. **Hard filter.** Drop any recipe containing a household allergen, or that
   breaks a hard rule that applies to this member. These never appear.
2. **Gap.** For each nutrient with a daily target, gap = target minus what's
   been logged today.
3. **Score.** For each nutrient, how much of the gap one serving closes,
   capped at 100%. Average across all target nutrients. A recipe that would
   push a nutrient past its daily upper limit loses 25 points per nutrient.

So the same recipe scores differently for different people and at different
times of day. Salmon scores high for someone who hasn't had vitamin D; it
scores low for someone who already ate it at lunch.

For a household: score for each member, rank by the **lowest** score. A recipe
blocked for anyone is out. This is deliberate. Averaging would let one person's
needs get quietly ignored.

## Functions

| Function | Returns |
|---|---|
| `fn_recommend(member_id, date, meal, limit)` | ranked recipes with score, top 3 reasons, warnings |
| `fn_recommend_household(household_id, date, meal, limit)` | ranked recipes with per-member scores |
| `fn_explain(member_id, recipe_id, date)` | every nutrient: target, eaten, gap, per serving, % closed |
| `fn_blocked_recipes(member_id)` | what's excluded and why |
| `fn_member_gap(member_id, date)` | today's remaining need per nutrient |
| `v_recipe_nutrients_per_serving` | nutrients per serving for every recipe |

## What it doesn't do yet

These are the "try different models" list, roughly in order of value.

**Weight nutrients by clinical priority.** Right now every nutrient counts the
same. Maya has iron deficiency, but salmon (no iron) still ranks above the tofu
curry (26% of her iron gap) because salmon closes more gaps overall. Weighting
condition-linked nutrients higher is the obvious first improvement, and the
data to do it is already there in `nutrient_rules.applies_to_condition`.

**Micronutrients for Food.com recipes.** Food.com publishes nine nutrients
per serving (calories, protein, fat, carbs, fiber, sugar, sodium, cholesterol,
saturated fat). No iron, calcium or vitamins. So a Food.com recipe can only
close the energy, protein and fiber gaps and tops out around a third of the
possible score, while the six demo recipes, which have USDA values per
ingredient, rank above all of them. The fix is matching Food.com ingredient
names to `ingredients` rows that carry USDA nutrition, so the
ingredient-derived path fills in what the published data lacks. That's the
first thing to do once the recipes are in.

**Variety.** Nothing stops it recommending salmon every night. A penalty for
recipes eaten in the last N days needs `profile_recipe_history`, which exists
but the demo doesn't populate.

**Similarity.** "More like this" via pgvector on `recipes.embedding_vector`.
Column and index exist when pgvector is installed. Needs embeddings generated.

**Learned ranking.** Only after there's usage data. There isn't any.

## Known limits

- Volumes (cup, tbsp) convert to grams assuming water density. Whole items use
  `ingredients.typical_serving_g`. Lines that can't convert are left out, so a
  recipe with unconvertible lines under-reports.
- `v_recipe_nutrients_per_serving` is a plain view. Fine for hundreds of
  recipes; make it materialized before thousands.
- Demo data is illustrative. The iron modifier for C002 is a placeholder, not
  clinical guidance.
