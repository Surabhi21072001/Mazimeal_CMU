-- 02_ingredients.sql
-- Ingredient master table. From the schema doc, sheet 05_Ingredients_Nutrition.
-- Load after 01_recipes, before 03_recipe_ingredients.
-- Owner: Swetha.
--
-- Nutrition values per ingredient live in 08_ingredient_nutrition.sql.

CREATE TABLE IF NOT EXISTS ingredients (
    ingredient_id           UUID          NOT NULL DEFAULT gen_random_uuid(),
    usda_fdc_id             BIGINT,
    ingredient_name         VARCHAR(200)  NOT NULL,
    ingredient_name_aliases TEXT[],
    food_category           VARCHAR(80)   NOT NULL,
    is_allergen             BOOLEAN       NOT NULL DEFAULT FALSE,
    allergen_type           VARCHAR(50),
    is_pet_toxic            BOOLEAN       NOT NULL DEFAULT FALSE,
    pet_toxic_notes         TEXT,
    typical_serving_g       DECIMAL(8,2),
    default_measure         VARCHAR(40),
    data_source             VARCHAR(50)   NOT NULL DEFAULT 'USDA',
    created_at              TIMESTAMPTZ   NOT NULL DEFAULT now(),

    CONSTRAINT pk_ingredients PRIMARY KEY (ingredient_id),

    CONSTRAINT ck_ingredients_source CHECK (data_source IN
        ('USDA', 'Open Food Facts', 'Nutritionix', 'Manual')),
    CONSTRAINT ck_ingredients_serving CHECK (typical_serving_g IS NULL OR typical_serving_g > 0),

    -- An allergen with no type can't be matched against anyone's allergy.
    CONSTRAINT ck_ingredients_allergen CHECK (NOT is_allergen OR allergen_type IS NOT NULL)
);

-- Stops "Tomato", "tomato" and "Tomato " going in as separate rows.
CREATE UNIQUE INDEX IF NOT EXISTS uq_ingredients_name_lower
    ON ingredients (lower(btrim(ingredient_name)));

-- USDA id unique where present. Manual entries won't have one.
CREATE UNIQUE INDEX IF NOT EXISTS uq_ingredients_fdc
    ON ingredients (usda_fdc_id)
    WHERE usda_fdc_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ingredients_name_fts
    ON ingredients USING GIN (to_tsvector('english', ingredient_name));
CREATE INDEX IF NOT EXISTS idx_ingredients_aliases  ON ingredients USING GIN (ingredient_name_aliases);
CREATE INDEX IF NOT EXISTS idx_ingredients_category ON ingredients (food_category);
CREATE INDEX IF NOT EXISTS idx_ingredients_allergen ON ingredients (allergen_type) WHERE is_allergen;
CREATE INDEX IF NOT EXISTS idx_ingredients_pet_toxic ON ingredients (ingredient_id) WHERE is_pet_toxic;

COMMENT ON TABLE  ingredients               IS 'Ingredient master. Nutrition per 100g lives in ingredient_nutrition.';
COMMENT ON COLUMN ingredients.usda_fdc_id   IS 'USDA FoodData Central id. NULL for manual entries.';
COMMENT ON COLUMN ingredients.food_category IS 'USDA food group.';
COMMENT ON COLUMN ingredients.is_pet_toxic  IS 'Onion, grapes, chocolate, xylitol etc. Shown when a household has pets.';
