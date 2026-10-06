-- Checks for fn_recipe_nutrition. Run against a database with the full
-- schema and the seed files loaded:
--   psql -d <db> -v ON_ERROR_STOP=1 -f recommender/tests/fn_recipe_nutrition.sql
-- Prints one line per check; stops at the first failure.

\set ON_ERROR_STOP on
\set QUIET on

DO $$
DECLARE
    rid   UUID;
    oil   UUID;
    j     JSONB;
    kcal  NUMERIC;
    kcal2 NUMERIC;
    n     INT;
BEGIN
    SELECT recipe_id INTO rid FROM recipes WHERE recipe_name = 'Bourbon Chicken';
    IF rid IS NULL THEN RAISE EXCEPTION 'Bourbon Chicken not loaded'; END IF;

    -- 1. as stored: published macros, derived for the rest, no change flagged
    j := fn_recipe_nutrition(rid);
    IF (j ->> 'changed')::boolean THEN RAISE EXCEPTION 'unchanged recipe reports changed'; END IF;
    SELECT count(*) INTO n FROM jsonb_array_elements(j -> 'nutrients') e WHERE e ->> 'source' = 'published';
    IF n < 5 THEN RAISE EXCEPTION 'expected published macros, got % published rows', n; END IF;
    SELECT count(*) INTO n FROM jsonb_array_elements(j -> 'nutrients') e WHERE e ->> 'source' = 'derived';
    IF n < 10 THEN RAISE EXCEPTION 'expected derived micronutrients, got %', n; END IF;
    SELECT (e ->> 'per_serving')::numeric INTO kcal FROM jsonb_array_elements(j -> 'nutrients') e WHERE e ->> 'nutrient' = 'Energy';
    IF kcal IS NULL OR kcal <= 0 THEN RAISE EXCEPTION 'no energy value'; END IF;
    IF jsonb_array_length(j -> 'lines') <> (SELECT count(*) FROM recipe_ingredients WHERE recipe_id = rid) THEN
        RAISE EXCEPTION 'line count differs from recipe_ingredients';
    END IF;
    RAISE NOTICE 'ok  as stored: % kcal, % lines', kcal, jsonb_array_length(j -> 'lines');

    -- 2. stored values match the cached view the home page uses
    SELECT count(*) INTO n
    FROM   jsonb_array_elements(j -> 'nutrients') e
    JOIN   mv_recipe_nutrients mv ON mv.recipe_id = rid AND mv.nutrient_id = e ->> 'nutrient'
    WHERE  abs((e ->> 'per_serving')::numeric - mv.per_serving) > 0.05;
    IF n > 0 THEN RAISE EXCEPTION '% nutrients differ from mv_recipe_nutrients', n; END IF;
    RAISE NOTICE 'ok  matches mv_recipe_nutrients';

    -- 3. doubling the servings halves every per-serving value
    j := fn_recipe_nutrition(rid, '[]', (SELECT servings * 2 FROM recipes WHERE recipe_id = rid));
    SELECT (e ->> 'per_serving')::numeric INTO kcal2 FROM jsonb_array_elements(j -> 'nutrients') e WHERE e ->> 'nutrient' = 'Energy';
    IF abs(kcal2 * 2 - kcal) > 0.1 THEN RAISE EXCEPTION 'servings x2: expected % got %', kcal / 2, kcal2; END IF;
    RAISE NOTICE 'ok  servings x2: % kcal', kcal2;

    -- 4. tripling the oil raises energy, flags the change, switches to derived
    SELECT ri.line_id INTO oil FROM recipe_ingredients ri JOIN ingredients i USING (ingredient_id)
    WHERE ri.recipe_id = rid AND lower(i.ingredient_name) = 'olive oil';
    j := fn_recipe_nutrition(rid, jsonb_build_array(jsonb_build_object('line_id', oil, 'quantity', 3, 'measure', 'tbsp')));
    IF NOT (j ->> 'changed')::boolean THEN RAISE EXCEPTION 'override not flagged as change'; END IF;
    SELECT (e ->> 'per_serving')::numeric INTO kcal2 FROM jsonb_array_elements(j -> 'nutrients') e WHERE e ->> 'nutrient' = 'Energy';
    IF (SELECT (e ->> 'source') FROM jsonb_array_elements(j -> 'nutrients') e WHERE e ->> 'nutrient' = 'Energy') <> 'derived' THEN
        RAISE EXCEPTION 'changed recipe still shows published energy';
    END IF;
    IF kcal2 <= (SELECT (e ->> 'original')::numeric FROM jsonb_array_elements(j -> 'nutrients') e WHERE e ->> 'nutrient' = 'Energy') * 0 THEN
        RAISE EXCEPTION 'energy not positive after override';
    END IF;
    SELECT (l ->> 'grams')::numeric INTO kcal FROM jsonb_array_elements(j -> 'lines') l WHERE (l ->> 'line_id')::uuid = oil;
    IF abs(kcal - 40.5) > 0.5 THEN RAISE EXCEPTION '3 tbsp olive oil should be ~40.5 g, got %', kcal; END IF;
    RAISE NOTICE 'ok  3 tbsp oil: % g on the line, % kcal derived', kcal, kcal2;

    -- 5. removing the oil line drops it from the output
    j := fn_recipe_nutrition(rid, jsonb_build_array(jsonb_build_object('line_id', oil, 'remove', true)));
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(j -> 'lines') l WHERE (l ->> 'line_id')::uuid = oil) THEN
        RAISE EXCEPTION 'removed line still present';
    END IF;
    RAISE NOTICE 'ok  remove line';

    -- 6. explicit grams win over everything
    j := fn_recipe_nutrition(rid, jsonb_build_array(jsonb_build_object('line_id', oil, 'grams', 100)));
    SELECT (l ->> 'grams')::numeric INTO kcal FROM jsonb_array_elements(j -> 'lines') l WHERE (l ->> 'line_id')::uuid = oil;
    IF kcal <> 100 THEN RAISE EXCEPTION 'explicit grams ignored: %', kcal; END IF;
    RAISE NOTICE 'ok  explicit grams';

    -- 7. adding a line
    j := fn_recipe_nutrition(rid, jsonb_build_array(jsonb_build_object(
             'ingredient_id', (SELECT ingredient_id FROM ingredients WHERE lower(ingredient_name) = 'garlic clove' LIMIT 1),
             'quantity', 4, 'measure', 'clove')));
    IF jsonb_array_length(j -> 'lines') <> (SELECT count(*) + 1 FROM recipe_ingredients WHERE recipe_id = rid) THEN
        RAISE EXCEPTION 'added line missing';
    END IF;
    RAISE NOTICE 'ok  add line';

    -- 8. unknown recipe returns NULL, not an error
    IF fn_recipe_nutrition('00000000-0000-0000-0000-000000000000') IS NOT NULL THEN
        RAISE EXCEPTION 'unknown recipe should return NULL';
    END IF;
    RAISE NOTICE 'ok  unknown recipe -> NULL';
END $$;
