-- 03_recipe_ingredients.sql
-- Ingredient lines for each recipe. From the schema doc, sheet 07_Recipes.
-- Load after 01_recipes and 02_ingredients: foreign keys into both.
--
-- Draft to get the schema loading end to end. Owner can rework freely.

CREATE TABLE IF NOT EXISTS recipe_ingredients (
    line_id          UUID           NOT NULL DEFAULT gen_random_uuid(),
    recipe_id        UUID           NOT NULL,
    ingredient_id    UUID           NOT NULL,
    quantity         DECIMAL(10,3)  NOT NULL,
    unit             VARCHAR(30)    NOT NULL,
    preparation_note VARCHAR(200),
    is_optional      BOOLEAN        NOT NULL DEFAULT FALSE,
    can_substitute   BOOLEAN        NOT NULL DEFAULT TRUE,
    synergy_role     VARCHAR(50),
    sequence_order   SMALLINT,

    CONSTRAINT pk_recipe_ingredients PRIMARY KEY (line_id),

    CONSTRAINT fk_ri_recipe FOREIGN KEY (recipe_id)
        REFERENCES recipes (recipe_id) ON DELETE CASCADE,
    CONSTRAINT fk_ri_ingredient FOREIGN KEY (ingredient_id)
        REFERENCES ingredients (ingredient_id),

    CONSTRAINT ck_ri_quantity CHECK (quantity > 0),
    CONSTRAINT ck_ri_sequence CHECK (sequence_order IS NULL OR sequence_order > 0)
);

-- Same ingredient shouldn't appear twice on one recipe.
CREATE UNIQUE INDEX IF NOT EXISTS uq_ri_recipe_ingredient
    ON recipe_ingredients (recipe_id, ingredient_id);

CREATE INDEX IF NOT EXISTS idx_ri_ingredient ON recipe_ingredients (ingredient_id);

COMMENT ON TABLE  recipe_ingredients                IS 'One row per ingredient per recipe.';
COMMENT ON COLUMN recipe_ingredients.unit           IS 'g, ml, tsp, cup, whole, cloves.';
COMMENT ON COLUMN recipe_ingredients.synergy_role   IS 'iron_source, vit_c_enhancer, resistant_starch. Used for scoring later.';
COMMENT ON COLUMN recipe_ingredients.sequence_order IS 'Eating order: 1 = vegetables first, 3 = carbs last.';
