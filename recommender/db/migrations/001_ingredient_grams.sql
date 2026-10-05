-- Grams per recipe line and household measures per ingredient.
-- For databases installed before this change. Fresh installs get it from
-- 50_ingredients_nutrition.sql and 70_recipes.sql. Safe to run more than once.
--
--   psql "$DATABASE_URL" -f recommender/db/migrations/001_ingredient_grams.sql
--   psql "$DATABASE_URL" -f schema/seed/ingredient_grams.sql

BEGIN;

ALTER TABLE public.ingredients
    ADD COLUMN IF NOT EXISTS default_measure VARCHAR(40);

CREATE TABLE IF NOT EXISTS public.ingredient_measures (
    ingredient_id      UUID          NOT NULL,
    measure            VARCHAR(40)   NOT NULL,
    gram_weight        DECIMAL(8,2)  NOT NULL,
    source             VARCHAR(30)   NOT NULL DEFAULT 'USDA SR Legacy',
    source_portion_id  BIGINT,
    CONSTRAINT pk_ingredient_measures PRIMARY KEY (ingredient_id, measure),
    CONSTRAINT ck_im_grams CHECK (gram_weight > 0)
);

ALTER TABLE public.recipe_ingredients
    ADD COLUMN IF NOT EXISTS measure          VARCHAR(40),
    ADD COLUMN IF NOT EXISTS quantity_g       DECIMAL(10,2),
    ADD COLUMN IF NOT EXISTS grams_source     VARCHAR(20) NOT NULL DEFAULT 'none',
    ADD COLUMN IF NOT EXISTS quantity_aligned BOOLEAN;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_ri_grams') THEN
        ALTER TABLE public.recipe_ingredients
            ADD CONSTRAINT ck_ri_grams     CHECK (quantity_g IS NULL OR quantity_g > 0),
            ADD CONSTRAINT ck_ri_grams_src CHECK (grams_source IN ('manual', 'measure', 'assumed', 'none'));
    END IF;
    -- MVP mode only: ingredients is partitioned in SCALE mode and can't be referenced
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_im_ingredient')
       AND NOT EXISTS (SELECT 1 FROM pg_partitioned_table p JOIN pg_class c ON c.oid = p.partrelid WHERE c.relname = 'ingredients') THEN
        ALTER TABLE public.ingredient_measures
            ADD CONSTRAINT fk_im_ingredient
            FOREIGN KEY (ingredient_id) REFERENCES public.ingredients (ingredient_id) ON DELETE CASCADE;
    END IF;
END $$;

ALTER TABLE public.ingredient_measures ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ingredient_measures_public_read ON public.ingredient_measures;
CREATE POLICY ingredient_measures_public_read ON public.ingredient_measures FOR SELECT USING (true);
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        GRANT SELECT ON public.ingredient_measures TO anon, authenticated;
    END IF;
END $$;

COMMENT ON COLUMN public.recipe_ingredients.quantity_g       IS 'Grams for this line. What nutrition is calculated from. NULL = unknown, never 0.';
COMMENT ON COLUMN public.recipe_ingredients.grams_source     IS 'manual: entered in grams. measure: quantity x measure weight. assumed: no quantity in the source, 1 measure assumed. none: unknown.';
COMMENT ON COLUMN public.recipe_ingredients.quantity_aligned IS 'Imported recipes only. FALSE when the source quantity list did not line up with its ingredient list.';

COMMIT;
