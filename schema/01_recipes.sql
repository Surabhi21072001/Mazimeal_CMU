-- 01_recipes.sql
-- Recipe master table. From the schema doc, sheet 07_Recipes.
-- Load first: 03_recipe_ingredients has foreign keys into this.
--
-- Two columns aren't in the doc:
--   meal_category  Breakfast/Lunch/Dinner/Snack. Sheet 07 has no meal type on
--                  recipes, so there's nowhere to mark what a recipe is for.
--   dietary_tags   vegan, gluten_free, etc. Kept separate from meal_category
--                  because a special-diet recipe is still a breakfast or a
--                  dinner, so it needs both.
-- Worth agreeing on these before we add recipes.
--
-- embedding_vector and cultural_category_id are left out until we need them.

CREATE TABLE IF NOT EXISTS recipes (
    -- Doc says UUIDv7 via gen_ulid(). Using the built-in gen_random_uuid()
    -- for now since nothing sets that up yet. Same type, easy to swap.
    recipe_id               UUID          NOT NULL DEFAULT gen_random_uuid(),

    external_source_id      VARCHAR(100),
    recipe_name             VARCHAR(300)  NOT NULL,
    recipe_description      TEXT,

    -- Not in the doc, see header.
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

    -- These two say the same thing, keep them in sync.
    CONSTRAINT ck_recipes_ai_flag CHECK (is_ai_generated = (data_source = 'AI_generated'))
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

-- Stops the same recipe going in twice from different batches.
-- Case-insensitive, so "Masala Oats" and "masala oats" clash.
CREATE UNIQUE INDEX IF NOT EXISTS uq_recipes_name_lower
    ON recipes (lower(recipe_name))
    WHERE deleted_at IS NULL;

-- For counting by category and filtering by meal.
CREATE INDEX IF NOT EXISTS idx_recipes_meal_category ON recipes (meal_category);

CREATE INDEX IF NOT EXISTS idx_recipes_dietary_tags  ON recipes USING GIN (dietary_tags);
CREATE INDEX IF NOT EXISTS idx_recipes_name_fts
    ON recipes USING GIN (to_tsvector('english', recipe_name));
CREATE INDEX IF NOT EXISTS idx_recipes_difficulty    ON recipes (difficulty_level);
CREATE INDEX IF NOT EXISTS idx_recipes_gi            ON recipes (glycemic_index_estimate);
CREATE INDEX IF NOT EXISTS idx_recipes_deleted       ON recipes (deleted_at)
    WHERE deleted_at IS NOT NULL;

-- Only applies where there is an id. Most rows won't have one.
CREATE UNIQUE INDEX IF NOT EXISTS uq_recipes_external_source
    ON recipes (external_source_id)
    WHERE external_source_id IS NOT NULL;

COMMENT ON TABLE  recipes                IS 'Recipe master. Target 400 rows.';
COMMENT ON COLUMN recipes.meal_category  IS 'Breakfast | Lunch | Dinner | Snack. Not in the schema doc.';
COMMENT ON COLUMN recipes.dietary_tags   IS 'vegan, gluten_free, etc. Separate from meal_category so a recipe can be both.';
COMMENT ON COLUMN recipes.deleted_at     IS 'Soft delete. Queries should filter deleted_at IS NULL.';
