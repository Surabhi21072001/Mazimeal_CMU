-- 07_foodcom_raw.sql
-- Landing table for the Food.com recipes dataset, one column per dataset
-- column, loaded as-is. The app never reads this table; the importer
-- transforms it into recipes / ingredients / recipe_ingredients /
-- recipe_steps / recipe_nutrition.
--
-- Dataset: Food.com Recipes and Reviews (Kaggle, irkaal) or the HuggingFace
-- mirror AkashPS11/recipes_data_food.com. Same columns either way.
--
-- List columns (Keywords, RecipeIngredientQuantities, RecipeIngredientParts,
-- RecipeInstructions) arrive as R-style vectors: c("a", "b", "c"). Kept as
-- text here; parsed by scripts/import_foodcom.py. Times are ISO 8601
-- durations like PT1H30M.

CREATE TABLE IF NOT EXISTS foodcom_recipes_raw (
    recipe_id                   BIGINT PRIMARY KEY,   -- dataset RecipeId
    name                        TEXT,
    author_id                   BIGINT,
    author_name                 TEXT,
    cook_time                   TEXT,                 -- PT30M
    prep_time                   TEXT,
    total_time                  TEXT,
    date_published              TEXT,
    description                 TEXT,
    images                      TEXT,
    recipe_category             TEXT,                 -- "Breakfast", "Chicken Breast", ...
    keywords                    TEXT,                 -- c("Vegan", "< 60 Mins", ...)
    recipe_ingredient_quantities TEXT,                -- c("2", "1/2", ...)
    recipe_ingredient_parts     TEXT,                 -- c("flour", "sugar", ...)
    aggregated_rating           DECIMAL(3,1),
    review_count                INTEGER,
    calories                    DECIMAL(10,2),
    fat_content                 DECIMAL(10,2),
    saturated_fat_content       DECIMAL(10,2),
    cholesterol_content         DECIMAL(10,2),
    sodium_content              DECIMAL(10,2),
    carbohydrate_content        DECIMAL(10,2),
    fiber_content               DECIMAL(10,2),
    sugar_content               DECIMAL(10,2),
    protein_content             DECIMAL(10,2),
    recipe_servings             DECIMAL(6,1),
    recipe_yield                TEXT,
    recipe_instructions         TEXT,                 -- c("Preheat oven.", ...)
    imported_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_foodcom_category ON foodcom_recipes_raw (recipe_category);
CREATE INDEX IF NOT EXISTS idx_foodcom_rating   ON foodcom_recipes_raw (aggregated_rating DESC, review_count DESC);

COMMENT ON TABLE foodcom_recipes_raw IS 'Raw Food.com dataset rows. Staging only. Nutrition columns are per serving.';
