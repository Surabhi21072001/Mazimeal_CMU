-- fn_recipe_nutrition: the nutrition panel for one recipe, recalculated on
-- the fly with swaps, amount changes and serving changes. Same definition as
-- recommender/db/98_recipe.sql. Needs 001-003. Re-runnable.
--
--   psql "$DATABASE_URL" -f recommender/db/migrations/004_recipe_nutrition_fn.sql

\ir ../98_recipe.sql
