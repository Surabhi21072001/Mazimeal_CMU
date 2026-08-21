-- 04_nutrition_rules.sql
-- Clinical and food science rules. From the schema doc, sheet 03.
--
-- Named nutrition_rules to match our task list. The doc calls it
-- nutrient_rules, worth confirming which we keep.
-- Table names are lowercase since Postgres lowercases them anyway.
--
-- applies_to_category, applies_to_condition and document_id point at tables we
-- haven't built yet. Columns are here so the data can go in; foreign keys get
-- added later (see bottom of file).

CREATE TABLE IF NOT EXISTS nutrition_rules (
    -- Readable id from the doc (R001, R085, R596) rather than a UUID.
    rule_id              VARCHAR(30)  NOT NULL,

    rule_name            VARCHAR(150) NOT NULL,
    rule_description     TEXT         NOT NULL,
    rule_type            VARCHAR(50)  NOT NULL,

    applies_to_category  VARCHAR(10),   -- FK later
    applies_to_condition VARCHAR(20),   -- FK later

    is_hard_constraint   BOOLEAN      NOT NULL DEFAULT FALSE,

    document_id          VARCHAR(20),   -- FK later
    short_description    VARCHAR(250),
    evidence_summary     TEXT,
    source               TEXT,

    created_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT pk_nutrition_rules PRIMARY KEY (rule_id),

    -- Catches the same rule being entered twice.
    CONSTRAINT uq_nutrition_rules_name UNIQUE (rule_name),

    CONSTRAINT ck_nutrition_rules_type CHECK (rule_type IN
        ('nutrient_threshold', 'food_safety', 'behavioural', 'prep_method', 'allergy')),

    -- Hard rules block a recipe outright, so they need a source.
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

-- Hard rules get pulled as a set, and there aren't many of them.
CREATE INDEX IF NOT EXISTS idx_nutrition_rules_hard
    ON nutrition_rules (rule_id)
    WHERE is_hard_constraint;

-- ---------------------------------------------------------------------------
-- Documentation
-- ---------------------------------------------------------------------------
COMMENT ON TABLE  nutrition_rules                    IS 'Clinical and food science rules. Doc calls this nutrient_rules.';
COMMENT ON COLUMN nutrition_rules.rule_id            IS 'R001, R085, R596 etc.';
COMMENT ON COLUMN nutrition_rules.is_hard_constraint IS 'Always enforced, never overridable. Needs a source.';

-- Add these once categories, conditions and documents exist:
--  ALTER TABLE nutrition_rules ADD CONSTRAINT fk_nr_category
--      FOREIGN KEY (applies_to_category)  REFERENCES categories (category_id);
--  ALTER TABLE nutrition_rules ADD CONSTRAINT fk_nr_condition
--      FOREIGN KEY (applies_to_condition) REFERENCES conditions (condition_code);
--  ALTER TABLE nutrition_rules ADD CONSTRAINT fk_nr_document
--      FOREIGN KEY (document_id)          REFERENCES documents (document_id);
-- ---------------------------------------------------------------------------

-- The five rules named in the doc, so the table isn't empty.
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
