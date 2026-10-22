-- 05_recipe_nutrition.sql
-- Nutrition per serving for a recipe, as given by the source dataset.
--
-- Food.com publishes calories, fat, protein etc per recipe, so we don't have
-- to compute them from ingredient quantities. One row per recipe per nutrient,
-- same nutrient_id strings as the full schema's nutrients_master so the two
-- line up later.

CREATE TABLE IF NOT EXISTS recipe_nutrition (
    recipe_id    UUID           NOT NULL,
    nutrient_id  VARCHAR(40)    NOT NULL,   -- Energy, Macro_Protein, Macro_Fat, ...
    per_serving  DECIMAL(12,4)  NOT NULL,
    unit         VARCHAR(20)    NOT NULL,   -- kcal, g, mg
    source       VARCHAR(50)    NOT NULL DEFAULT 'Food.com',

    CONSTRAINT pk_recipe_nutrition PRIMARY KEY (recipe_id, nutrient_id),
    CONSTRAINT fk_rn_recipe FOREIGN KEY (recipe_id)
        REFERENCES recipes (recipe_id) ON DELETE CASCADE,
    CONSTRAINT ck_rn_value CHECK (per_serving >= 0)
);

CREATE INDEX IF NOT EXISTS idx_rn_nutrient ON recipe_nutrition (nutrient_id);

COMMENT ON TABLE recipe_nutrition IS 'Per-serving nutrition from the source dataset. FK to nutrients_master comes with the full schema.';
