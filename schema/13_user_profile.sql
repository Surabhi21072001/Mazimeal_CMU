-- 13_user_profile.sql
-- Single-user nutrition profile layer (MVP). One row per user.
--
-- This stores a user's basic nutrition-relevant profile and dietary
-- constraints. It is the first half of the user nutrition layer; daily nutrient
-- targets live in 14_user_nutrient_targets.sql.
--
-- No recommendation/scoring/filtering logic lives here -- this is storage only.
-- Allergies and preferences are kept as arrays on the profile for the MVP
-- (mirrors recipes.dietary_tags), rather than separate tables:
--   * allergies    -> will later act as HARD constraints (block a recipe)
--   * preferences  -> will later act as SOFT ranking signals
-- That logic is NOT implemented yet.
--
-- Conventions follow the rest of the schema: UUID PK via gen_random_uuid(),
-- TIMESTAMPTZ DEFAULT now(), named ck_/pk_ constraints, IN(...) vocabularies.

CREATE TABLE IF NOT EXISTS user_profile (
    user_id        UUID          NOT NULL DEFAULT gen_random_uuid(),

    name           VARCHAR(200)  NOT NULL,

    age_years      INTEGER       NOT NULL,
    sex            VARCHAR(20)    NOT NULL,

    height_cm      DECIMAL(5,1),
    weight_kg      DECIMAL(5,1),

    activity_level VARCHAR(20),
    goal           VARCHAR(20),

    diet_type      VARCHAR(50),

    allergies      TEXT[],
    preferences    TEXT[],

    created_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),

    CONSTRAINT pk_user_profile PRIMARY KEY (user_id),

    CONSTRAINT ck_user_profile_age    CHECK (age_years > 0 AND age_years < 130),
    CONSTRAINT ck_user_profile_height CHECK (height_cm IS NULL OR height_cm > 0),
    CONSTRAINT ck_user_profile_weight CHECK (weight_kg IS NULL OR weight_kg > 0),

    -- No pre-existing project vocabulary for these, so we define simple MVP
    -- controlled sets. Documented allowed values below.
    CONSTRAINT ck_user_profile_sex CHECK (sex IN
        ('female', 'male', 'other', 'prefer_not_to_say')),

    CONSTRAINT ck_user_profile_activity CHECK (activity_level IS NULL OR activity_level IN
        ('sedentary', 'light', 'moderate', 'active', 'very_active')),

    CONSTRAINT ck_user_profile_goal CHECK (goal IS NULL OR goal IN
        ('maintain_weight', 'lose_weight', 'gain_weight'))
);

COMMENT ON TABLE  user_profile              IS 'Single-user nutrition profile (MVP). One row per user. Storage only; no recommendation logic.';
COMMENT ON COLUMN user_profile.allergies    IS 'HARD constraints later: a recipe containing any of these is blocked. Not enforced yet.';
COMMENT ON COLUMN user_profile.preferences  IS 'SOFT signals later: used for ranking, never blocking. Not enforced yet.';
COMMENT ON COLUMN user_profile.sex          IS 'Allowed: female | male | other | prefer_not_to_say.';
COMMENT ON COLUMN user_profile.activity_level IS 'Allowed: sedentary | light | moderate | active | very_active.';
COMMENT ON COLUMN user_profile.goal         IS 'Allowed: maintain_weight | lose_weight | gain_weight.';
COMMENT ON COLUMN user_profile.diet_type    IS 'Free text for the MVP, e.g. mediterranean, vegan, omnivore.';
