-- ============================================================================
--  Sheet 02 · Household & Member Profiles
--  households · household_members · member_conditions · user_allergen_map
--
--  HIPAA: columns marked PHI below hold protected health information. They are
--  declared with their documented types here; encryption is applied in
--  94_security_phi.sql, and every one is discoverable via
--    SELECT * FROM public.v_phi_columns;
-- ============================================================================

-- ---------------------------------------------------------------------------
-- households · ~2M rows
-- ---------------------------------------------------------------------------
CREATE TABLE public.households (
    household_id        UUID          NOT NULL DEFAULT public.gen_ulid(),
    created_by_user_id  UUID          NOT NULL,
    household_name      VARCHAR(150),
    country_region      VARCHAR(10)   NOT NULL DEFAULT 'US',
    has_pets            BOOLEAN       NOT NULL DEFAULT FALSE,
    pets_receive_scraps BOOLEAN,
    subscription_tier   VARCHAR(20)   NOT NULL DEFAULT 'free',
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ,

    CONSTRAINT pk_households        PRIMARY KEY (household_id),
    CONSTRAINT ck_hh_country        CHECK (country_region ~ '^[A-Z]{2}$'),
    CONSTRAINT ck_hh_tier           CHECK (subscription_tier IN ('free', 'premium', 'clinical')),
    -- Scraps only mean something when there are pets to receive them.
    CONSTRAINT ck_hh_scraps_needs_pets
        CHECK (pets_receive_scraps IS NULL OR has_pets)
);

COMMENT ON COLUMN public.households.country_region      IS 'ISO 3166-1 alpha-2. Drives region-specific dietary defaults.';
COMMENT ON COLUMN public.households.pets_receive_scraps IS 'Escalates pet-toxic ingredient warnings (see ingredients.is_pet_toxic).';

-- ---------------------------------------------------------------------------
-- household_members · ~5M rows · SCALE: HASH(household_id) x16
--
-- This is the table the onboarding flow writes. Field-by-field it maps to the
-- questionnaire the workbook calls Q1-Q17; that source document was not
-- supplied with the schema, so the Q-numbers below are copied from the sheet's
-- "UI Field" column and should be confirmed against the real questionnaire.
-- ---------------------------------------------------------------------------
CREATE TABLE public.household_members (
    member_id           UUID          NOT NULL DEFAULT public.gen_ulid(),
    household_id        UUID          NOT NULL,
    member_name         VARCHAR(100)  NOT NULL,
    age                 SMALLINT,                         -- Q1
    sex_at_birth        CHAR(1),                          -- Q2
    weight_kg           DECIMAL(5,2),                     -- Q3
    height_cm           DECIMAL(5,2),
    activity_level      VARCHAR(20),                      -- Q4
    life_stage          VARCHAR(80),                      -- Q5  · PHI
    pregnancy_detail    VARCHAR(50),                      -- Q5  · PHI
    lifestyle_dietary   TEXT[],                           -- Q6
    goal                VARCHAR(80),                      -- Q10
    food_preference_csv TEXT[],                           -- Q14
    meal_spacing_pref   VARCHAR(80),                      -- Q15
    category_id         VARCHAR(10),                      -- derived from age+sex
    profile_email       VARCHAR(255),                     -- Q17
    phone               VARCHAR(20),                      -- Q16 · PHI
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ,
    deleted_at          TIMESTAMPTZ,

    CONSTRAINT pk_household_members PRIMARY KEY (:pk_household_members),
    CONSTRAINT ck_hm_age            CHECK (age IS NULL OR age BETWEEN 0 AND 130),
    CONSTRAINT ck_hm_sex            CHECK (sex_at_birth IS NULL OR sex_at_birth IN ('M', 'F')),
    CONSTRAINT ck_hm_weight         CHECK (weight_kg IS NULL OR weight_kg BETWEEN 0.5 AND 500),
    CONSTRAINT ck_hm_height         CHECK (height_cm IS NULL OR height_cm BETWEEN 20 AND 280),
    CONSTRAINT ck_hm_activity       CHECK (activity_level IS NULL OR activity_level IN
                                      ('sedentary', 'lightly_active', 'moderate', 'very_active', 'athlete')),
    CONSTRAINT ck_hm_goal           CHECK (goal IS NULL OR goal IN
                                      ('weight_loss', 'muscle_gain', 'maintenance', 'wellness')),
    CONSTRAINT ck_hm_spacing        CHECK (meal_spacing_pref IS NULL OR meal_spacing_pref IN
                                      ('3_meals', 'intermittent_fasting', '5_small')),
    CONSTRAINT ck_hm_email_lc       CHECK (profile_email IS NULL OR profile_email = lower(profile_email)),
    CONSTRAINT ck_hm_phone_e164     CHECK (phone IS NULL OR phone ~ '^\+[1-9][0-9]{6,14}$'),
    -- pregnancy_detail is only meaningful alongside a pregnancy life_stage.
    CONSTRAINT ck_hm_pregnancy      CHECK (pregnancy_detail IS NULL OR life_stage IS NOT NULL)
) :part_household_members ;

COMMENT ON COLUMN public.household_members.life_stage          IS 'PHI: pregnancy_wk_N / lactating / menopause. Encrypt at rest.';
COMMENT ON COLUMN public.household_members.pregnancy_detail    IS 'PHI: trimester or week number. Encrypt at rest.';
COMMENT ON COLUMN public.household_members.phone               IS 'PHI: E.164 format. Encrypt at rest.';
COMMENT ON COLUMN public.household_members.lifestyle_dietary   IS 'Array of tags (vegan, halal, ...). GIN-indexed: WHERE ''vegan'' = ANY(lifestyle_dietary).';
COMMENT ON COLUMN public.household_members.food_preference_csv IS 'Cuisine preferences. Name retained from the workbook for traceability, but the type is TEXT[] — it is not CSV.';
COMMENT ON COLUMN public.household_members.category_id         IS 'System-derived C001-C021 from age + sex_at_birth. See fn_derive_category_id() in 93_functions.sql.';
COMMENT ON COLUMN public.household_members.updated_at          IS 'Trigger fires pg_notify -> nutrient-target-recompute queue.';

-- ---------------------------------------------------------------------------
-- member_conditions · ~15M rows · SCALE: HASH(member_id) x16 · ALL ROWS PHI
--
-- Allergies, diagnosed conditions, medications and supplements share this table
-- and are distinguished by condition_type.
-- ---------------------------------------------------------------------------
CREATE TABLE public.member_conditions (
    record_id      UUID          NOT NULL DEFAULT public.gen_ulid(),
    member_id      UUID          NOT NULL,
    condition_type VARCHAR(30)   NOT NULL,
    condition_code VARCHAR(20),
    value_text     VARCHAR(200),
    severity       VARCHAR(20),
    hipaa_flag     BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),

    CONSTRAINT pk_member_conditions PRIMARY KEY (:pk_member_conditions),
    CONSTRAINT ck_mc_type     CHECK (condition_type IN ('condition', 'allergy', 'medication', 'supplement')),
    CONSTRAINT ck_mc_severity CHECK (severity IS NULL OR severity IN
                                ('mild', 'moderate', 'severe', 'anaphylactic')),
    -- A row must identify what it refers to: a reference code, free text, or both.
    CONSTRAINT ck_mc_has_subject CHECK (condition_code IS NOT NULL OR value_text IS NOT NULL)
) :part_member_conditions ;

COMMENT ON TABLE  public.member_conditions            IS 'PHI TABLE. Every row is protected health information; all access is audited.';
COMMENT ON COLUMN public.member_conditions.value_text IS 'PHI: free text (medication name, allergy detail). Encrypt at rest.';

-- ---------------------------------------------------------------------------
-- user_allergen_map · ~8M rows
--
-- The denormalised household-level hard-block set. Derived from
-- member_conditions WHERE condition_type='allergy', resolved to ingredient_ids,
-- then unioned across the household: if ANY member is blocked, the whole
-- household is blocked. Cached in Redis as al:{household_id} (SET, TTL 3600s).
-- ---------------------------------------------------------------------------
CREATE TABLE public.user_allergen_map (
    allergen_id             UUID        NOT NULL DEFAULT public.gen_ulid(),
    household_id            UUID        NOT NULL,
    member_id               UUID        NOT NULL,
    ingredient_id           UUID,
    is_household_hard_block BOOLEAN     NOT NULL DEFAULT TRUE,
    severity                VARCHAR(20),

    CONSTRAINT pk_user_allergen_map PRIMARY KEY (allergen_id),
    CONSTRAINT ck_uam_severity CHECK (severity IS NULL OR severity IN
                                 ('anaphylactic', 'severe', 'intolerance', 'preference'))
);

COMMENT ON TABLE  public.user_allergen_map                         IS 'Derived hard-block set. Rebuilt by the household-allergen-cache-warm job on member_conditions change.';
COMMENT ON COLUMN public.user_allergen_map.is_household_hard_block IS 'TRUE excludes the ingredient from every recipe surfaced to this household.';
