-- 12_ingredient_rule_tags.sql
-- Many-to-many between existing MaziMeal ingredients and rule_codes.
-- Lets the recipe engine turn an ingredient list into a set of trigger codes:
--   garlic   -> ING_GARLIC
--   broccoli -> ING_CRUCIFER
--   kale     -> ING_CRUCIFER / ING_LEAFY_GREEN
--
-- Load after 02_ingredients and 11_rule_codes (foreign keys into both).
-- Seeded by scripts/import_rules.py -> schema/seed/ingredient_rule_tags.sql.
-- Only confident mappings are seeded; ambiguous ones go to
-- schema/seed/ingredient_rule_tags_review.csv for a human to confirm.

CREATE TABLE IF NOT EXISTS ingredient_rule_tags (
    ingredient_id UUID        NOT NULL,
    rule_code     TEXT        NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT pk_ingredient_rule_tags PRIMARY KEY (ingredient_id, rule_code),

    CONSTRAINT fk_irt_ingredient FOREIGN KEY (ingredient_id)
        REFERENCES ingredients (ingredient_id) ON DELETE CASCADE,
    CONSTRAINT fk_irt_rule_code FOREIGN KEY (rule_code)
        REFERENCES rule_codes (code) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_irt_rule_code ON ingredient_rule_tags (rule_code);

COMMENT ON TABLE  ingredient_rule_tags IS
  'Maps existing ingredients to semantic rule codes. Composite PK keeps a pair unique, so re-seeding is idempotent.';
COMMENT ON COLUMN ingredient_rule_tags.rule_code IS 'FK to rule_codes.code. Usually an ING_* / CMP_* / BEV_* code a business rule triggers on.';
