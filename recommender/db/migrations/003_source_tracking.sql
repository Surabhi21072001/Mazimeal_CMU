-- Source tracking: data_sources, ingredient_source_map, source_id on nutrient
-- values and measures, and v_ingredient_nutrition (one value per nutrient by
-- source precedence). Rebuilds the cached nutrition views on top of it.
-- For databases installed before this change. Needs 001 and 002 first.
-- Re-runnable.
--
--   psql "$DATABASE_URL" -f recommender/db/migrations/003_source_tracking.sql
--   psql "$DATABASE_URL" -f schema/seed/ingredient_sources.sql

BEGIN;

CREATE TABLE IF NOT EXISTS data_sources (
    source_id         VARCHAR(30)   NOT NULL,
    source_name       VARCHAR(120)  NOT NULL,
    publisher         VARCHAR(120),
    region            VARCHAR(60),
    release           VARCHAR(40),
    licence           VARCHAR(120),
    attribution_text  TEXT,
    url               TEXT,
    precedence        SMALLINT      NOT NULL,
    ingested_at       DATE,

    CONSTRAINT pk_data_sources PRIMARY KEY (source_id),
    CONSTRAINT uq_data_sources_precedence UNIQUE (precedence)
);

INSERT INTO data_sources VALUES
    ('usda_sr_legacy', 'USDA FoodData Central, SR Legacy', 'USDA Agricultural Research Service', 'United States',
     '2018-04 (FDC release 2019-04)', 'CC0 1.0 (public domain)',
     'U.S. Department of Agriculture, Agricultural Research Service. FoodData Central, SR Legacy. fdc.nal.usda.gov',
     'https://fdc.nal.usda.gov/', 10, '2026-09-08'),
    ('foodcom', 'Food.com recipes (Kaggle)', 'Food.com via Kaggle', 'United States',
     'irkaal/foodcom-recipes-and-reviews', 'scraped dataset; check terms before shipping',
     'Recipes and per-serving nutrition from Food.com', 'https://www.kaggle.com/datasets/irkaal/foodcom-recipes-and-reviews', 50, '2026-09-08'),
    ('mazi_estimate', 'MaziMeal estimate', 'MaziMeal', NULL, NULL, NULL,
     'Estimated by MaziMeal when no source publishes a value', NULL, 90, NULL)
ON CONFLICT (source_id) DO NOTHING;

ALTER TABLE public.ingredient_nutrition
    ADD COLUMN IF NOT EXISTS source_id VARCHAR(30) NOT NULL DEFAULT 'usda_sr_legacy';
ALTER TABLE public.ingredient_nutrition DROP CONSTRAINT IF EXISTS uq_in_ing_nut;
ALTER TABLE public.ingredient_nutrition ADD CONSTRAINT uq_in_ing_nut UNIQUE (ingredient_id, nutrient_id, source_id);

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'ingredient_measures' AND column_name = 'source') THEN
        ALTER TABLE public.ingredient_measures RENAME COLUMN source TO source_id;
        UPDATE public.ingredient_measures
        SET    source_id = CASE source_id WHEN 'fallback' THEN 'mazi_estimate' ELSE 'usda_sr_legacy' END;
        ALTER TABLE public.ingredient_measures ALTER COLUMN source_id SET DEFAULT 'usda_sr_legacy';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.ingredient_source_map (
    ingredient_id       UUID          NOT NULL,
    source_id           VARCHAR(30)   NOT NULL,
    source_record_id    VARCHAR(60)   NOT NULL,
    source_description  TEXT,
    match_score         SMALLINT,
    matched_by          VARCHAR(20)   NOT NULL DEFAULT 'fuzzy',
    matched_at          DATE          NOT NULL DEFAULT current_date,
    CONSTRAINT pk_ingredient_source_map PRIMARY KEY (ingredient_id, source_id),
    CONSTRAINT ck_ism_matched_by CHECK (matched_by IN ('fuzzy', 'alias', 'manual'))
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_in_source') THEN
        ALTER TABLE public.ingredient_nutrition  ADD CONSTRAINT fk_in_source  FOREIGN KEY (source_id) REFERENCES public.data_sources (source_id);
        ALTER TABLE public.ingredient_measures   ADD CONSTRAINT fk_im_source  FOREIGN KEY (source_id) REFERENCES public.data_sources (source_id);
        ALTER TABLE public.ingredient_source_map ADD CONSTRAINT fk_ism_source FOREIGN KEY (source_id) REFERENCES public.data_sources (source_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_ism_ingredient')
       AND NOT EXISTS (SELECT 1 FROM pg_partitioned_table p JOIN pg_class c ON c.oid = p.partrelid WHERE c.relname = 'ingredients') THEN
        ALTER TABLE public.ingredient_source_map ADD CONSTRAINT fk_ism_ingredient
            FOREIGN KEY (ingredient_id) REFERENCES public.ingredients (ingredient_id) ON DELETE CASCADE;
    END IF;
END $$;

CREATE OR REPLACE VIEW public.v_ingredient_nutrition AS
SELECT DISTINCT ON (n.ingredient_id, n.nutrient_id)
       n.ingredient_id, n.nutrient_id, n.value_per_100g, n.unit,
       n.bioavailability_pct, n.data_quality_flag, n.source_id
FROM   public.ingredient_nutrition n
JOIN   public.data_sources s ON s.source_id = n.source_id
ORDER  BY n.ingredient_id, n.nutrient_id, s.precedence;

-- public read, same as the other reference tables
DO $$ DECLARE t text; BEGIN
    FOREACH t IN ARRAY ARRAY['data_sources', 'ingredient_source_map'] LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', t || '_public_read', t);
        EXECUTE format('CREATE POLICY %I ON public.%I FOR SELECT USING (true)', t || '_public_read', t);
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            EXECUTE format('GRANT SELECT ON public.%I TO anon, authenticated', t);
        END IF;
    END LOOP;
END $$;

-- cached nutrition views now read v_ingredient_nutrition
-- ---------------------------------------------------------------------------
-- Data quality per recipe: how many ingredient lines have grams, whether the
-- imported quantities lined up with their ingredients, and how far the
-- derived calories are from the published ones.
--
-- calibration_factor = published kcal / derived kcal, clamped to 0.25..4.
-- Imported recipes have a number per line but no unit, so grams are
-- estimates; the proportions between ingredients are usually right but the
-- total often isn't. Derived nutrients are multiplied by this factor so the
-- total agrees with the published calories. It's stored here, not hidden.
-- A factor near 1 means the gram estimates were good.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_recipe_nutrients_per_serving;
DROP MATERIALIZED VIEW IF EXISTS mv_recipe_nutrients;
DROP MATERIALIZED VIEW IF EXISTS mv_recipe_quality;
CREATE MATERIALIZED VIEW mv_recipe_quality AS
WITH lines AS (
    SELECT ri.recipe_id,
           count(*)                                                        AS lines_total,
           count(ri.quantity_g)                                            AS lines_with_grams,
           count(ri.quantity_g) FILTER (WHERE EXISTS (
               SELECT 1 FROM v_ingredient_nutrition n WHERE n.ingredient_id = ri.ingredient_id))
                                                                           AS lines_usable,
           bool_and(ri.quantity_aligned)                                   AS quantity_aligned
    FROM   recipe_ingredients ri
    JOIN   recipes r ON r.recipe_id = ri.recipe_id AND r.deleted_at IS NULL
    GROUP  BY ri.recipe_id
),
energy AS (
    SELECT ri.recipe_id,
           sum(ri.quantity_g * n.value_per_100g / 100.0) / greatest(r.servings, 1) AS derived_kcal
    FROM   recipe_ingredients ri
    JOIN   recipes r              ON r.recipe_id = ri.recipe_id
    JOIN   v_ingredient_nutrition n ON n.ingredient_id = ri.ingredient_id AND n.nutrient_id = 'Energy'
    WHERE  ri.quantity_g IS NOT NULL
    GROUP  BY ri.recipe_id, r.servings
)
SELECT l.recipe_id,
       l.lines_total,
       l.lines_with_grams,
       l.lines_usable,
       round(l.lines_usable::numeric / greatest(l.lines_total, 1), 2)      AS coverage,
       l.quantity_aligned,
       round(e.derived_kcal, 1)                                            AS derived_kcal,
       p.per_serving                                                       AS published_kcal,
       CASE WHEN p.per_serving > 0 AND e.derived_kcal > 0
            THEN round(least(greatest(p.per_serving / e.derived_kcal, 0.25), 4), 3)
       END                                                                 AS calibration_factor
FROM   lines l
LEFT   JOIN energy e ON e.recipe_id = l.recipe_id
LEFT   JOIN recipe_nutrition p ON p.recipe_id = l.recipe_id AND p.nutrient_id = 'Energy'
WITH NO DATA;

CREATE UNIQUE INDEX mv_recipe_quality_pk ON mv_recipe_quality (recipe_id);

-- ---------------------------------------------------------------------------
-- Nutrients per serving for every recipe. Published values (recipe_nutrition,
-- e.g. from Food.com) take precedence; anything else is derived from
-- ingredient grams: sum(quantity_g x value per 100 g / 100) / servings.
-- Lines without grams are left out, never counted as zero; a recipe whose
-- lines all lack grams simply has no derived rows. Derived rows carry the
-- calibration factor that was applied (see mv_recipe_quality).
--
-- Materialized: the recommender reads it many times per page. Refresh after
-- loading recipes, grams or ingredient nutrition:
--   select fn_refresh_recipe_nutrients();   The seed files do it.
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW mv_recipe_nutrients AS
WITH derived AS (
    SELECT ri.recipe_id,
           n.nutrient_id,
           n.unit,
           sum(ri.quantity_g * n.value_per_100g / 100.0) / greatest(r.servings, 1) AS per_serving
    FROM   recipe_ingredients ri
    JOIN   recipes r              ON r.recipe_id = ri.recipe_id AND r.deleted_at IS NULL
    JOIN   v_ingredient_nutrition n ON n.ingredient_id = ri.ingredient_id
    WHERE  ri.quantity_g IS NOT NULL
    GROUP  BY ri.recipe_id, n.nutrient_id, n.unit, r.servings
)
SELECT p.recipe_id, p.nutrient_id, p.unit, p.per_serving,
       'published'::text AS source, NULL::numeric AS calibration_factor
FROM   recipe_nutrition p
JOIN   recipes r ON r.recipe_id = p.recipe_id AND r.deleted_at IS NULL
UNION ALL
SELECT d.recipe_id, d.nutrient_id, d.unit,
       round(d.per_serving * coalesce(q.calibration_factor, 1), 4),
       'derived', coalesce(q.calibration_factor, 1)
FROM   derived d
LEFT   JOIN mv_recipe_quality q ON q.recipe_id = d.recipe_id
WHERE  NOT EXISTS (SELECT 1 FROM recipe_nutrition p
                   WHERE p.recipe_id = d.recipe_id AND p.nutrient_id = d.nutrient_id)
WITH NO DATA;

CREATE UNIQUE INDEX mv_recipe_nutrients_pk ON mv_recipe_nutrients (recipe_id, nutrient_id);
CREATE INDEX mv_recipe_nutrients_nutrient ON mv_recipe_nutrients (nutrient_id);

-- Everything else reads through this name.
CREATE VIEW v_recipe_nutrients_per_serving AS SELECT * FROM mv_recipe_nutrients;

CREATE OR REPLACE FUNCTION fn_refresh_recipe_nutrients() RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_class WHERE relname = 'mv_recipe_quality' AND relispopulated) THEN
        REFRESH MATERIALIZED VIEW CONCURRENTLY mv_recipe_quality;
        REFRESH MATERIALIZED VIEW CONCURRENTLY mv_recipe_nutrients;
    ELSE
        REFRESH MATERIALIZED VIEW mv_recipe_quality;
        REFRESH MATERIALIZED VIEW mv_recipe_nutrients;
    END IF;
END $$;

SELECT fn_refresh_recipe_nutrients();

COMMIT;
