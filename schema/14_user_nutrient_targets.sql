-- 14_user_nutrient_targets.sql
-- A user's DAILY nutrient targets. One row per (user, nutrient). Load after
-- 13_user_profile.sql (foreign key into it).
--
-- Targets are stored as DAILY values (the recommendation engine will operate at
-- meal/day level). Weekly values, if ever needed, are derived: daily * 7.
--
-- nutrient_id uses the SAME identifier convention as recipe_nutrition /
-- ingredient_nutrition (VARCHAR(40): 'Energy', 'Macro_Protein', 'Iron',
-- 'Vitamin_C', 'Calcium', ...). There is no nutrients_master table in the repo
-- yet, so no FK is added here -- same as the existing nutrition tables, which
-- note the FK "comes with the full schema." If a nutrients_master is added
-- later, attach the FK then.
--
-- No target-calculation logic lives here. This table only stores targets.

CREATE TABLE IF NOT EXISTS user_nutrient_targets (
    user_id        UUID          NOT NULL,
    nutrient_id    VARCHAR(40)   NOT NULL,   -- same scheme as recipe_nutrition

    daily_target   DECIMAL(12,4) NOT NULL,
    unit           VARCHAR(20)   NOT NULL,   -- kcal, g, mg, mcg

    minimum_target DECIMAL(12,4),            -- optional floor
    upper_limit    DECIMAL(12,4),            -- optional ceiling (e.g. UL)

    target_source  VARCHAR(50),              -- USDA, NIH, DRI, MaziMeal calculated, Manual

    created_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),

    CONSTRAINT pk_user_nutrient_targets PRIMARY KEY (user_id, nutrient_id),

    CONSTRAINT fk_unt_user FOREIGN KEY (user_id)
        REFERENCES user_profile (user_id) ON DELETE CASCADE,

    -- Values are amounts, so they cannot be negative. daily_target must be set.
    CONSTRAINT ck_unt_daily   CHECK (daily_target >= 0),
    CONSTRAINT ck_unt_minimum CHECK (minimum_target IS NULL OR minimum_target >= 0),
    CONSTRAINT ck_unt_upper   CHECK (upper_limit IS NULL OR upper_limit >= 0),

    -- When both bounds are present, the floor must not exceed the ceiling.
    CONSTRAINT ck_unt_bounds CHECK (
        minimum_target IS NULL OR upper_limit IS NULL OR minimum_target <= upper_limit
    )
);

CREATE INDEX IF NOT EXISTS idx_unt_nutrient ON user_nutrient_targets (nutrient_id);

COMMENT ON TABLE  user_nutrient_targets               IS 'Per-user DAILY nutrient targets. One row per (user, nutrient). Storage only.';
COMMENT ON COLUMN user_nutrient_targets.nutrient_id   IS 'Same scheme as recipe_nutrition.nutrient_id (Energy, Macro_Protein, Iron, Vitamin_C, Calcium, ...).';
COMMENT ON COLUMN user_nutrient_targets.daily_target  IS 'Daily target amount. Weekly = daily_target * 7, computed downstream.';
COMMENT ON COLUMN user_nutrient_targets.minimum_target IS 'Optional lower bound; not every nutrient has one.';
COMMENT ON COLUMN user_nutrient_targets.upper_limit   IS 'Optional upper bound (e.g. tolerable upper intake level).';
COMMENT ON COLUMN user_nutrient_targets.target_source IS 'Provenance: USDA | NIH | DRI | MaziMeal calculated | Manual.';
