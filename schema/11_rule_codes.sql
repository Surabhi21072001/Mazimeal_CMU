-- 11_rule_codes.sql
-- Controlled vocabulary for the semantic codes referenced by business_rules
-- (trigger_code, target_code, action_code) and by ingredient_rule_tags.
--
-- Seeded by scripts/import_rules.py from the codes actually present in the
-- workbook -> schema/seed/rule_codes.sql.
--
-- The workbook's "Codebook" sheet is empty, so display_name / description are
-- derived (humanized from the code) and flagged needs_review = TRUE until a
-- human fills them in. We never invent nutrition-science meaning here.

CREATE TABLE IF NOT EXISTS rule_codes (
    code          TEXT        NOT NULL,
    code_type     TEXT        NOT NULL,   -- prefix family: ING, NUT, PROC, PAIR, CMP, ...
    display_name  TEXT        NOT NULL,
    description   TEXT,
    needs_review  BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT pk_rule_codes PRIMARY KEY (code)
);

CREATE INDEX IF NOT EXISTS idx_rule_codes_type   ON rule_codes (code_type);
CREATE INDEX IF NOT EXISTS idx_rule_codes_review ON rule_codes (code) WHERE needs_review;

COMMENT ON TABLE  rule_codes IS
  'Semantic code vocabulary used by business_rules and ingredient_rule_tags. One row per unique code.';
COMMENT ON COLUMN rule_codes.code_type    IS 'Prefix family: ING_* ingredient, NUT_* nutrient, CMP_* compound, MACRO_* macro/pattern, PROC_* process, PAIR_* pairing, BEV_* beverage, etc.';
COMMENT ON COLUMN rule_codes.needs_review IS 'TRUE when display_name/description were auto-derived because the workbook Codebook sheet was empty.';
