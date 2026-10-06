-- 98_recipe.sql
-- The nutrition facts panel for one recipe, recalculated on the fly.
--
--   select fn_recipe_nutrition(recipe_id);                  -- as stored
--   select fn_recipe_nutrition(recipe_id, '[...]');         -- with changes
--   select fn_recipe_nutrition(recipe_id, '[]', 6);         -- as 6 servings
--
-- From the frontend: supabase.rpc('fn_recipe_nutrition', { p_recipe_id, p_overrides, p_servings })
--
-- p_overrides is a JSON array; each element changes one line:
--   { "line_id": "...", "quantity": 2, "measure": "tbsp" }   change the amount
--   { "line_id": "...", "ingredient_id": "..." }             swap the ingredient (amount kept)
--   { "line_id": "...", "grams": 150 }                       set grams directly
--   { "line_id": "...", "remove": true }                     drop the line
--   { "ingredient_id": "...", "quantity": 1, "measure": "cup" }   add a line
--
-- Grams per line: explicit grams, else the stored grams if the line is
-- untouched, else quantity x ingredient_measures weight for that measure,
-- else fn_line_grams. Nutrients are sum(grams x value per 100 g / 100) over
-- servings, from v_ingredient_nutrition. As stored, published values
-- (Food.com macros) are shown where they exist, same as the home page; once
-- a line changes, every nutrient is derived, multiplied by the recipe's
-- stored calibration factor so the edited version is on the same footing
-- as the original. 'original' on each nutrient is what the stored recipe
-- shows, for the UI to display the change.
--
-- {
--   recipe_id, name, servings, original_servings, changed, calibration_factor, coverage,
--   lines:     [ { line_id, ingredient_id, ingredient, quantity, measure, grams, basis, changed,
--                  measures: [ { measure, grams } ] } ],
--   nutrients: [ { nutrient, label, unit, category, per_serving, original, source } ]
-- }

CREATE OR REPLACE FUNCTION fn_recipe_nutrition(
    p_recipe_id  UUID,
    p_overrides  JSONB   DEFAULT '[]'::jsonb,
    p_servings   DECIMAL DEFAULT NULL
)
RETURNS JSONB
LANGUAGE sql STABLE
SECURITY DEFINER SET search_path = public AS $$
    WITH r AS (
        SELECT recipe_id, recipe_name, greatest(coalesce(servings, 1), 1) AS servings
        FROM   recipes
        WHERE  recipe_id = p_recipe_id AND deleted_at IS NULL
    ),
    ov AS (
        SELECT (o ->> 'line_id')::uuid        AS line_id,
               (o ->> 'ingredient_id')::uuid  AS ingredient_id,
               (o ->> 'quantity')::decimal    AS quantity,
               lower(o ->> 'measure')         AS measure,
               (o ->> 'grams')::decimal       AS grams,
               coalesce((o ->> 'remove')::boolean, false) AS remove,
               ord
        FROM   jsonb_array_elements(coalesce(p_overrides, '[]'::jsonb)) WITH ORDINALITY AS t(o, ord)
    ),
    lines AS (
        -- stored lines, with any override merged in; removed ones dropped
        SELECT b.line_id,
               coalesce(o.ingredient_id, b.ingredient_id)      AS ingredient_id,
               coalesce(o.quantity, b.quantity)                AS quantity,
               coalesce(o.measure, b.measure)                  AS measure,
               CASE WHEN o.line_id IS NULL THEN b.quantity_g END AS stored_g,
               o.grams                                         AS grams_override,
               (o.line_id IS NOT NULL)                         AS changed,
               0 AS ord, b.sequence_order
        FROM   recipe_ingredients b
        LEFT   JOIN ov o ON o.line_id = b.line_id
        WHERE  b.recipe_id = p_recipe_id
        AND    NOT coalesce(o.remove, false)
        UNION ALL
        -- added lines
        SELECT NULL, o.ingredient_id, coalesce(o.quantity, 1), o.measure, NULL, o.grams, true, o.ord::int, NULL
        FROM   ov o
        WHERE  o.line_id IS NULL AND o.ingredient_id IS NOT NULL
    ),
    grams AS (
        SELECT l.*, i.ingredient_name,
               coalesce(l.grams_override,
                        l.stored_g,
                        l.quantity * m.gram_weight,
                        nullif(fn_line_grams(l.quantity, l.measure, i.typical_serving_g), 0)) AS g,
               CASE WHEN l.grams_override IS NOT NULL THEN 'manual'
                    WHEN l.stored_g IS NOT NULL       THEN 'stored'
                    WHEN m.gram_weight IS NOT NULL    THEN 'measure'
                    WHEN fn_line_grams(l.quantity, l.measure, i.typical_serving_g) > 0 THEN 'unit'
                    ELSE 'none' END AS basis
        FROM   lines l
        JOIN   ingredients i ON i.ingredient_id = l.ingredient_id
        LEFT   JOIN ingredient_measures m ON m.ingredient_id = l.ingredient_id AND m.measure = l.measure
    ),
    state AS (
        SELECT coalesce(bool_or(changed), false) AS changed,
               coalesce(p_servings, (SELECT servings FROM r)) AS servings,
               (SELECT servings FROM r) AS original_servings,
               count(*) AS lines_total,
               count(g) FILTER (WHERE EXISTS (SELECT 1 FROM v_ingredient_nutrition n WHERE n.ingredient_id = grams.ingredient_id)) AS lines_usable
        FROM   grams
    ),
    derived AS (
        SELECT n.nutrient_id, n.unit,
               sum(g.g * n.value_per_100g / 100.0) / greatest((SELECT servings FROM state), 0.01) AS per_serving
        FROM   grams g
        JOIN   v_ingredient_nutrition n ON n.ingredient_id = g.ingredient_id
        WHERE  g.g IS NOT NULL
        GROUP  BY n.nutrient_id, n.unit
    ),
    factor AS (
        SELECT coalesce((SELECT calibration_factor FROM mv_recipe_quality WHERE recipe_id = p_recipe_id), 1) AS f,
               (SELECT coverage FROM mv_recipe_quality WHERE recipe_id = p_recipe_id) AS coverage
    ),
    nutrients AS (
        SELECT nm.nutrient_id, nm.nutrient_name, coalesce(d.unit, p.unit, nm.default_unit) AS unit, nm.nutrient_category,
               CASE WHEN NOT s.changed AND p.per_serving IS NOT NULL
                    THEN round(p.per_serving * s.original_servings / greatest(s.servings, 0.01), 2)
                    ELSE round(d.per_serving * f.f, 2) END AS per_serving,
               CASE WHEN NOT s.changed AND p.per_serving IS NOT NULL THEN 'published' ELSE 'derived' END AS source,
               round(mv.per_serving, 2) AS original
        FROM   nutrients_master nm
        CROSS  JOIN state s
        CROSS  JOIN factor f
        LEFT   JOIN derived d          ON d.nutrient_id = nm.nutrient_id
        LEFT   JOIN recipe_nutrition p ON p.recipe_id = p_recipe_id AND p.nutrient_id = nm.nutrient_id
        LEFT   JOIN mv_recipe_nutrients mv ON mv.recipe_id = p_recipe_id AND mv.nutrient_id = nm.nutrient_id
        WHERE  d.nutrient_id IS NOT NULL OR p.nutrient_id IS NOT NULL
    )
    SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM r) THEN NULL ELSE jsonb_build_object(
        'recipe_id',          p_recipe_id,
        'name',               (SELECT recipe_name FROM r),
        'servings',           (SELECT servings FROM state),
        'original_servings',  (SELECT original_servings FROM state),
        'changed',            (SELECT changed FROM state),
        'calibration_factor', (SELECT f FROM factor),
        'coverage',           CASE WHEN (SELECT changed FROM state)
                                   THEN round((SELECT lines_usable::numeric / greatest(lines_total, 1) FROM state), 2)
                                   ELSE (SELECT coverage FROM factor) END,
        'lines', coalesce((
            SELECT jsonb_agg(jsonb_build_object(
                       'line_id',       g.line_id,
                       'ingredient_id', g.ingredient_id,
                       'ingredient',    g.ingredient_name,
                       'quantity',      g.quantity,
                       'measure',       g.measure,
                       'grams',         round(g.g, 1),
                       'basis',         g.basis,
                       'changed',       g.changed,
                       'measures',      coalesce((SELECT jsonb_agg(jsonb_build_object('measure', m.measure, 'grams', m.gram_weight)
                                                                   ORDER BY m.measure)
                                                  FROM ingredient_measures m WHERE m.ingredient_id = g.ingredient_id), '[]'::jsonb))
                       ORDER BY g.ord, g.sequence_order NULLS LAST, g.ingredient_name)
            FROM grams g), '[]'::jsonb),
        'nutrients', coalesce((
            SELECT jsonb_agg(jsonb_build_object(
                       'nutrient',    n.nutrient_id,
                       'label',       n.nutrient_name,
                       'unit',        n.unit,
                       'category',    n.nutrient_category,
                       'per_serving', n.per_serving,
                       'original',    n.original,
                       'source',      n.source)
                       ORDER BY array_position(ARRAY['Macro', 'Fat-soluble', 'Water-soluble', 'Mineral', 'Other'], n.nutrient_category),
                                n.nutrient_id)
            FROM nutrients n), '[]'::jsonb)
    ) END
$$;

ALTER FUNCTION fn_recipe_nutrition(UUID, JSONB, DECIMAL) SET jit = off;

-- Reads public reference data only; SECURITY DEFINER so the cached views
-- (no RLS on materialized views) are readable through it from the app.
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        GRANT EXECUTE ON FUNCTION fn_recipe_nutrition(UUID, JSONB, DECIMAL) TO anon, authenticated;
    END IF;
END $$;
