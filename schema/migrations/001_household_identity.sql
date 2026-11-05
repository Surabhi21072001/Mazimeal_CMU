-- ============================================================================
--  001 · Identity, households and member profiles
--
--  Why this file exists instead of recommender/db/install.sql
--  ----------------------------------------------------------
--  The installer creates 54 tables, and 10 of them - recipes,
--  recipe_ingredients, recipe_nutrition, recipe_steps, ingredients,
--  ingredient_nutrition, ingredient_measures, ingredient_source_map,
--  data_sources, nutrient_rules - are tables this database already has, with
--  the seed data the whole app reads. It runs in one transaction and is
--  documented to fail on the first duplicate object, so running it here
--  installs nothing. It also needs psql variables (:pk_household_members) that
--  only its own 00_extensions.sql sets.
--
--  So this takes the three tables the sign-in flow actually writes, in their
--  MVP (unpartitioned) form, with the identity functions and row-level
--  security that make them safe to expose to a browser. Column definitions are
--  copied from recommender/db/20_household_profile.sql; the PHI comments and
--  the HASH-partitioned primary keys are the only things left behind.
--
--  Additive only: nothing here drops or alters an existing object. Safe to
--  re-run.
--
--      psql "$SUPABASE_DB_URL" -f schema/migrations/001_household_identity.sql
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- gen_ulid() - time-ordered UUIDv7, from recommender/db/00_extensions.sql.
-- Every surrogate key below defaults to it: sequential inserts, no B-tree hot
-- spot. Random bytes come from gen_random_uuid() rather than pgcrypto, which
-- is not visible to Supabase's roles.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.gen_ulid()
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
  ts_millis  bigint;
  uuid_bytes bytea;
BEGIN
  BEGIN
    RETURN uuidv7();          -- Postgres 18+
  EXCEPTION WHEN undefined_function THEN
    NULL;
  END;

  ts_millis  := floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint;
  uuid_bytes := substring(int8send(ts_millis) FROM 3 FOR 6)
             || substring(uuid_send(gen_random_uuid()) FROM 1 FOR 10);
  uuid_bytes := set_byte(uuid_bytes, 6, (get_byte(uuid_bytes, 6) & 15) | 112);
  uuid_bytes := set_byte(uuid_bytes, 8, (get_byte(uuid_bytes, 8) & 63) | 128);
  RETURN encode(uuid_bytes, 'hex')::uuid;
END
$$;

COMMENT ON FUNCTION public.gen_ulid() IS
  'Time-ordered UUIDv7. Sequential inserts, no B-tree hot spots, safe across shards.';


-- ---------------------------------------------------------------------------
-- households
--
-- created_by_user_id is the Supabase auth user id (auth.users.id). No foreign
-- key to it: auth lives in another schema that this role does not own, and
-- the app already treats a missing user as a failed sign-in.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.households (
    household_id        UUID          NOT NULL DEFAULT public.gen_ulid(),
    created_by_user_id  UUID          NOT NULL,
    household_name      VARCHAR(150),
    country_region      VARCHAR(10)   NOT NULL DEFAULT 'US',
    has_pets            BOOLEAN       NOT NULL DEFAULT FALSE,
    pets_receive_scraps BOOLEAN,
    subscription_tier   VARCHAR(20)   NOT NULL DEFAULT 'free',
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ,

    CONSTRAINT pk_households PRIMARY KEY (household_id),
    CONSTRAINT ck_hh_country CHECK (country_region ~ '^[A-Z]{2}$'),
    CONSTRAINT ck_hh_tier    CHECK (subscription_tier IN ('free', 'premium', 'clinical')),
    CONSTRAINT ck_hh_scraps_needs_pets
        CHECK (pets_receive_scraps IS NULL OR has_pets)
);

COMMENT ON COLUMN public.households.created_by_user_id   IS 'auth.users.id of the account that signed up. Every RLS policy here resolves through it.';
COMMENT ON COLUMN public.households.country_region       IS 'ISO 3166-1 alpha-2. Drives region-specific dietary defaults.';
COMMENT ON COLUMN public.households.pets_receive_scraps  IS 'Escalates pet-toxic ingredient warnings (see ingredients.is_pet_toxic).';


-- ---------------------------------------------------------------------------
-- household_members
--
-- The table the onboarding questionnaire writes, field for field. category_id
-- is kept as a plain column: the categories reference table it points at is
-- part of the recommender schema this database has not loaded, and a foreign
-- key to a missing table would block every signup.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.household_members (
    member_id           UUID          NOT NULL DEFAULT public.gen_ulid(),
    household_id        UUID          NOT NULL,
    member_name         VARCHAR(100)  NOT NULL,
    age                 SMALLINT,
    sex_at_birth        CHAR(1),
    weight_kg           DECIMAL(5,2),
    height_cm           DECIMAL(5,2),
    activity_level      VARCHAR(20),
    life_stage          VARCHAR(80),
    pregnancy_detail    VARCHAR(50),
    lifestyle_dietary   TEXT[],
    goal                VARCHAR(80),
    food_preference_csv TEXT[],
    meal_spacing_pref   VARCHAR(80),
    category_id         VARCHAR(10),
    profile_email       VARCHAR(255),
    phone               VARCHAR(20),
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ,
    deleted_at          TIMESTAMPTZ,

    CONSTRAINT pk_household_members PRIMARY KEY (member_id),
    CONSTRAINT fk_hm_household FOREIGN KEY (household_id)
        REFERENCES public.households (household_id) ON DELETE CASCADE,
    CONSTRAINT ck_hm_age      CHECK (age IS NULL OR age BETWEEN 0 AND 130),
    CONSTRAINT ck_hm_sex      CHECK (sex_at_birth IS NULL OR sex_at_birth IN ('M', 'F')),
    CONSTRAINT ck_hm_weight   CHECK (weight_kg IS NULL OR weight_kg BETWEEN 0.5 AND 500),
    CONSTRAINT ck_hm_height   CHECK (height_cm IS NULL OR height_cm BETWEEN 20 AND 280),
    CONSTRAINT ck_hm_activity CHECK (activity_level IS NULL OR activity_level IN
                                ('sedentary', 'lightly_active', 'moderate', 'very_active', 'athlete')),
    CONSTRAINT ck_hm_goal     CHECK (goal IS NULL OR goal IN
                                ('weight_loss', 'muscle_gain', 'maintenance', 'wellness')),
    CONSTRAINT ck_hm_spacing  CHECK (meal_spacing_pref IS NULL OR meal_spacing_pref IN
                                ('3_meals', 'intermittent_fasting', '5_small')),
    CONSTRAINT ck_hm_email_lc CHECK (profile_email IS NULL OR profile_email = lower(profile_email)),
    CONSTRAINT ck_hm_phone_e164 CHECK (phone IS NULL OR phone ~ '^\+[1-9][0-9]{6,14}$'),
    CONSTRAINT ck_hm_pregnancy CHECK (pregnancy_detail IS NULL OR life_stage IS NOT NULL)
);

COMMENT ON COLUMN public.household_members.life_stage          IS 'PHI: pregnancy_wk_N / lactating / menopause.';
COMMENT ON COLUMN public.household_members.pregnancy_detail    IS 'PHI: trimester or week number.';
COMMENT ON COLUMN public.household_members.phone               IS 'PHI: E.164 format.';
COMMENT ON COLUMN public.household_members.food_preference_csv IS 'Cuisine preferences. Name kept from the workbook for traceability; the type is TEXT[], not CSV.';
COMMENT ON COLUMN public.household_members.category_id         IS 'System-derived C001-C021 from age + sex_at_birth. No FK: the categories table is not loaded here.';

CREATE INDEX IF NOT EXISTS ix_hm_household ON public.household_members (household_id)
    WHERE deleted_at IS NULL;


-- ---------------------------------------------------------------------------
-- member_conditions - every row is PHI
--
-- Allergies, diagnoses, medications and supplements share one table and are
-- told apart by condition_type. The sign-up flow writes allergies here.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.member_conditions (
    record_id      UUID          NOT NULL DEFAULT public.gen_ulid(),
    member_id      UUID          NOT NULL,
    condition_type VARCHAR(30)   NOT NULL,
    condition_code VARCHAR(20),
    value_text     VARCHAR(200),
    severity       VARCHAR(20),
    hipaa_flag     BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),

    CONSTRAINT pk_member_conditions PRIMARY KEY (record_id),
    CONSTRAINT fk_mc_member FOREIGN KEY (member_id)
        REFERENCES public.household_members (member_id) ON DELETE CASCADE,
    CONSTRAINT ck_mc_type     CHECK (condition_type IN ('condition', 'allergy', 'medication', 'supplement')),
    CONSTRAINT ck_mc_severity CHECK (severity IS NULL OR severity IN
                                ('mild', 'moderate', 'severe', 'anaphylactic')),
    CONSTRAINT ck_mc_has_subject CHECK (condition_code IS NOT NULL OR value_text IS NOT NULL)
);

COMMENT ON TABLE  public.member_conditions            IS 'PHI TABLE. Every row is protected health information.';
COMMENT ON COLUMN public.member_conditions.value_text IS 'PHI: free text (medication name, allergy detail).';

CREATE INDEX IF NOT EXISTS ix_mc_member ON public.member_conditions (member_id, condition_type);


-- ---------------------------------------------------------------------------
-- Identity resolution, from recommender/db/95_rls.sql
--
-- Every policy below asks "who is calling?" through this one function, which
-- reads the verified Supabase JWT claim and otherwise falls back to a session
-- GUC - so the same policies hold whether the caller is the browser talking
-- to PostgREST or our own API behind a connection pool. Unauthenticated
-- resolves to NULL, and then every policy is false rather than permissive.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.current_app_user_id()
RETURNS uuid
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v text;
BEGIN
    BEGIN
        v := nullif(current_setting('request.jwt.claims', true), '')::json ->> 'sub';
        IF v IS NOT NULL THEN
            RETURN v::uuid;
        END IF;
    EXCEPTION WHEN OTHERS THEN
        NULL;
    END;

    BEGIN
        v := nullif(current_setting('app.user_id', true), '');
        IF v IS NOT NULL THEN
            RETURN v::uuid;
        END IF;
    EXCEPTION WHEN OTHERS THEN
        NULL;
    END;

    RETURN NULL;
END
$$;

COMMENT ON FUNCTION public.current_app_user_id() IS
  'Resolves the acting user from a Supabase JWT claim or the app.user_id GUC. NULL when unauthenticated.';

-- SECURITY DEFINER so a policy on households can read households without
-- recursing through that same policy.
CREATE OR REPLACE FUNCTION public.fn_user_household_ids()
RETURNS SETOF uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT household_id FROM public.households
    WHERE  created_by_user_id = public.current_app_user_id()
      AND  deleted_at IS NULL;
$$;

CREATE OR REPLACE FUNCTION public.fn_user_member_ids()
RETURNS SETOF uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT m.member_id FROM public.household_members m
    WHERE  m.household_id IN (SELECT public.fn_user_household_ids())
      AND  m.deleted_at IS NULL;
$$;


-- ---------------------------------------------------------------------------
-- Row-level security
--
-- These three tables hold names, ages, weights and allergies, and the browser
-- reaches them with an anon key. Without RLS that key reads every household in
-- the project. A user sees exactly the households they created.
-- ---------------------------------------------------------------------------
ALTER TABLE public.households         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.household_members  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.member_conditions  ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS households_own ON public.households;
CREATE POLICY households_own ON public.households
    FOR ALL
    USING      (created_by_user_id = public.current_app_user_id())
    WITH CHECK (created_by_user_id = public.current_app_user_id());

DROP POLICY IF EXISTS hm_own_household ON public.household_members;
CREATE POLICY hm_own_household ON public.household_members
    FOR ALL
    USING      (household_id IN (SELECT public.fn_user_household_ids()))
    WITH CHECK (household_id IN (SELECT public.fn_user_household_ids()));

DROP POLICY IF EXISTS mc_own_members ON public.member_conditions;
CREATE POLICY mc_own_members ON public.member_conditions
    FOR ALL
    USING      (member_id IN (SELECT public.fn_user_member_ids()))
    WITH CHECK (member_id IN (SELECT public.fn_user_member_ids()));


-- ---------------------------------------------------------------------------
-- Supabase table grants
--
-- RLS decides which rows; the API roles still need the table-level grant to
-- see the table at all. `anon` is left out deliberately - a signed-out
-- visitor has no household, so every policy would be false anyway, and not
-- granting it means a missing session fails as "permission denied" rather
-- than as a silently empty result.
-- ---------------------------------------------------------------------------
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE
          ON public.households, public.household_members, public.member_conditions
          TO authenticated;
    END IF;
END $$;

COMMIT;
