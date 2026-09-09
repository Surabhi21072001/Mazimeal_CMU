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
-- ingredient quantities.
--
-- Derived values are scaled so the recipe's derived calories match its
-- published calories. Imported recipes have quantities without units, so the
-- gram estimate per line is rough; the proportions are usually right but the
-- total isn't. Anchoring to published energy fixes the total. The factor is
-- clamped to 0.25..4 so one bad line can't blow up a recipe.
--
-- Materialized: the recommender reads it many times per page and computing
-- it costs a few seconds. Refresh after loading recipes or ingredient
-- nutrition: select fn_refresh_recipe_nutrients();  The seed files do it.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_recipe_nutrients_per_serving;
DROP MATERIALIZED VIEW IF EXISTS mv_recipe_nutrients;
CREATE MATERIALIZED VIEW mv_recipe_nutrients AS
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
),
scale AS (
    SELECT d.recipe_id,
           least(greatest(p.per_serving / nullif(d.per_serving, 0), 0.25), 4) AS factor
    FROM   derived d
    JOIN   recipe_nutrition p ON p.recipe_id = d.recipe_id AND p.nutrient_id = 'Energy'
    WHERE  d.nutrient_id = 'Energy' AND p.per_serving > 0
)
-- published values first
SELECT p.recipe_id, p.nutrient_id, p.unit, p.per_serving, 0 AS unconverted_lines
FROM   recipe_nutrition p
JOIN   recipes r ON r.recipe_id = p.recipe_id AND r.deleted_at IS NULL
UNION ALL
-- then anything derived that the published data doesn't cover
SELECT d.recipe_id, d.nutrient_id, d.unit,
       d.per_serving * coalesce(s.factor, 1),
       d.unconverted_lines
FROM   derived d
LEFT   JOIN scale s ON s.recipe_id = d.recipe_id
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
    IF EXISTS (SELECT 1 FROM pg_class WHERE relname = 'mv_recipe_nutrients' AND relispopulated) THEN
        REFRESH MATERIALIZED VIEW CONCURRENTLY mv_recipe_nutrients;
    ELSE
        REFRESH MATERIALIZED VIEW mv_recipe_nutrients;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- What this member still needs today: target minus what's been logged.
-- ---------------------------------------------------------------------------
DROP FUNCTION IF EXISTS fn_member_gap(UUID, DATE) CASCADE;
CREATE FUNCTION fn_member_gap(p_member_id UUID, p_date DATE)
RETURNS TABLE (nutrient_id VARCHAR, target DECIMAL, consumed DECIMAL, gap DECIMAL, upper_day DECIMAL,
               adjusted BOOLEAN)   -- a modifier (condition, goal, activity) changed this target
LANGUAGE sql STABLE AS $$
    SELECT t.nutrient_id,
           t.final_target_value,
           coalesce(l.consumed_value, 0),
           greatest(t.final_target_value - coalesce(l.consumed_value, 0), 0),
           b.upper_threshold_day,
           coalesce(t.applied_rules_csv, '') <> ''
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
-- One meal is expected to cover a share of the day's remaining gap:
-- Breakfast 25%, Lunch 30%, Dinner 35%, Snack 10% (35% when no meal given).
--
-- score: mean over target nutrients of min(delivered / (gap * share), 1), as a
-- percentage. Energy is the exception: it scores highest when it matches the
-- share and drops off in both directions, so a 1,500 kcal lunch doesn't win.
-- Nutrients already at target contribute 0. Pushing a nutrient past its daily
-- upper limit subtracts.
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
    WITH share AS (
        SELECT CASE p_meal WHEN 'Breakfast' THEN 0.25 WHEN 'Lunch' THEN 0.30
                           WHEN 'Snack' THEN 0.10 ELSE 0.35 END AS s
    ),
    gap AS (
        SELECT g.nutrient_id, g.target, g.consumed, g.upper_day,
               g.gap * (SELECT s FROM share) AS gap
        FROM   fn_member_gap(p_member_id, p_date) g
    ),
    n_targets AS (
        SELECT count(*) AS n FROM gap WHERE target > 0   -- limit-only nutrients don't count
    ),
    contrib AS (
        SELECT v.recipe_id,
               v.nutrient_id,
               v.per_serving,
               g.gap,
               g.upper_day,
               g.consumed,
               CASE WHEN g.gap <= 0 THEN 0
                    WHEN v.nutrient_id = 'Energy'
                         THEN greatest(1 - abs(v.per_serving - g.gap) / g.gap, 0)
                    ELSE least(v.per_serving / g.gap, 1) END AS fill,
               CASE WHEN g.upper_day IS NOT NULL AND g.consumed + v.per_serving > g.upper_day
                    THEN 1 ELSE 0 END AS over_limit
        FROM   v_recipe_nutrients_per_serving v
        JOIN   gap g ON g.nutrient_id = v.nutrient_id
    ),
    ranked AS (
        SELECT c.*, row_number() OVER (PARTITION BY c.recipe_id ORDER BY c.fill DESC) AS rn
        FROM   contrib c
    ),
    scored AS (
        SELECT c.recipe_id,
               round(100.0 * sum(c.fill) / (SELECT n FROM n_targets) - 25.0 * sum(c.over_limit), 1) AS score,
               jsonb_agg(jsonb_build_object(
                   'nutrient', c.nutrient_id,
                   'closes_pct', round(100 * c.fill),
                   'per_serving', round(c.per_serving, 1)) ORDER BY c.fill DESC)
                   FILTER (WHERE c.rn <= 3 AND c.fill > 0)                          AS top_reasons,
               jsonb_agg(c.nutrient_id || ' over daily limit') FILTER (WHERE c.over_limit = 1) AS warnings
        FROM   ranked c
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
DROP FUNCTION IF EXISTS fn_recommend_household(UUID, DATE, TEXT, INT);
CREATE FUNCTION fn_recommend_household(
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
    per_member      JSONB,
    top_reasons     JSONB       -- reasons for the member who needs it most
)
LANGUAGE sql STABLE AS $$
    WITH members AS (
        SELECT member_id, member_name
        FROM   household_members
        WHERE  household_id = p_household_id AND deleted_at IS NULL
    ),
    -- MATERIALIZED: score each member once, not once per output row
    each AS MATERIALIZED (
        SELECT m.member_name, rec.*,
               row_number() OVER (PARTITION BY rec.recipe_id ORDER BY rec.score) AS weakest
        FROM   members m
        CROSS  JOIN LATERAL fn_recommend(m.member_id, p_date, p_meal, 1000) rec
    ),
    n_members AS (SELECT count(*) AS n FROM members)
    SELECT e.recipe_id,
           e.recipe_name,
           min(e.score),
           round(avg(e.score), 1),
           jsonb_object_agg(e.member_name, e.score),
           (jsonb_agg(jsonb_build_object('member', e.member_name, 'reasons', e.top_reasons) ORDER BY e.weakest)) -> 0
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
DROP FUNCTION IF EXISTS fn_explain(UUID, UUID, DATE);
CREATE OR REPLACE FUNCTION fn_explain(
    p_member_id UUID, p_recipe_id UUID, p_date DATE DEFAULT current_date, p_meal TEXT DEFAULT NULL
)
RETURNS TABLE (nutrient_id VARCHAR, target DECIMAL, consumed DECIMAL, meal_gap DECIMAL, per_serving DECIMAL, closes_pct NUMERIC)
LANGUAGE sql STABLE AS $$
    WITH share AS (
        SELECT CASE p_meal WHEN 'Breakfast' THEN 0.25 WHEN 'Lunch' THEN 0.30
                           WHEN 'Snack' THEN 0.10 ELSE 0.35 END AS s
    )
    SELECT g.nutrient_id, g.target, g.consumed,
           round(g.gap * (SELECT s FROM share), 1),
           round(coalesce(v.per_serving, 0), 2),
           CASE WHEN g.gap <= 0 THEN 0
                WHEN g.nutrient_id = 'Energy'
                     THEN round(100 * greatest(1 - abs(coalesce(v.per_serving, 0) - g.gap * (SELECT s FROM share))
                                                   / (g.gap * (SELECT s FROM share)), 0))
                ELSE round(100 * least(coalesce(v.per_serving, 0) / (g.gap * (SELECT s FROM share)), 1)) END
    FROM   fn_member_gap(p_member_id, p_date) g
    LEFT   JOIN v_recipe_nutrients_per_serving v
           ON v.recipe_id = p_recipe_id AND v.nutrient_id = g.nutrient_id
    ORDER  BY 6 DESC, g.nutrient_id
$$;

-- JIT compiles these for seconds on a partitioned schema and gains nothing.
ALTER FUNCTION fn_recommend(UUID, DATE, TEXT, INT) SET jit = off;
ALTER FUNCTION fn_recommend_household(UUID, DATE, TEXT, INT) SET jit = off;
ALTER FUNCTION fn_explain(UUID, UUID, DATE, TEXT) SET jit = off;
