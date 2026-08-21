-- ============================================================================
--  MAZIMEAL · Week 1 Schema
--  01_recipes.sql
--
--  Owner:  Zihan Liu
--  Source: Synergia_Unified_DB_Schema.xlsx, sheet 07_Recipes
--  Load order: 01 (no dependencies — load this before 03_recipe_ingredients)
--
--  Week-1 subset. Columns match the workbook exactly except where flagged
--  below; the remaining sheet-07 columns (embedding_vector, cultural_category_id)
--  are deferred until pgvector and cultural_categories exist.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Two things for the schema review call
-- ---------------------------------------------------------------------------
--
-- 1. THE WORKBOOK HAS NO MEAL CATEGORY ON RECIPES.
--
--    Our data plan splits 400 recipes into Breakfast 80 / Lunch 80 / Dinner 100
--    / Snacks 60 / Special Diets 80. Sheet 07 has no column to store that —
--    `meal_type` exists only on household_recipe_plan, which is the *plan*, not
--    the recipe. Without a column here, batch 1 has nowhere to record that a
--    recipe is breakfast, and the per-category counts cannot be run.
--
--    `meal_category` below is therefore an addition, not a transcription.
--    Flagging it so the team adopts it deliberately.
--
-- 2. "SPECIAL DIETS" IS NOT A MEAL SLOT.
--
--    Breakfast, Lunch, Dinner and Snack are mutually exclusive — a recipe is
--    one of them. "Special Diet" is a different axis: a vegan breakfast is both.
--    Putting all five in one column forces a false choice and makes the 80
--    special-diet recipes unreachable by any breakfast query.
--
--    Modelled here as two columns: meal_category (the slot) and dietary_tags
--    (an array, so a recipe can carry several). The 80 "Special Diets" rows
--    then get a real meal_category AND their dietary tags, which is what the
--    app actually needs to filter on.
--
--    If the team prefers to keep one column, say so in the review call — but
--    it should be a decision, not an accident.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS recipes (
    -- The workbook specifies time-ordered UUIDv7 ("gen_ulid()") to keep inserts
    -- sequential. That needs a helper function nobody owns this week, so this
    -- uses the built-in gen_random_uuid() (PostgreSQL 13+, no extension) and
    -- swaps to gen_ulid() when the full schema lands. Same type, same width.
    recipe_id               UUID          NOT NULL DEFAULT gen_random_uuid(),

    external_source_id      VARCHAR(100),
    recipe_name             VARCHAR(300)  NOT NULL,
    recipe_description      TEXT,

    -- See note 1 above — addition, not from the workbook.
    meal_category           VARCHAR(20)   NOT NULL,
    dietary_tags            TEXT[],

    prep_time_min           SMALLINT,
    cook_time_min           SMALLINT,
    difficulty_level        VARCHAR(20),
    servings                SMALLINT      NOT NULL DEFAULT 4,
    calories_per_serving    DECIMAL(8,2),
    glycemic_index_estimate DECIMAL(5,2),
    regional_origin         VARCHAR(100),
    data_source             VARCHAR(80)   NOT NULL DEFAULT 'Manual',
    is_ai_generated         BOOLEAN       NOT NULL DEFAULT FALSE,
    active_rule_ids_csv     TEXT,
    created_at              TIMESTAMPTZ   NOT NULL DEFAULT now(),
    deleted_at              TIMESTAMPTZ,

    CONSTRAINT pk_recipes PRIMARY KEY (recipe_id),

    CONSTRAINT ck_recipes_meal_category CHECK (meal_category IN
        ('Breakfast', 'Lunch', 'Dinner', 'Snack')),

    CONSTRAINT ck_recipes_data_source CHECK (data_source IN
        ('USDA', 'Open_Food_Facts', 'Manual', 'AI_generated')),

    CONSTRAINT ck_recipes_difficulty CHECK (difficulty_level IS NULL
        OR difficulty_level IN ('Easy', 'Medium', 'Hard')),

    CONSTRAINT ck_recipes_servings CHECK (servings > 0),
    CONSTRAINT ck_recipes_prep     CHECK (prep_time_min IS NULL OR prep_time_min >= 0),
    CONSTRAINT ck_recipes_cook     CHECK (cook_time_min IS NULL OR cook_time_min >= 0),
    CONSTRAINT ck_recipes_calories CHECK (calories_per_serving IS NULL
                                          OR calories_per_serving >= 0),
    CONSTRAINT ck_recipes_gi       CHECK (glycemic_index_estimate IS NULL
                                          OR glycemic_index_estimate BETWEEN 0 AND 100),

    -- The partition key in the full schema is data_source, and is_ai_generated
    -- describes the same fact. Letting them disagree puts AI content in the
    -- reference set. Cheap to enforce now, painful to reconcile later.
    CONSTRAINT ck_recipes_ai_flag CHECK (is_ai_generated = (data_source = 'AI_generated'))
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

-- Three people insert 400 recipes into one table this week. Without this, two
-- batches can silently contain the same dish, and the validation script only
-- finds it afterwards. Case-insensitive so "Masala Oats" and "masala oats"
-- collide.
CREATE UNIQUE INDEX IF NOT EXISTS uq_recipes_name_lower
    ON recipes (lower(recipe_name))
    WHERE deleted_at IS NULL;

-- Serves the per-category counts and every "show me breakfasts" query.
CREATE INDEX IF NOT EXISTS idx_recipes_meal_category ON recipes (meal_category);

CREATE INDEX IF NOT EXISTS idx_recipes_dietary_tags  ON recipes USING GIN (dietary_tags);
CREATE INDEX IF NOT EXISTS idx_recipes_name_fts
    ON recipes USING GIN (to_tsvector('english', recipe_name));
CREATE INDEX IF NOT EXISTS idx_recipes_difficulty    ON recipes (difficulty_level);
CREATE INDEX IF NOT EXISTS idx_recipes_gi            ON recipes (glycemic_index_estimate);
CREATE INDEX IF NOT EXISTS idx_recipes_deleted       ON recipes (deleted_at)
    WHERE deleted_at IS NOT NULL;

-- Unique among non-NULL values only: most Manual rows have no upstream id.
CREATE UNIQUE INDEX IF NOT EXISTS uq_recipes_external_source
    ON recipes (external_source_id)
    WHERE external_source_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Documentation
-- ---------------------------------------------------------------------------
COMMENT ON TABLE  recipes                         IS 'Recipe master. Week-1 subset of sheet 07. Target: 400 rows.';
COMMENT ON COLUMN recipes.meal_category           IS 'ADDITION (not in workbook): Breakfast | Lunch | Dinner | Snack. Required for the batch plan and the task-21 counts.';
COMMENT ON COLUMN recipes.dietary_tags            IS 'ADDITION: vegan, vegetarian, gluten_free, dairy_free, low_carb, keto, halal, kosher. Orthogonal to meal_category — the "Special Diets" batch uses both.';
COMMENT ON COLUMN recipes.external_source_id      IS 'Upstream id when imported. NULL for hand-written rows.';
COMMENT ON COLUMN recipes.glycemic_index_estimate IS 'Carb-weighted average GI. Filters recipes for diabetic profiles.';
COMMENT ON COLUMN recipes.active_rule_ids_csv     IS 'Denormalised summary of rules demonstrated. recipe_rules_map is the normalised source of truth once it exists.';
COMMENT ON COLUMN recipes.deleted_at              IS 'Soft delete. Every query must filter deleted_at IS NULL.';
