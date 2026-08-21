-- ============================================================================
--  MAZIMEAL · Week 1 Schema
--  04_nutrition_rules.sql
--
--  Owner:  Zihan Liu
--  Source: Synergia_Unified_DB_Schema.xlsx, sheet 03_Conditions_Rules
--  Load order: 04 (no hard dependencies this week — see the FK note below)
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Two naming points for the schema review call
-- ---------------------------------------------------------------------------
--
-- 1. NAME: our task list says `Nutrition_Rules`; the workbook says
--    `nutrient_rules`. Using the team's name here, because the task list is
--    what we agreed. Worth confirming out loud — the workbook is the long-term
--    reference and a rename later touches every query that reads it.
--
-- 2. CASE: PostgreSQL folds unquoted identifiers to lowercase, so writing
--    `Nutrition_Rules` in DDL creates a table actually called
--    `nutrition_rules`. Preserving the capitals would require double-quoting it
--    everywhere, forever. All three DDL files should use lowercase snake_case
--    for exactly this reason — cheap to agree now, tedious to fix later.
--
-- ---------------------------------------------------------------------------
-- Deferred foreign keys
-- ---------------------------------------------------------------------------
--  Three columns below reference tables that do not exist in week 1:
--    applies_to_category  -> categories      (sheet 04)
--    applies_to_condition -> conditions      (sheet 03)
--    document_id          -> documents       (sheet 03)
--
--  The columns are declared now so rule rows can carry the values, and the FK
--  constraints are added in week 2 as a one-line ALTER each (see the bottom of
--  this file). Declaring the columns now costs nothing; adding them later means
--  re-entering data.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS nutrition_rules (
    -- Readable string key from the workbook (R001, R085, R596, R-PRG01), not a
    -- surrogate UUID. Rules are referenced by id in prose, in evidence
    -- documents and by the scoring engine, so the id needs to stay legible.
    rule_id              VARCHAR(30)  NOT NULL,

    rule_name            VARCHAR(150) NOT NULL,
    rule_description     TEXT         NOT NULL,
    rule_type            VARCHAR(50)  NOT NULL,

    applies_to_category  VARCHAR(10),   -- FK -> categories  (week 2)
    applies_to_condition VARCHAR(20),   -- FK -> conditions  (week 2)

    is_hard_constraint   BOOLEAN      NOT NULL DEFAULT FALSE,

    document_id          VARCHAR(20),   -- FK -> documents   (week 2)
    short_description    VARCHAR(250),
    evidence_summary     TEXT,
    source               TEXT,

    created_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT pk_nutrition_rules PRIMARY KEY (rule_id),

    -- Two rules with the same name are two people entering the same rule twice.
    CONSTRAINT uq_nutrition_rules_name UNIQUE (rule_name),

    CONSTRAINT ck_nutrition_rules_type CHECK (rule_type IN
        ('nutrient_threshold', 'food_safety', 'behavioural', 'prep_method', 'allergy')),

    -- A hard constraint is never overridable and can block a recipe outright
    -- (allergen exclusion, "no honey under 12 months"). If one is wrong, someone
    -- gets hurt — so a hard rule must cite its evidence.
    CONSTRAINT ck_nutrition_rules_hard_needs_evidence CHECK (
        NOT is_hard_constraint OR source IS NOT NULL OR document_id IS NOT NULL
    )
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_nutrition_rules_condition
    ON nutrition_rules (applies_to_condition);

CREATE INDEX IF NOT EXISTS idx_nutrition_rules_category
    ON nutrition_rules (applies_to_category);

CREATE INDEX IF NOT EXISTS idx_nutrition_rules_type
    ON nutrition_rules (rule_type);

-- Hard constraints are pulled as a complete set on every scoring pass and are a
-- small fraction of the table, so a partial index keeps that lookup near-free.
CREATE INDEX IF NOT EXISTS idx_nutrition_rules_hard
    ON nutrition_rules (rule_id)
    WHERE is_hard_constraint;

-- ---------------------------------------------------------------------------
-- Documentation
-- ---------------------------------------------------------------------------
COMMENT ON TABLE  nutrition_rules                      IS 'Clinical and food-science rules. Workbook calls this nutrient_rules; renamed per the week-1 task list. ~2K rows at full scope.';
COMMENT ON COLUMN nutrition_rules.rule_id              IS 'Workbook format: R001, R085, R596, R-PRG01.';
COMMENT ON COLUMN nutrition_rules.rule_type            IS 'nutrient_threshold | food_safety | behavioural | prep_method | allergy';
COMMENT ON COLUMN nutrition_rules.applies_to_category  IS 'Age/sex category code. NULL = applies to everyone. FK deferred to week 2.';
COMMENT ON COLUMN nutrition_rules.applies_to_condition IS 'Condition code. NULL = not condition-specific. FK deferred to week 2.';
COMMENT ON COLUMN nutrition_rules.is_hard_constraint   IS 'TRUE = always enforced, never overridable. Requires cited evidence.';
COMMENT ON COLUMN nutrition_rules.source               IS 'DOI or PubMed URL.';

-- ---------------------------------------------------------------------------
-- Week 2 — run these once categories, conditions and documents exist
-- ---------------------------------------------------------------------------
--  ALTER TABLE nutrition_rules ADD CONSTRAINT fk_nr_category
--      FOREIGN KEY (applies_to_category)  REFERENCES categories (category_id);
--  ALTER TABLE nutrition_rules ADD CONSTRAINT fk_nr_condition
--      FOREIGN KEY (applies_to_condition) REFERENCES conditions (condition_code);
--  ALTER TABLE nutrition_rules ADD CONSTRAINT fk_nr_document
--      FOREIGN KEY (document_id)          REFERENCES documents (document_id);
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- Starter rows — the five rules named in the workbook, so the table is not
-- empty at Friday's demo and the recipe batches have something to reference.
-- ---------------------------------------------------------------------------
INSERT INTO nutrition_rules
    (rule_id, rule_name, rule_description, rule_type, applies_to_category,
     applies_to_condition, is_hard_constraint, short_description, source)
VALUES
    ('R001', 'Vitamin_C_Iron_Synergy',
     'Vitamin C consumed in the same meal as a non-heme iron source substantially increases iron absorption by reducing ferric to ferrous iron.',
     'nutrient_threshold', NULL, NULL, FALSE,
     'Pair iron-rich plants with a vitamin C source.',
     'https://pubmed.ncbi.nlm.nih.gov/2507689/'),

    ('R002', 'Allicin_Rest_Period',
     'Crushed or chopped garlic must rest about 10 minutes before heating, allowing alliinase to convert alliin into allicin. Heating immediately destroys the enzyme first.',
     'prep_method', NULL, NULL, FALSE,
     'Rest crushed garlic 10 minutes before cooking.',
     'https://pubmed.ncbi.nlm.nih.gov/11238797/'),

    ('R011', 'Glycemic_Retrogradation',
     'Cooking then cooling starch raises resistant starch and materially lowers the glycemic response. Most of the effect survives reheating.',
     'prep_method', NULL, NULL, FALSE,
     'Cook, chill, then reheat rice and potatoes.',
     'https://pubmed.ncbi.nlm.nih.gov/26693746/'),

    ('R085', 'No_Honey_Under_12m',
     'Honey must never be given to infants under 12 months due to the risk of infant botulism.',
     'food_safety', NULL, NULL, TRUE,
     'No honey before 12 months.',
     'https://www.cdc.gov/botulism/'),

    ('R596', 'Food_Sequence_VPC',
     'Eating vegetables first, protein second and carbohydrate last lowers the post-meal glucose excursion compared with the reverse order.',
     'behavioural', NULL, NULL, FALSE,
     'Vegetables, then protein, then carbohydrate.',
     NULL)
ON CONFLICT (rule_id) DO NOTHING;
