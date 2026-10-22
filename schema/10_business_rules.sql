-- 10_business_rules.sql
-- Phase 2 recipe-optimization business rules. Loaded from the approved
-- workbook "IN WORK - MaziMeal Recipe Optimization Rules (1).xlsx" by
-- scripts/import_rules.py, which writes schema/seed/business_rules.sql.
--
-- These are the Bioavailability / Food Synergies / Inhibitors / Glycemic
-- Behaviors rules. Separate from nutrient_rules (sheet 03, clinical/safety
-- rules): this table carries the richer optimization vocabulary with the
-- trigger/target/action codes the recipe engine detects against.
--
-- Readable rule_id (BIO-001, SYN-002 ...) rather than a UUID, matching the
-- nutrient_rules convention. Load order: standalone, no FKs out. Load before
-- 11_rule_codes and 12_ingredient_rule_tags if you want, order doesn't matter.

CREATE TABLE IF NOT EXISTS business_rules (
    rule_id                    TEXT        NOT NULL,

    rule_name                  TEXT        NOT NULL,
    rule_category              TEXT        NOT NULL,   -- derived from sheet name
    rule_type                  TEXT,                   -- workbook free-text, not enumerated

    trigger_food_or_pattern    TEXT,
    trigger_code               TEXT,                   -- semantic code, FK-ish to rule_codes.code
    target_nutrient_or_outcome TEXT,
    target_code                TEXT,
    action                     TEXT,
    action_code                TEXT,

    mechanism                  TEXT,
    recipe_engine_instruction  TEXT,
    conditions_and_limits      TEXT,                   -- workbook holds prose, kept as TEXT
    population_scope           TEXT,                   -- workbook holds prose, kept as TEXT

    evidence_tier              TEXT,
    evidence_summary           TEXT,
    automation_status          TEXT,

    source_title               TEXT,
    source_type                TEXT,
    source_url                 TEXT,
    review_date                DATE,

    is_active                  BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT pk_business_rules PRIMARY KEY (rule_id),

    -- Workbook uses exactly these four automation statuses. Constrain to them.
    -- recipe_safe        apply automatically
    -- conditional        apply only when a condition/population matches
    -- instruction_only   surface as guidance, never auto-modify the recipe
    -- do_not_automate    human decision only
    CONSTRAINT ck_business_rules_automation CHECK (
        automation_status IS NULL OR automation_status IN
        ('recipe_safe', 'conditional', 'instruction_only', 'do_not_automate')),

    -- Workbook evidence tiers are A / B / C only.
    CONSTRAINT ck_business_rules_evidence_tier CHECK (
        evidence_tier IS NULL OR evidence_tier IN ('A', 'B', 'C')),

    -- rule_category comes from the four rule sheets.
    CONSTRAINT ck_business_rules_category CHECK (rule_category IN
        ('bioavailability', 'food_synergy', 'inhibitor', 'glycemic'))

    -- Deliberately NO check on rule_type or source_type: the workbook uses
    -- 14 and 22 distinct free-text values respectively. Constraining them
    -- would reject valid approved rows.
);

CREATE INDEX IF NOT EXISTS idx_business_rules_category     ON business_rules (rule_category);
CREATE INDEX IF NOT EXISTS idx_business_rules_trigger_code ON business_rules (trigger_code);
CREATE INDEX IF NOT EXISTS idx_business_rules_target_code  ON business_rules (target_code);
CREATE INDEX IF NOT EXISTS idx_business_rules_action_code  ON business_rules (action_code);
CREATE INDEX IF NOT EXISTS idx_business_rules_automation   ON business_rules (automation_status);
-- Detection only cares about active rules, and most rows are active.
CREATE INDEX IF NOT EXISTS idx_business_rules_active       ON business_rules (rule_id) WHERE is_active;

COMMENT ON TABLE  business_rules IS
  'Phase 2 recipe-optimization rules from the approved workbook. One row per approved rule (BIO-/SYN-/INH-/GLY-).';
COMMENT ON COLUMN business_rules.rule_category             IS 'bioavailability | food_synergy | inhibitor | glycemic. Derived from the source sheet.';
COMMENT ON COLUMN business_rules.trigger_code              IS 'Semantic code the recipe engine detects, e.g. ING_GARLIC. Vocabulary lives in rule_codes.';
COMMENT ON COLUMN business_rules.automation_status         IS 'recipe_safe | conditional | instruction_only | do_not_automate.';
COMMENT ON COLUMN business_rules.recipe_engine_instruction IS 'Plain-language instruction for the (future) optimization/LLM layer.';
COMMENT ON COLUMN business_rules.is_active                 IS 'Soft disable. Detection only returns active rules.';
