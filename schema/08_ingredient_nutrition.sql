-- 08_ingredient_nutrition.sql
-- Nutrients per 100 g of an ingredient. From the schema doc, sheet 05.
-- Filled from USDA FoodData Central by scripts/match_usda.py.

CREATE TABLE IF NOT EXISTS ingredient_nutrition (
    nutrition_id          UUID          NOT NULL DEFAULT gen_random_uuid(),
    ingredient_id         UUID          NOT NULL,
    nutrient_id           VARCHAR(40)   NOT NULL,
    value_per_100g        DECIMAL(12,4) NOT NULL,
    unit                  VARCHAR(20)   NOT NULL,
    bioavailability_pct   DECIMAL(5,2),
    bioavailability_notes TEXT,
    usda_nutrient_code    VARCHAR(20),
    data_quality_flag     VARCHAR(20)   NOT NULL DEFAULT 'standard',
    source_id             VARCHAR(30)   NOT NULL DEFAULT 'usda_sr_legacy',

    CONSTRAINT pk_ingredient_nutrition PRIMARY KEY (nutrition_id),
    CONSTRAINT fk_in_ingredient FOREIGN KEY (ingredient_id)
        REFERENCES ingredients (ingredient_id) ON DELETE CASCADE,
    CONSTRAINT fk_in_source FOREIGN KEY (source_id) REFERENCES data_sources (source_id),
    -- one value per nutrient per source; v_ingredient_nutrition picks by precedence
    CONSTRAINT uq_in_ing_nut  UNIQUE (ingredient_id, nutrient_id, source_id),
    CONSTRAINT ck_in_value    CHECK (value_per_100g >= 0),
    CONSTRAINT ck_in_bioavail CHECK (bioavailability_pct IS NULL OR bioavailability_pct BETWEEN 0 AND 100),
    CONSTRAINT ck_in_quality  CHECK (data_quality_flag IN ('standard', 'estimated', 'measured'))
);

CREATE INDEX IF NOT EXISTS idx_in_nutrient ON ingredient_nutrition (nutrient_id);

COMMENT ON COLUMN ingredient_nutrition.value_per_100g IS 'USDA value per 100 g. Recipe totals scale this by recipe_ingredients.quantity_g.';
COMMENT ON COLUMN ingredient_nutrition.source_id      IS 'Which data_sources row this value came from.';
