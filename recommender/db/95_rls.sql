-- ============================================================================
--  Row Level Security
--
--  This file exists because of what is currently in the repository. The
--  shipped supabase-schema.sql grants the `anon` role SELECT, INSERT and
--  UPDATE on every row of weekly_plans with `USING (true)`. Any visitor to the
--  deployed site can read or overwrite any other user's meal plan. Once this
--  schema holds member_conditions — allergies, diagnoses, medications — the
--  same mistake is a HIPAA breach rather than an annoyance.
--
--  The model below is household-scoped: a user reaches exactly the rows
--  belonging to households they created, and nothing else. Reference data
--  (ingredients, recipes, rules) is world-readable but writable only by the
--  service role.
--
--  PORTABILITY: identity is resolved through current_app_user_id(), which reads
--  the Supabase JWT claim when present and otherwise falls back to a session
--  GUC. The same policies therefore work on Supabase and on plain Postgres
--  behind an application server.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Identity resolution
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.current_app_user_id()
RETURNS uuid
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v text;
BEGIN
    -- Supabase / PostgREST: the verified JWT payload
    BEGIN
        v := nullif(current_setting('request.jwt.claims', true), '')::json ->> 'sub';
        IF v IS NOT NULL THEN
            RETURN v::uuid;
        END IF;
    EXCEPTION WHEN OTHERS THEN
        NULL;
    END;

    -- Plain Postgres: SET LOCAL app.user_id = '<uuid>' on connection checkout
    BEGIN
        v := nullif(current_setting('app.user_id', true), '');
        IF v IS NOT NULL THEN
            RETURN v::uuid;
        END IF;
    EXCEPTION WHEN OTHERS THEN
        NULL;
    END;

    RETURN NULL;   -- unauthenticated: every policy below evaluates to false
END
$$;

COMMENT ON FUNCTION public.current_app_user_id() IS
  'Resolves the acting user from a Supabase JWT claim or the app.user_id GUC. NULL when unauthenticated.';

-- Households the current user owns. SECURITY DEFINER so the policy can read
-- households without recursing through households'' own RLS policy.
CREATE OR REPLACE FUNCTION public.fn_user_household_ids()
RETURNS SETOF uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT household_id
    FROM   public.households
    WHERE  created_by_user_id = public.current_app_user_id()
      AND  deleted_at IS NULL;
$$;

-- Members of those households.
CREATE OR REPLACE FUNCTION public.fn_user_member_ids()
RETURNS SETOF uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT m.member_id
    FROM   public.household_members m
    WHERE  m.household_id IN (SELECT public.fn_user_household_ids())
      AND  m.deleted_at IS NULL;
$$;

-- ---------------------------------------------------------------------------
-- User-scoped tables
-- ---------------------------------------------------------------------------
ALTER TABLE public.users                    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.households               ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.household_members        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.member_conditions        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_allergen_map        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profile_nutrient_targets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.household_recipe_plan    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profile_recipe_history   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.nutrient_daily_log       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sessions                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_log                ENABLE ROW LEVEL SECURITY;

-- A user sees only their own account row.
CREATE POLICY users_self ON public.users
    FOR ALL
    USING      (user_id = public.current_app_user_id())
    WITH CHECK (user_id = public.current_app_user_id());

CREATE POLICY households_own ON public.households
    FOR ALL
    USING      (created_by_user_id = public.current_app_user_id())
    WITH CHECK (created_by_user_id = public.current_app_user_id());

CREATE POLICY hm_own_household ON public.household_members
    FOR ALL
    USING      (household_id IN (SELECT public.fn_user_household_ids()))
    WITH CHECK (household_id IN (SELECT public.fn_user_household_ids()));

CREATE POLICY mc_own_members ON public.member_conditions
    FOR ALL
    USING      (member_id IN (SELECT public.fn_user_member_ids()))
    WITH CHECK (member_id IN (SELECT public.fn_user_member_ids()));

CREATE POLICY uam_own_household ON public.user_allergen_map
    FOR ALL
    USING      (household_id IN (SELECT public.fn_user_household_ids()))
    WITH CHECK (household_id IN (SELECT public.fn_user_household_ids()));

-- Targets are computed by a worker running as the service role, which bypasses
-- RLS. Clients get read-only access.
CREATE POLICY pnt_own_members_read ON public.profile_nutrient_targets
    FOR SELECT
    USING (member_id IN (SELECT public.fn_user_member_ids()));

CREATE POLICY hrp_own_household ON public.household_recipe_plan
    FOR ALL
    USING      (household_id IN (SELECT public.fn_user_household_ids()))
    WITH CHECK (household_id IN (SELECT public.fn_user_household_ids()));

CREATE POLICY prh_own_household ON public.profile_recipe_history
    FOR ALL
    USING      (household_id IN (SELECT public.fn_user_household_ids()))
    WITH CHECK (household_id IN (SELECT public.fn_user_household_ids()));

CREATE POLICY ndl_own_members ON public.nutrient_daily_log
    FOR ALL
    USING      (member_id IN (SELECT public.fn_user_member_ids()))
    WITH CHECK (member_id IN (SELECT public.fn_user_member_ids()));

CREATE POLICY sessions_own ON public.sessions
    FOR ALL
    USING      (user_id = public.current_app_user_id())
    WITH CHECK (user_id = public.current_app_user_id());

-- Users may read their own audit history and nothing else. No INSERT policy:
-- audit rows are written by a SECURITY DEFINER trigger, never by a client.
CREATE POLICY audit_own_read ON public.audit_log
    FOR SELECT
    USING (user_id = public.current_app_user_id());

-- ---------------------------------------------------------------------------
-- Reference data — world-readable, service-role writable
--
-- RLS is enabled with a permissive SELECT policy rather than left disabled, so
-- that "which tables are protected?" has one answer: all of them. A table with
-- RLS off is indistinguishable from a table someone forgot.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'conditions', 'condition_attributes', 'nutrient_rules', 'nutrient_modifiers',
        'documents', 'categories', 'nutrients_master', 'profile_nutrient_baselines',
        'data_sources', 'ingredients', 'ingredient_nutrition', 'ingredient_measures', 'ingredient_source_map',
        'usda_nutrient_ref', 'ingredient_attributes',
        'ingredient_synergy_pairs', 'ingredient_bioavailability',
        'ingredient_substitutions', 'glycemic_index_data',
        'cultural_categories', 'recipes', 'recipe_ingredients', 'recipe_steps',
        'recipe_videos', 'recipe_rules_map'
    ]
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR SELECT USING (true)',
            t || '_public_read', t);
    END LOOP;
END
$$;

-- Soft-deleted recipes must not surface even though recipes is world-readable.
DROP POLICY recipes_public_read ON public.recipes;
CREATE POLICY recipes_public_read ON public.recipes
    FOR SELECT USING (deleted_at IS NULL);

-- Supabase: the policies above decide which rows, but the API roles also
-- need the table-level grant on the public reference tables. No-op elsewhere.
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        GRANT SELECT ON public.recipes, public.recipe_steps, public.recipe_ingredients, public.ingredients,
                        public.ingredient_measures, public.data_sources, public.nutrients_master,
                        public.ingredient_nutrition, public.ingredient_source_map
        TO anon, authenticated;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- WHAT IS DELIBERATELY ABSENT
--
--   * No policy grants `anon` any write anywhere. Writes require an
--     authenticated identity or the service role.
--   * No policy uses USING (true) on a user-data table.
--   * Workers (target recompute, embedding, aggregation) must connect as the
--     service role / table owner, which bypasses RLS by design. Never hand a
--     service-role key to the browser.
--
-- Verify after deployment:
--     SELECT relname, relrowsecurity
--     FROM   pg_class
--     WHERE  relnamespace = 'public'::regnamespace AND relkind = 'r'
--       AND  NOT relrowsecurity;      -- must return zero rows
-- ---------------------------------------------------------------------------
