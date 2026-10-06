-- fn_log_meal, fn_unlog_meal, fn_member_meals: meal logging with a frozen
-- nutrient snapshot per person, plus log_id on profile_recipe_history.
-- Same definitions as recommender/db/98_log.sql. Needs 001-004. Re-runnable.
--
--   psql "$DATABASE_URL" -f recommender/db/migrations/005_log_meal.sql

ALTER TABLE public.profile_recipe_history ADD COLUMN IF NOT EXISTS log_id UUID;

-- pct_of_target was DECIMAL(5,2): one meal against a small target (a child's
-- B12) overflows 999.99%. Widen it and cap the trigger.
ALTER TABLE public.nutrient_daily_log ALTER COLUMN pct_of_target TYPE DECIMAL(8,2);
CREATE OR REPLACE FUNCTION public.trg_ndl_derive() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    IF NEW.target_value > 0 THEN
        NEW.pct_of_target := least(round((NEW.consumed_value / NEW.target_value) * 100, 2), 999999.99);
    ELSE
        NEW.pct_of_target := NULL;
    END IF;
    RETURN NEW;
END $$;
CREATE INDEX IF NOT EXISTS idx_prh_log ON public.profile_recipe_history (log_id);
COMMENT ON COLUMN public.profile_recipe_history.log_id IS 'One meal logged once for several members shares a log_id. Client-generated, so a retried fn_log_meal call is a no-op.';

\ir ../98_log.sql

-- The app reads these directly (recipe screen); RLS already allows public
-- SELECT, but the Supabase roles also need the table grant.
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        GRANT SELECT ON public.recipes, public.recipe_steps, public.recipe_ingredients, public.ingredients,
                        public.ingredient_measures, public.data_sources, public.nutrients_master
        TO anon, authenticated;
    END IF;
END $$;
