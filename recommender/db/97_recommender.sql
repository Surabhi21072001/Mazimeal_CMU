-- 97_recommender.sql
-- Baseline recipe recommender. Rule-based and explainable, no ML.
--
--   1. Hard filter: drop recipes with a household allergen or that break a
--      hard rule for this member.
--   2. Score the rest by how much of today's remaining nutrient gap one
--      serving closes. 100 = fills every gap, 0 = fills none.
--   3. Household: score per member, rank by the weakest member's score.
--
--   select * from fn_recommend(member_id, current_date, 'Dinner', 10);
--   select * from fn_recommend_household(household_id, current_date, 'Dinner', 10);
--
-- Callable from the frontend as supabase.rpc('fn_recommend', {...}).

-- ---------------------------------------------------------------------------
-- Grams for one ingredient line. Volumes assume water density; whole items
-- use typical_serving_g. Lines that can't be converted return NULL and are
-- left out of the total, so a recipe with unconvertible lines under-reports.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_line_grams(
    p_quantity DECIMAL, p_unit TEXT, p_typical_serving_g DECIMAL
) RETURNS DECIMAL
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE lower(p_unit)
        WHEN 'g'     THEN p_quantity
        WHEN 'kg'    THEN p_quantity * 1000
        WHEN 'ml'    THEN p_quantity
        WHEN 'l'     THEN p_quantity * 1000
        WHEN 'tsp'   THEN p_quantity * 5
        WHEN 'tbsp'  THEN p_quantity * 15
        WHEN 'cup'   THEN p_quantity * 240
        WHEN 'oz'    THEN p_quantity * 28.35
        WHEN 'lb'    THEN p_quantity * 453.6
        ELSE p_quantity * p_typical_serving_g   -- whole, cloves, slices, portion
    END
$$;

-- ---------------------------------------------------------------------------
-- Nutrients per serving for every recipe. Published values (recipe_nutrition,
-- e.g. from Food.com) take precedence; anything else is derived from
-- ingredient quantities. A view for now; materialize at thousands of recipes.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_recipe_nutrients_per_serving AS
WITH derived AS (
    SELECT ri.recipe_id,
           n.nutrient_id,
           n.unit,
           sum(fn_line_grams(ri.quantity, ri.unit, i.typical_serving_g) * n.value_per_100g / 100.0)
               / greatest(r.servings, 1)                                   AS per_serving,
           count(*) FILTER (WHERE fn_line_grams(ri.quantity, ri.unit, i.typical_serving_g) IS NULL)
                                                                             AS unconverted_lines
    FROM   recipe_ingredients ri
    JOIN   recipes r              ON r.recipe_id = ri.recipe_id AND r.deleted_at IS NULL
    JOIN   ingredients i          ON i.ingredient_id = ri.ingredient_id
    JOIN   ingredient_nutrition n ON n.ingredient_id = ri.ingredient_id
    GROUP  BY ri.recipe_id, n.nutrient_id, n.unit, r.servings
)
-- published values first
SELECT p.recipe_id, p.nutrient_id, p.unit, p.per_serving, 0 AS unconverted_lines
FROM   recipe_nutrition p
JOIN   recipes r ON r.recipe_id = p.recipe_id AND r.deleted_at IS NULL
UNION ALL
-- then anything derived that the published data doesn't cover
SELECT d.recipe_id, d.nutrient_id, d.unit, d.per_serving, d.unconverted_lines
FROM   derived d
WHERE  NOT EXISTS (SELECT 1 FROM recipe_nutrition p
                   WHERE p.recipe_id = d.recipe_id AND p.nutrient_id = d.nutrient_id);

-- ---------------------------------------------------------------------------
-- What this member still needs today: target minus what's been logged.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_member_gap(p_member_id UUID, p_date DATE)
RETURNS TABLE (nutrient_id VARCHAR, target DECIMAL, consumed DECIMAL, gap DECIMAL, upper_day DECIMAL)
LANGUAGE sql STABLE AS $$
    SELECT t.nutrient_id,
           t.final_target_value,
           coalesce(l.consumed_value, 0),
           greatest(t.final_target_value - coalesce(l.consumed_value, 0), 0),
           b.upper_threshold_day
    FROM   profile_nutrient_targets t
    LEFT   JOIN nutrient_daily_log l
           ON l.member_id = t.member_id AND l.nutrient_id = t.nutrient_id AND l.log_date = p_date
    LEFT   JOIN household_members m ON m.member_id = t.member_id
    LEFT   JOIN profile_nutrient_baselines b
           ON b.category_id = m.category_id AND b.nutrient_id = t.nutrient_id
    WHERE  t.member_id = p_member_id
      AND  t.per = 'Day'
$$;

-- ---------------------------------------------------------------------------
-- Recipes this member must never see.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_blocked_recipes(p_member_id UUID)
RETURNS TABLE (recipe_id UUID, reason TEXT)
LANGUAGE sql STABLE AS $$
    -- household allergen present in the recipe
    SELECT DISTINCT ri.recipe_id,
           'contains ' || i.ingredient_name || ' (household allergen)'
    FROM   household_members m
    JOIN   user_allergen_map a  ON a.household_id = m.household_id AND a.is_household_hard_block
    JOIN   recipe_ingredients ri ON ri.ingredient_id = a.ingredient_id
    JOIN   ingredients i         ON i.ingredient_id = a.ingredient_id
    WHERE  m.member_id = p_member_id

    UNION

    -- breaks a hard rule that applies to this member
    SELECT DISTINCT rm.recipe_id,
           'breaks hard rule ' || nr.rule_id || ' (' || nr.rule_name || ')'
    FROM   household_members m
    JOIN   recipe_rules_map rm ON NOT rm.rule_satisfied
    JOIN   nutrient_rules nr   ON nr.rule_id = rm.rule_id AND nr.is_hard_constraint
    WHERE  m.member_id = p_member_id
      AND (nr.applies_to_category IS NULL OR nr.applies_to_category = m.category_id)
      AND (nr.applies_to_condition IS NULL OR nr.applies_to_condition IN (
              SELECT condition_code FROM member_conditions
              WHERE member_id = m.member_id AND condition_code IS NOT NULL))
$$;

-- ---------------------------------------------------------------------------
-- Single member. Returns ranked recipes with a score and the reasons.
--
-- score: mean over target nutrients of min(delivered / gap, 1), as a
-- percentage. Nutrients already at target contribute 0 (nothing to close).
-- Pushing a nutrient past its daily upper limit subtracts.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_recommend(
    p_member_id UUID,
    p_date      DATE    DEFAULT current_date,
    p_meal      TEXT    DEFAULT NULL,       -- Breakfast/Lunch/Dinner/Snack, NULL for any
    p_limit     INT     DEFAULT 10
)
RETURNS TABLE (
    recipe_id     UUID,
    recipe_name   VARCHAR,
    score         NUMERIC,
    top_reasons   JSONB,
    warnings      JSONB
)
LANGUAGE sql STABLE AS $$
    WITH gap AS (
        SELECT * FROM fn_member_gap(p_member_id, p_date)
    ),
    n_targets AS (
        SELECT count(*) AS n FROM gap
    ),
    contrib AS (
        SELECT v.recipe_id,
               v.nutrient_id,
               v.per_serving,
               g.gap,
               g.upper_day,
               g.consumed,
               CASE WHEN g.gap > 0 THEN least(v.per_serving / g.gap, 1) ELSE 0 END AS fill,
               CASE WHEN g.upper_day IS NOT NULL AND g.consumed + v.per_serving > g.upper_day
                    THEN 1 ELSE 0 END AS over_limit
        FROM   v_recipe_nutrients_per_serving v
        JOIN   gap g ON g.nutrient_id = v.nutrient_id
    ),
    scored AS (
        SELECT c.recipe_id,
               round(100.0 * sum(c.fill) / (SELECT n FROM n_targets) - 25.0 * sum(c.over_limit), 1) AS score,
               (SELECT jsonb_agg(jsonb_build_object(
                           'nutrient', x.nutrient_id,
                           'closes_pct', round(100 * x.fill),
                           'per_serving', round(x.per_serving, 1))
                        ORDER BY x.fill DESC)
                FROM (SELECT * FROM contrib c2 WHERE c2.recipe_id = c.recipe_id AND c2.fill > 0
                      ORDER BY c2.fill DESC LIMIT 3) x)                          AS top_reasons,
               (SELECT jsonb_agg(x.nutrient_id || ' over daily limit')
                FROM contrib x WHERE x.recipe_id = c.recipe_id AND x.over_limit = 1) AS warnings
        FROM   contrib c
        GROUP  BY c.recipe_id
    )
    SELECT s.recipe_id, r.recipe_name, s.score,
           coalesce(s.top_reasons, '[]'::jsonb),
           coalesce(s.warnings, '[]'::jsonb)
    FROM   scored s
    JOIN   recipes r ON r.recipe_id = s.recipe_id AND r.deleted_at IS NULL
    WHERE  s.recipe_id NOT IN (SELECT b.recipe_id FROM fn_blocked_recipes(p_member_id) b)
      AND (p_meal IS NULL OR r.meal_category = p_meal)
    ORDER  BY s.score DESC, r.recipe_name
    LIMIT  p_limit
$$;

-- ---------------------------------------------------------------------------
-- Whole household. Ranked by the lowest member score, so one person's
-- needs never get averaged away. A recipe blocked for anyone is out.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_recommend_household(
    p_household_id UUID,
    p_date         DATE DEFAULT current_date,
    p_meal         TEXT DEFAULT NULL,
    p_limit        INT  DEFAULT 10
)
RETURNS TABLE (
    recipe_id       UUID,
    recipe_name     VARCHAR,
    min_score       NUMERIC,
    avg_score       NUMERIC,
    per_member      JSONB
)
LANGUAGE sql STABLE AS $$
    WITH members AS (
        SELECT member_id, member_name
        FROM   household_members
        WHERE  household_id = p_household_id AND deleted_at IS NULL
    ),
    each AS (
        SELECT m.member_id, m.member_name, rec.*
        FROM   members m
        CROSS  JOIN LATERAL fn_recommend(m.member_id, p_date, p_meal, 1000) rec
    ),
    n_members AS (SELECT count(*) AS n FROM members)
    SELECT e.recipe_id,
           e.recipe_name,
           min(e.score),
           round(avg(e.score), 1),
           jsonb_object_agg(e.member_name, e.score)
    FROM   each e
    GROUP  BY e.recipe_id, e.recipe_name
    -- only recipes that passed every member's hard filter
    HAVING count(*) = (SELECT n FROM n_members)
    ORDER  BY min(e.score) DESC, avg(e.score) DESC
    LIMIT  p_limit
$$;

-- ---------------------------------------------------------------------------
-- Why was a recipe blocked or scored the way it was? For the UI and for
-- debugging.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_explain(p_member_id UUID, p_recipe_id UUID, p_date DATE DEFAULT current_date)
RETURNS TABLE (nutrient_id VARCHAR, target DECIMAL, consumed DECIMAL, gap DECIMAL, per_serving DECIMAL, closes_pct NUMERIC)
LANGUAGE sql STABLE AS $$
    SELECT g.nutrient_id, g.target, g.consumed, g.gap,
           round(coalesce(v.per_serving, 0), 2),
           CASE WHEN g.gap > 0 THEN round(100 * least(coalesce(v.per_serving, 0) / g.gap, 1)) ELSE 0 END
    FROM   fn_member_gap(p_member_id, p_date) g
    LEFT   JOIN v_recipe_nutrients_per_serving v
           ON v.recipe_id = p_recipe_id AND v.nutrient_id = g.nutrient_id
    ORDER  BY 6 DESC, g.nutrient_id
$$;
