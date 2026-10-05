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
    measure          VARCHAR(40),
    quantity_g       DECIMAL(10,2),
    grams_source     VARCHAR(20)    NOT NULL DEFAULT 'none',
    quantity_aligned BOOLEAN,
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
    CONSTRAINT ck_ri_grams    CHECK (quantity_g IS NULL OR quantity_g > 0),
    CONSTRAINT ck_ri_grams_src CHECK (grams_source IN ('manual', 'measure', 'assumed', 'none')),
    CONSTRAINT ck_ri_sequence CHECK (sequence_order IS NULL OR sequence_order > 0)
);

-- Same ingredient shouldn't appear twice on one recipe.
CREATE UNIQUE INDEX IF NOT EXISTS uq_ri_recipe_ingredient
    ON recipe_ingredients (recipe_id, ingredient_id);

CREATE INDEX IF NOT EXISTS idx_ri_ingredient ON recipe_ingredients (ingredient_id);

COMMENT ON TABLE  recipe_ingredients                IS 'One row per ingredient per recipe.';
COMMENT ON COLUMN recipe_ingredients.unit           IS 'g, ml, tsp, cup, whole, cloves. Imported Food.com lines: unit (bare number) or portion (no number).';
COMMENT ON COLUMN recipe_ingredients.quantity_g     IS 'Grams for this line. What nutrition is calculated from. NULL = unknown, never 0.';
COMMENT ON COLUMN recipe_ingredients.measure        IS 'Household measure the quantity is in (cup, tbsp, each). Weight comes from ingredient_measures.';
COMMENT ON COLUMN recipe_ingredients.grams_source   IS 'manual: entered in grams. measure: quantity x measure weight. assumed: no quantity in the source, 1 measure assumed. none: unknown.';
COMMENT ON COLUMN recipe_ingredients.quantity_aligned IS 'Imported recipes only. FALSE when the source quantity list did not line up with its ingredient list.';
COMMENT ON COLUMN recipe_ingredients.synergy_role   IS 'iron_source, vit_c_enhancer, resistant_starch. Used for scoring later.';
COMMENT ON COLUMN recipe_ingredients.sequence_order IS 'Eating order: 1 = vegetables first, 3 = carbs last.';
