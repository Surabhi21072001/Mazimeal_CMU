-- 98_home.sql
-- Everything the home page needs in one call, as JSON.
--
--   select fn_home(household_id);            -- today
--   select fn_home(household_id, '2026-09-08', 3);
--
-- From the frontend: supabase.rpc('fn_home', { p_household_id: ... })
--
-- {
--   household: { id, name },
--   date: '2026-09-08',
--   members: [ { id, name, gaps: [ { nutrient, label, unit, target, consumed, gap, adjusted, pct_open } ] } ],
--   picks:   { Breakfast: [ { recipe_id, name, min_score, avg_score, per_member, top_reasons,
--                             calories, prep_min, cook_min, tags } ], Lunch: [...], ... },
--   blocked: [ { recipe_id, name, reason } ]
-- }

CREATE OR REPLACE FUNCTION fn_home(
    p_household_id UUID,
    p_date         DATE DEFAULT current_date,
    p_per_slot     INT  DEFAULT 3
)
RETURNS JSONB
LANGUAGE sql STABLE AS $$
    WITH hh AS (
        SELECT household_id, household_name
        FROM   households
        WHERE  household_id = p_household_id AND deleted_at IS NULL
    ),
    members AS (
        SELECT member_id, member_name
        FROM   household_members
        WHERE  household_id = p_household_id AND deleted_at IS NULL
        ORDER  BY member_name
    ),
    member_json AS (
        SELECT jsonb_agg(jsonb_build_object(
                   'id',   m.member_id,
                   'name', m.member_name,
                   'gaps', (SELECT jsonb_agg(jsonb_build_object(
                                       'nutrient', g.nutrient_id,
                                       'label',    n.nutrient_name,
                                       'unit',     n.default_unit,
                                       'target',   round(g.target, 1),
                                       'consumed', round(g.consumed, 1),
                                       'gap',      round(g.gap, 1),
                                       'adjusted', g.adjusted,
                                       'pct_open', CASE WHEN g.target > 0
                                                        THEN round(100 * g.gap / g.target) ELSE 0 END)
                                   -- most open first; among ties, targets a modifier raised
                                   ORDER BY CASE WHEN g.target > 0 THEN g.gap / g.target ELSE 0 END DESC,
                                            g.adjusted DESC, g.nutrient_id)
                            FROM fn_member_gap(m.member_id, p_date) g
                            LEFT JOIN nutrients_master n ON n.nutrient_id = g.nutrient_id)
               ) ORDER BY m.member_name) AS j
        FROM members m
    ),
    slots AS (
        SELECT unnest(ARRAY['Breakfast', 'Lunch', 'Dinner', 'Snack']) AS slot
    ),
    picks AS (
        SELECT s.slot,
               jsonb_agg(jsonb_build_object(
                   'recipe_id',   p.recipe_id,
                   'name',        p.recipe_name,
                   'min_score',   p.min_score,
                   'avg_score',   p.avg_score,
                   'per_member',  p.per_member,
                   'top_reasons', p.top_reasons,
                   'calories',    round(coalesce(r.calories_per_serving,
                                      (SELECT v.per_serving FROM v_recipe_nutrients_per_serving v
                                       WHERE v.recipe_id = r.recipe_id AND v.nutrient_id = 'Energy'))),
                   'prep_min',    r.prep_time_min,
                   'cook_min',    r.cook_time_min,
                   'tags',        coalesce(to_jsonb(r.dietary_tags), '[]'::jsonb))
                   ORDER BY p.min_score DESC, p.avg_score DESC) AS j
        FROM   slots s
        CROSS  JOIN LATERAL fn_recommend_household(p_household_id, p_date, s.slot, p_per_slot) p
        JOIN   recipes r ON r.recipe_id = p.recipe_id
        GROUP  BY s.slot
    ),
    blocked AS (
        SELECT jsonb_agg(jsonb_build_object(
                   'recipe_id', b.recipe_id,
                   'name',      r.recipe_name,
                   'reason',    b.reason)
                   ORDER BY r.recipe_name) AS j
        FROM  (SELECT DISTINCT b.recipe_id, b.reason
               FROM   members m
               CROSS  JOIN LATERAL fn_blocked_recipes(m.member_id) b) b
        JOIN   recipes r ON r.recipe_id = b.recipe_id AND r.deleted_at IS NULL
    )
    SELECT jsonb_build_object(
        'household', (SELECT jsonb_build_object('id', household_id, 'name', household_name) FROM hh),
        'date',      p_date,
        'members',   coalesce((SELECT j FROM member_json), '[]'::jsonb),
        'picks',     coalesce((SELECT jsonb_object_agg(slot, j) FROM picks), '{}'::jsonb),
        'blocked',   coalesce((SELECT j FROM blocked), '[]'::jsonb)
    )
$$;

-- JIT compiles this query for seconds on a partitioned schema and gains nothing.
ALTER FUNCTION fn_home(UUID, DATE, INT) SET jit = off;
