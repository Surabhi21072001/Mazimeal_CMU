-- 99_validate.sql
-- Checks the recipe data: total count, duplicates, missing fields.
--
--   psql -d mazimeal -f schema/99_validate.sql
--   select * from validate_week1();
--
-- Safe to run any time. Checks against tables that don't exist yet report SKIP.

CREATE OR REPLACE FUNCTION validate_week1()
RETURNS TABLE (
    status  TEXT,
    check_name TEXT,
    detail  TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    n           bigint;
    m           bigint;
    r           RECORD;
    -- Original batch plan: Breakfast 80, Lunch 80, Dinner 100, Snacks 60,
    -- Special Diets 80 = 400.
    target_total constant int := 400;
BEGIN
    ------------------------------------------------------------------
    -- 1 · Total recipe count
    ------------------------------------------------------------------
    SELECT count(*) INTO n FROM recipes WHERE deleted_at IS NULL;

    status     := CASE WHEN n = target_total THEN 'PASS'
                       WHEN n > target_total THEN 'WARN'
                       ELSE 'PENDING' END;
    check_name := 'total recipe count';
    detail     := n || ' of ' || target_total
                  || CASE WHEN n < target_total
                          THEN ' (' || (target_total - n) || ' remaining)'
                          WHEN n > target_total
                          THEN ' (' || (n - target_total) || ' OVER target)'
                          ELSE '' END;
    RETURN NEXT;

    ------------------------------------------------------------------
    -- 2 · Count per meal type
    ------------------------------------------------------------------
    FOR r IN
        SELECT meal_category, count(*) AS c
        FROM   recipes
        WHERE  deleted_at IS NULL
        GROUP  BY meal_category
        ORDER  BY meal_category
    LOOP
        status     := 'INFO';
        check_name := 'slot: ' || r.meal_category;
        detail     := r.c || ' recipes';
        RETURN NEXT;
    END LOOP;

    ------------------------------------------------------------------
    -- 3 · Special-diet coverage
    ------------------------------------------------------------------
    SELECT count(*) INTO n
    FROM   recipes
    WHERE  deleted_at IS NULL
      AND  dietary_tags IS NOT NULL
      AND  cardinality(dietary_tags) > 0;

    status     := CASE WHEN n >= 80 THEN 'PASS' ELSE 'PENDING' END;
    check_name := 'special-diet recipes';
    detail     := n || ' of 80 tagged';
    RETURN NEXT;

    ------------------------------------------------------------------
    -- 4 · Exact duplicate names. The unique index should prevent these.
    ------------------------------------------------------------------
    SELECT count(*) INTO n FROM (
        SELECT lower(recipe_name)
        FROM   recipes
        WHERE  deleted_at IS NULL
        GROUP  BY lower(recipe_name)
        HAVING count(*) > 1
    ) d;

    status     := CASE WHEN n = 0 THEN 'PASS' ELSE 'FAIL' END;
    check_name := 'duplicate recipe names (exact)';
    detail     := CASE WHEN n = 0 THEN 'none'
                       ELSE n || ' duplicated name(s)' END;
    RETURN NEXT;

    ------------------------------------------------------------------
    -- 5 · Near duplicates. The index catches "Masala Oats" vs "masala oats"
    --     but not "Masala-Oats", so strip punctuation and compare again.
    ------------------------------------------------------------------
    FOR r IN
        SELECT lower(regexp_replace(recipe_name, '[^a-zA-Z0-9]+', '', 'g')) AS norm,
               count(*)      AS c,
               string_agg(recipe_name, ' | ' ORDER BY recipe_name) AS names
        FROM   recipes
        WHERE  deleted_at IS NULL
        GROUP  BY 1
        HAVING count(*) > 1
    LOOP
        status     := 'FAIL';
        check_name := 'near-duplicate recipe name';
        detail     := r.c || 'x: ' || r.names;
        RETURN NEXT;
    END LOOP;

    IF NOT FOUND THEN
        status     := 'PASS';
        check_name := 'duplicate recipe names (normalised)';
        detail     := 'none';
        RETURN NEXT;
    END IF;

    ------------------------------------------------------------------
    -- 6 · Required fields present
    ------------------------------------------------------------------
    SELECT count(*) INTO n
    FROM   recipes
    WHERE  deleted_at IS NULL
      AND (recipe_name IS NULL OR btrim(recipe_name) = ''
           OR servings IS NULL);

    status     := CASE WHEN n = 0 THEN 'PASS' ELSE 'FAIL' END;
    check_name := 'required fields populated';
    detail     := CASE WHEN n = 0 THEN 'all rows complete'
                       ELSE n || ' row(s) missing name or servings' END;
    RETURN NEXT;

    ------------------------------------------------------------------
    -- 7 · Nutrition rules
    ------------------------------------------------------------------
    IF to_regclass('public.nutrient_rules') IS NULL THEN
        status := 'SKIP'; check_name := 'nutrient_rules'; detail := 'table not created yet';
        RETURN NEXT;
    ELSE
        SELECT count(*) INTO n FROM nutrient_rules;
        status := 'INFO'; check_name := 'nutrition rules loaded'; detail := n || ' rules';
        RETURN NEXT;

        -- Hard rules block recipes, so they need a source.
        SELECT count(*) INTO n
        FROM   nutrient_rules
        WHERE  is_hard_constraint
          AND  source IS NULL AND document_id IS NULL;

        status     := CASE WHEN n = 0 THEN 'PASS' ELSE 'FAIL' END;
        check_name := 'hard rules cite evidence';
        detail     := CASE WHEN n = 0 THEN 'all cited'
                           ELSE n || ' hard rule(s) with no source' END;
        RETURN NEXT;
    END IF;

    ------------------------------------------------------------------
    -- 8 · Ingredients — Swetha's table
    ------------------------------------------------------------------
    IF to_regclass('public.ingredients') IS NULL THEN
        status := 'SKIP'; check_name := 'ingredients'; detail := 'table not created yet';
        RETURN NEXT;
    ELSE
        EXECUTE 'SELECT count(*) FROM ingredients' INTO n;
        status := 'INFO'; check_name := 'ingredient count'; detail := n || ' ingredients';
        RETURN NEXT;

        IF to_regclass('public.ingredient_nutrition') IS NOT NULL THEN
            EXECUTE 'SELECT count(*), count(DISTINCT ingredient_id) FROM ingredient_nutrition' INTO n, m;
            status := 'INFO'; check_name := 'ingredients with USDA nutrition';
            detail := m || ' ingredients, ' || n || ' nutrient values';
            RETURN NEXT;
        END IF;

        IF to_regclass('public.ingredient_source_map') IS NOT NULL THEN
            EXECUTE 'SELECT count(DISTINCT ingredient_id), count(*) FROM ingredient_source_map' INTO n, m;
            status := 'INFO'; check_name := 'ingredients with a source record';
            detail := n || ' ingredients, ' || m || ' source links';
            RETURN NEXT;
        END IF;

        IF to_regclass('public.ingredient_measures') IS NOT NULL THEN
            EXECUTE 'SELECT count(*) FILTER (WHERE quantity_g IS NOT NULL), count(*) FROM recipe_ingredients' INTO n, m;
            status := 'INFO'; check_name := 'recipe lines with grams';
            detail := n || ' of ' || m;
            RETURN NEXT;
        END IF;

        -- If we each add ingredients as we go, "Tomato", "tomato" and
        -- "Tomatoes" end up as three rows and the nutrition maths splits.
        EXECUTE $q$
            SELECT count(*) FROM (
                SELECT lower(regexp_replace(ingredient_name, '[^a-zA-Z0-9]+', '', 'g'))
                FROM ingredients
                GROUP BY 1 HAVING count(*) > 1
            ) d
        $q$ INTO n;

        status     := CASE WHEN n = 0 THEN 'PASS' ELSE 'FAIL' END;
        check_name := 'duplicate ingredients (normalised)';
        detail     := CASE WHEN n = 0 THEN 'none'
                           ELSE n || ' ingredient(s) entered more than once' END;
        RETURN NEXT;
    END IF;

    ------------------------------------------------------------------
    -- 9 · Recipe_Ingredients — Kate's table
    ------------------------------------------------------------------
    IF to_regclass('public.recipe_ingredients') IS NULL THEN
        status := 'SKIP'; check_name := 'recipe_ingredients'; detail := 'table not created yet';
        RETURN NEXT;
    ELSE
        -- A recipe with no ingredients looks fine but computes zero nutrition.
        EXECUTE $q$
            SELECT count(*) FROM recipes r
            WHERE r.deleted_at IS NULL
              AND NOT EXISTS (SELECT 1 FROM recipe_ingredients ri
                              WHERE ri.recipe_id = r.recipe_id)
        $q$ INTO n;

        status     := CASE WHEN n = 0 THEN 'PASS' ELSE 'WARN' END;
        check_name := 'recipes have ingredients';
        detail     := CASE WHEN n = 0 THEN 'all recipes linked'
                           ELSE n || ' recipe(s) with no ingredient lines' END;
        RETURN NEXT;

        EXECUTE $q$
            SELECT count(*) FROM recipe_ingredients ri
            WHERE NOT EXISTS (SELECT 1 FROM recipes r WHERE r.recipe_id = ri.recipe_id)
        $q$ INTO m;

        status     := CASE WHEN m = 0 THEN 'PASS' ELSE 'FAIL' END;
        check_name := 'no orphan ingredient lines';
        detail     := CASE WHEN m = 0 THEN 'none'
                           ELSE m || ' line(s) point at a missing recipe' END;
        RETURN NEXT;
    END IF;

    RETURN;
END
$$;

COMMENT ON FUNCTION validate_week1() IS
  'Recipe data validation. PASS/FAIL/WARN/PENDING/SKIP per check. Run after every insert batch.';

-- Shortcut view.
CREATE OR REPLACE VIEW v_week1_status AS
SELECT status, check_name, detail FROM validate_week1();

-- Run it now
SELECT * FROM validate_week1();
