-- Recipe nutrition from grams per line, plus a per-recipe data quality view.
-- Same definitions as recommender/db/97_recommender.sql, for databases
-- installed before this change. Needs migration 001 first. Re-runnable.
--
--   psql "$DATABASE_URL" -f recommender/db/migrations/002_nutrition_from_grams.sql

BEGIN;

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
               SELECT 1 FROM ingredient_nutrition n WHERE n.ingredient_id = ri.ingredient_id))
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
    JOIN   ingredient_nutrition n ON n.ingredient_id = ri.ingredient_id AND n.nutrient_id = 'Energy'
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
    JOIN   ingredient_nutrition n ON n.ingredient_id = ri.ingredient_id
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
