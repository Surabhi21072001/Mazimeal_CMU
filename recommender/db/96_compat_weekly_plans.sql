-- ============================================================================
--  Compatibility · weekly_plans
--
--  The deployed app persists its entire planner as one JSONB blob keyed by a
--  client-derived string:
--      weekly_plans (user_key text primary key, planner_state jsonb, updated_at)
--
--  That table is not part of the workbook and is superseded by
--  household_recipe_plan. It cannot simply be dropped — the live MVP writes to
--  it on every planner edit — so this file does three things:
--
--    1. Creates it if absent, so a fresh database can run the current frontend.
--    2. Replaces the anon-write RLS policies with something not open to the
--       public internet.
--    3. Ships the migration that lifts blobs into household_recipe_plan.
--
--  Retire this file once the frontend writes household_recipe_plan directly.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.weekly_plans (
    user_key      TEXT        PRIMARY KEY,
    planner_state JSONB       NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.weekly_plans IS
  'LEGACY. Superseded by household_recipe_plan. Do not add columns; migrate off it.';

-- ---------------------------------------------------------------------------
-- Remove the open policies shipped in supabase-schema.sql
--
-- The originals were:
--   FOR SELECT TO anon USING (true)
--   FOR INSERT TO anon WITH CHECK (true)
--   FOR UPDATE TO anon USING (true) WITH CHECK (true)
--
-- `true` means every row, for everyone, unauthenticated. Any visitor could
-- enumerate and overwrite every user's planner.
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "Allow anon read weekly plans"   ON public.weekly_plans;
DROP POLICY IF EXISTS "Allow anon write weekly plans"  ON public.weekly_plans;
DROP POLICY IF EXISTS "Allow anon update weekly plans" ON public.weekly_plans;

ALTER TABLE public.weekly_plans ENABLE ROW LEVEL SECURITY;

-- Interim policy: a row is reachable only by the user whose id matches its key.
--
-- This is a stopgap, not a design. user_key is currently derived client-side
-- from a name typed into a login form that validates nothing, so it is a claim,
-- not an identity. The real fix is authentication; until then this at least
-- stops one user from reading another's plan by guessing.
CREATE POLICY weekly_plans_own ON public.weekly_plans
    FOR ALL
    USING      (user_key = public.current_app_user_id()::text)
    WITH CHECK (user_key = public.current_app_user_id()::text);

-- ---------------------------------------------------------------------------
-- fn_migrate_weekly_plan(user_key, household_id) -> rows inserted
--
-- Expands one planner blob into household_recipe_plan rows. The blob shape the
-- frontend writes is:
--
--   { "anchorDate": "2026-08-17T00:00:00.000Z",
--     "selectedDayIndex": 0,
--     "days": [ { "meals": { "breakfast": {...}, "lunch": {...},
--                            "dinner": {...},   "snack": {...} } }, ... ] }
--
-- Each day's index is an offset from anchorDate. Meals carry a name but no
-- stable recipe id — the frontend's recipes are hardcoded literals — so this
-- resolves by name against public.recipes and reports what it could not match
-- rather than inventing rows.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.fn_migrate_weekly_plan(
    p_user_key     text,
    p_household_id uuid
)
RETURNS TABLE (inserted int, unmatched text[])
LANGUAGE plpgsql
AS $$
DECLARE
    v_state    jsonb;
    v_anchor   date;
    v_day      jsonb;
    v_idx      int;
    v_meal_key text;
    v_meal     jsonb;
    v_name     text;
    v_recipe   uuid;
    v_inserted int   := 0;
    v_missing  text[] := ARRAY[]::text[];
BEGIN
    SELECT planner_state INTO v_state
    FROM   public.weekly_plans
    WHERE  user_key = p_user_key;

    IF v_state IS NULL THEN
        RAISE EXCEPTION 'No weekly_plans row for user_key %', p_user_key;
    END IF;

    v_anchor := (v_state ->> 'anchorDate')::timestamptz::date;
    v_idx    := 0;

    FOR v_day IN SELECT * FROM jsonb_array_elements(v_state -> 'days') LOOP
        FOREACH v_meal_key IN ARRAY ARRAY['breakfast', 'lunch', 'dinner', 'snack'] LOOP
            v_meal := v_day -> 'meals' -> v_meal_key;
            CONTINUE WHEN v_meal IS NULL OR jsonb_typeof(v_meal) <> 'object';

            v_name := COALESCE(v_meal ->> 'name', v_meal ->> 'title');
            CONTINUE WHEN v_name IS NULL;

            SELECT r.recipe_id INTO v_recipe
            FROM   public.recipes r
            WHERE  lower(r.recipe_name) = lower(v_name)
              AND  r.deleted_at IS NULL
            LIMIT  1;

            IF v_recipe IS NULL THEN
                v_missing := v_missing || v_name;
                CONTINUE;
            END IF;

            INSERT INTO public.household_recipe_plan
                (household_id, recipe_id, planned_date, meal_type, is_ai_suggested, status)
            VALUES
                (p_household_id,
                 v_recipe,
                 v_anchor + v_idx,
                 initcap(v_meal_key),
                 false,
                 'planned');

            v_inserted := v_inserted + 1;
        END LOOP;

        v_idx := v_idx + 1;
    END LOOP;

    inserted  := v_inserted;
    unmatched := v_missing;
    RETURN NEXT;
END
$$;

COMMENT ON FUNCTION public.fn_migrate_weekly_plan(text, uuid) IS
  'Expands a legacy planner blob into household_recipe_plan rows. Returns names it could not resolve.';
