-- 09_ingredient_measures.sql
-- Household measures and their weight in grams, per ingredient.
-- "1 cup flour" is 125 g, "1 large egg" 50 g, "1 clove garlic" 3 g.
-- Filled from USDA food_portion by scripts/ingredient_grams.py; fallback rows
-- are constants for measures USDA doesn't publish.

CREATE TABLE IF NOT EXISTS ingredient_measures (
    ingredient_id      UUID          NOT NULL,
    measure            VARCHAR(40)   NOT NULL,
    gram_weight        DECIMAL(8,2)  NOT NULL,
    source             VARCHAR(30)   NOT NULL DEFAULT 'USDA SR Legacy',
    source_portion_id  BIGINT,

    CONSTRAINT pk_ingredient_measures PRIMARY KEY (ingredient_id, measure),
    CONSTRAINT fk_im_ingredient FOREIGN KEY (ingredient_id)
        REFERENCES ingredients (ingredient_id) ON DELETE CASCADE,
    CONSTRAINT ck_im_grams CHECK (gram_weight > 0)
);

COMMENT ON TABLE  ingredient_measures                   IS 'Grams per one household measure of an ingredient.';
COMMENT ON COLUMN ingredient_measures.source_portion_id IS 'USDA food_portion.id when the weight came from USDA.';
