-- 98_log.sql
-- Meal logging. One call records who ate a recipe, how much, and freezes the
-- nutrients as they were at that moment, then rolls them into each member's
-- daily totals so the home page gaps and the recommendations move.
--
--   select fn_log_meal(recipe_id, '[{"member_id": "...", "servings": 1}, ...]', 'Dinner');
--   select fn_log_meal(recipe_id, portions, 'Dinner', now(), overrides, log_id);
--   select fn_unlog_meal(log_id);
--
-- From the frontend:
--   supabase.rpc('fn_log_meal', { p_recipe_id, p_portions, p_meal_type, p_log_id })
--
-- p_portions: [{ "member_id": uuid, "servings": 1.5 }]   one entry per person who ate
-- p_overrides: same shape as fn_recipe_nutrition, for a recipe cooked with changes
-- p_log_id: client-generated UUID. Logging the same id twice is a no-op that
--           returns the first result, so a retried request (offline queue,
--           double tap) never double counts.
--
-- Writes:
--   profile_recipe_history  one row per member, nutrient_snapshot = what they
--                           ate ({nutrient_id: amount}), frozen; later recipe
--                           edits don't touch it
--   nutrient_daily_log      consumed_value += amount for each nutrient, that
--                           day; target_value is the member's target at log time
--
-- Returns { log_id, recipe_id, eaten_at, meal_type, members: [ { member_id, history_id, servings, energy } ] }

CREATE OR REPLACE FUNCTION fn_log_meal(
    p_recipe_id  UUID,
    p_portions   JSONB,
    p_meal_type  TEXT        DEFAULT NULL,
    p_eaten_at   TIMESTAMPTZ DEFAULT now(),
    p_overrides  JSONB       DEFAULT '[]'::jsonb,
    p_log_id     UUID        DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public AS $$
DECLARE
    v_log_id    UUID := coalesce(p_log_id, gen_ulid());
    v_nutrition JSONB;
    v_existing  JSONB;
    v_member    RECORD;
    v_hh        UUID;
    v_snapshot  JSONB;
    v_hist_id   UUID;
    v_members   JSONB := '[]'::jsonb;
    v_day       DATE := (p_eaten_at AT TIME ZONE 'UTC')::date;
    v_energy    NUMERIC;
BEGIN
    IF p_meal_type IS NOT NULL AND p_meal_type NOT IN ('Breakfast', 'Lunch', 'Dinner', 'Snack') THEN
        RAISE EXCEPTION 'meal_type must be Breakfast, Lunch, Dinner or Snack';
    END IF;
    IF jsonb_typeof(p_portions) <> 'array' OR jsonb_array_length(p_portions) = 0 THEN
        RAISE EXCEPTION 'p_portions must be a non-empty array of {member_id, servings}';
    END IF;

    -- already logged under this id: return what was written then
    SELECT jsonb_build_object(
               'log_id', v_log_id, 'recipe_id', p_recipe_id,
               'eaten_at', min(h.eaten_at), 'meal_type', min(h.meal_type), 'already_logged', true,
               'members', jsonb_agg(jsonb_build_object(
                   'member_id', h.member_id, 'history_id', h.history_id,
                   'servings', h.actual_servings, 'energy', (h.nutrient_snapshot ->> 'Energy')::numeric)))
    INTO   v_existing
    FROM   profile_recipe_history h
    WHERE  h.log_id = v_log_id;
    IF v_existing -> 'members' IS NOT NULL AND v_existing -> 'members' <> 'null'::jsonb THEN
        RETURN v_existing;
    END IF;

    v_nutrition := fn_recipe_nutrition(p_recipe_id, p_overrides);
    IF v_nutrition IS NULL THEN
        RAISE EXCEPTION 'recipe % not found', p_recipe_id;
    END IF;

    FOR v_member IN
        SELECT (e ->> 'member_id')::uuid AS member_id,
               coalesce((e ->> 'servings')::numeric, 1) AS servings
        FROM   jsonb_array_elements(p_portions) e
    LOOP
        IF v_member.servings <= 0 THEN
            RAISE EXCEPTION 'servings must be positive for member %', v_member.member_id;
        END IF;
        SELECT household_id INTO v_hh FROM household_members
        WHERE  member_id = v_member.member_id AND deleted_at IS NULL;
        IF v_hh IS NULL THEN
            RAISE EXCEPTION 'member % not found', v_member.member_id;
        END IF;

        -- what this person ate: per-serving values x their servings
        SELECT jsonb_object_agg(n ->> 'nutrient', round((n ->> 'per_serving')::numeric * v_member.servings, 4))
        INTO   v_snapshot
        FROM   jsonb_array_elements(v_nutrition -> 'nutrients') n
        WHERE  n ->> 'per_serving' IS NOT NULL;

        INSERT INTO profile_recipe_history
            (log_id, member_id, household_id, recipe_id, eaten_at, actual_servings, nutrient_snapshot,
             meal_type, week_number)
        VALUES
            (v_log_id, v_member.member_id, v_hh, p_recipe_id, p_eaten_at, v_member.servings, v_snapshot,
             p_meal_type, extract(week FROM p_eaten_at)::smallint)
        RETURNING history_id INTO v_hist_id;

        -- daily totals, target frozen from the member's current targets
        INSERT INTO nutrient_daily_log (member_id, log_date, nutrient_id, consumed_value, target_value)
        SELECT v_member.member_id, v_day, s.key, s.value::numeric,
               coalesce((SELECT t.final_target_value FROM profile_nutrient_targets t
                         WHERE t.member_id = v_member.member_id AND t.nutrient_id = s.key AND t.per = 'Day'), 0)
        FROM   jsonb_each_text(v_snapshot) s
        ON CONFLICT (member_id, log_date, nutrient_id) DO UPDATE
            SET consumed_value = nutrient_daily_log.consumed_value + EXCLUDED.consumed_value;

        v_energy := (v_snapshot ->> 'Energy')::numeric;
        v_members := v_members || jsonb_build_object(
            'member_id', v_member.member_id, 'history_id', v_hist_id,
            'servings', v_member.servings, 'energy', round(v_energy));
    END LOOP;

    RETURN jsonb_build_object(
        'log_id', v_log_id, 'recipe_id', p_recipe_id, 'eaten_at', p_eaten_at,
        'meal_type', p_meal_type, 'already_logged', false, 'members', v_members);
END $$;

-- ---------------------------------------------------------------------------
-- Undo one logged meal: remove the history rows and subtract their snapshot
-- from the daily totals. Returns how many member rows were removed.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_unlog_meal(p_log_id UUID)
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public AS $$
DECLARE
    v_row RECORD;
    v_n   INT := 0;
BEGIN
    FOR v_row IN
        SELECT history_id, member_id, eaten_at, nutrient_snapshot
        FROM   profile_recipe_history
        WHERE  log_id = p_log_id
    LOOP
        UPDATE nutrient_daily_log l
        SET    consumed_value = greatest(l.consumed_value - s.value::numeric, 0)
        FROM   jsonb_each_text(v_row.nutrient_snapshot) s
        WHERE  l.member_id = v_row.member_id
        AND    l.log_date  = (v_row.eaten_at AT TIME ZONE 'UTC')::date
        AND    l.nutrient_id = s.key;
        DELETE FROM profile_recipe_history WHERE history_id = v_row.history_id;
        v_n := v_n + 1;
    END LOOP;
    RETURN v_n;
END $$;

-- ---------------------------------------------------------------------------
-- What a member ate on a day, newest first. For the log screen.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_member_meals(p_member_id UUID, p_date DATE DEFAULT current_date)
RETURNS JSONB
LANGUAGE sql STABLE
SECURITY DEFINER SET search_path = public AS $$
    SELECT coalesce(jsonb_agg(jsonb_build_object(
               'log_id',     h.log_id,
               'history_id', h.history_id,
               'recipe_id',  h.recipe_id,
               'name',       r.recipe_name,
               'meal_type',  h.meal_type,
               'eaten_at',   h.eaten_at,
               'servings',   h.actual_servings,
               'energy',     round((h.nutrient_snapshot ->> 'Energy')::numeric),
               'protein',    round((h.nutrient_snapshot ->> 'Macro_Protein')::numeric, 1))
               ORDER BY h.eaten_at DESC), '[]'::jsonb)
    FROM   profile_recipe_history h
    LEFT   JOIN recipes r ON r.recipe_id = h.recipe_id
    WHERE  h.member_id = p_member_id
    AND    (h.eaten_at AT TIME ZONE 'UTC')::date = p_date
$$;

ALTER FUNCTION fn_log_meal(UUID, JSONB, TEXT, TIMESTAMPTZ, JSONB, UUID) SET jit = off;

-- Until sign-in lands the app has no identity, so the demo household logs as
-- anon. When auth is in: REVOKE EXECUTE ... FROM anon, and check inside
-- fn_log_meal that every member_id belongs to fn_user_member_ids().
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        GRANT EXECUTE ON FUNCTION fn_log_meal(UUID, JSONB, TEXT, TIMESTAMPTZ, JSONB, UUID) TO anon, authenticated;
        GRANT EXECUTE ON FUNCTION fn_unlog_meal(UUID) TO anon, authenticated;
        GRANT EXECUTE ON FUNCTION fn_member_meals(UUID, DATE) TO anon, authenticated;
    END IF;
END $$;
