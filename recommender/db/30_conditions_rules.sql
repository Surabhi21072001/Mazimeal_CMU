-- ============================================================================
--  Sheet 03 · Conditions & Rule Engine
--  conditions · condition_attributes · nutrient_rules · nutrient_modifiers
--  documents
--
--  ~5K rows total. Read-mostly reference data, loaded into Redis at startup
--  (rules:all, conditions:all — 6h TTL, Pub/Sub invalidation on admin update).
--  None of these tables are partitioned in either build mode.
--
--  NAMING WARNING: nutrient_rules.rule_id and nutrient_modifiers.rule_id are
--  DIFFERENT identifier spaces with different formats (R001 vs
--  PROT_ACT_F_HIGH_001) and no FK between them. The workbook reuses the column
--  name for both. Renaming nutrient_modifiers.rule_id to modifier_id would be
--  the right fix; it is left as-is here so the DDL matches the sheet, but the
--  team should decide before any code depends on it.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- conditions · ~200 rows · C001 = Type II Diabetes, C002 = Iron Deficiency ...
-- ---------------------------------------------------------------------------
CREATE TABLE public.conditions (
    condition_code     VARCHAR(20)  NOT NULL,
    condition_name     VARCHAR(100) NOT NULL,
    condition_category VARCHAR(80)  NOT NULL,
    requires_dietitian BOOLEAN      NOT NULL DEFAULT FALSE,
    hipaa_sensitive    BOOLEAN      NOT NULL DEFAULT TRUE,

    CONSTRAINT pk_conditions      PRIMARY KEY (condition_code),
    CONSTRAINT uq_conditions_name UNIQUE (condition_name),
    CONSTRAINT ck_conditions_code CHECK (condition_code ~ '^C[0-9]{3,}$')
);

COMMENT ON COLUMN public.conditions.condition_category IS 'metabolic | cardiovascular | GI | autoimmune | reproductive | ...';
COMMENT ON COLUMN public.conditions.requires_dietitian IS 'Gate: complex conditions must not be auto-planned without human review.';

-- ---------------------------------------------------------------------------
-- condition_attributes · ~500 rows
-- ---------------------------------------------------------------------------
CREATE TABLE public.condition_attributes (
    attribute_id         VARCHAR(20)  NOT NULL,
    condition_code       VARCHAR(20)  NOT NULL,
    attribute_name       VARCHAR(150) NOT NULL,
    attribute_type       VARCHAR(50)  NOT NULL,
    attribute_value      VARCHAR(100),
    is_ai_guidance       BOOLEAN      NOT NULL DEFAULT TRUE,
    dietitian_selectable BOOLEAN      NOT NULL DEFAULT FALSE,
    document_id          VARCHAR(20),

    CONSTRAINT pk_condition_attributes PRIMARY KEY (attribute_id),
    CONSTRAINT ck_ca_type CHECK (attribute_type IN
        ('physiological', 'behavioural', 'pharmacological'))
);

COMMENT ON COLUMN public.condition_attributes.is_ai_guidance IS 'TRUE = trait offered to the AI as context. NEVER a clinical decision.';
COMMENT ON COLUMN public.condition_attributes.document_id    IS 'RAG evidence reference into documents.';

-- ---------------------------------------------------------------------------
-- nutrient_rules · ~2K rows · R001 ... R596 plus condition-specific rules
-- The hot path for recipe scoring — fully Redis-cached as rule:{rule_id}.
-- ---------------------------------------------------------------------------
CREATE TABLE public.nutrient_rules (
    rule_id              VARCHAR(30)  NOT NULL,
    rule_name            VARCHAR(150) NOT NULL,
    rule_description     TEXT         NOT NULL,
    rule_type            VARCHAR(50)  NOT NULL,
    applies_to_category  VARCHAR(10),
    applies_to_condition VARCHAR(20),
    is_hard_constraint   BOOLEAN      NOT NULL DEFAULT FALSE,
    document_id          VARCHAR(20),
    short_description    VARCHAR(250),
    evidence_summary     TEXT,
    source               TEXT,

    CONSTRAINT pk_nutrient_rules PRIMARY KEY (rule_id),
    CONSTRAINT ck_nr_type CHECK (rule_type IN
        ('nutrient_threshold', 'food_safety', 'behavioural', 'prep_method', 'allergy'))
);

COMMENT ON COLUMN public.nutrient_rules.applies_to_category IS 'NULL = applies to every age/sex category.';
COMMENT ON COLUMN public.nutrient_rules.is_hard_constraint  IS 'TRUE = always enforced and never overridable (e.g. allergen exclusion).';
COMMENT ON COLUMN public.nutrient_rules.source              IS 'DOI or PubMed URL backing the rule.';

-- ---------------------------------------------------------------------------
-- nutrient_modifiers · ~1K rows
-- Adjustments layered onto a baseline DRI to produce a member's final target.
-- Key format: [NUTRIENT]_[CATEGORY]_[SEX]_[CONDITION]_[SEQ]
-- ---------------------------------------------------------------------------
CREATE TABLE public.nutrient_modifiers (
    rule_id          VARCHAR(40)    NOT NULL,
    nutrient_id      VARCHAR(40)    NOT NULL,
    rule_category    VARCHAR(50)    NOT NULL,
    sex              CHAR(1),
    condition_field  VARCHAR(50),
    condition_value  VARCHAR(100),
    modifier_type    VARCHAR(20)    NOT NULL,
    modifier_value   DECIMAL(10,4)  NOT NULL,
    unit             VARCHAR(20)    NOT NULL,
    priority         SMALLINT       NOT NULL DEFAULT 1,
    status           VARCHAR(20)    NOT NULL DEFAULT 'Draft',
    long_description TEXT,
    evidence_summary TEXT,
    source           TEXT,

    CONSTRAINT pk_nutrient_modifiers PRIMARY KEY (rule_id),
    CONSTRAINT ck_nm_sex      CHECK (sex IS NULL OR sex IN ('M', 'F')),
    CONSTRAINT ck_nm_type     CHECK (modifier_type IN ('Add', 'Subtract', 'Multiply', 'Set')),
    CONSTRAINT ck_nm_status   CHECK (status IN ('Draft', 'Validated', 'Human-in-loop')),
    CONSTRAINT ck_nm_priority CHECK (priority > 0),
    -- Multiply by zero would silently zero out a nutrient target.
    CONSTRAINT ck_nm_multiply CHECK (modifier_type <> 'Multiply' OR modifier_value > 0)
);

COMMENT ON COLUMN public.nutrient_modifiers.sex           IS 'NULL applies to both sexes.';
COMMENT ON COLUMN public.nutrient_modifiers.priority      IS 'Higher value applied first when modifiers conflict.';
COMMENT ON COLUMN public.nutrient_modifiers.status        IS 'Only Validated modifiers should reach production target computation.';

-- ---------------------------------------------------------------------------
-- documents · ~5K rows · RAG corpus
-- embedding_vector VECTOR(1536) is added conditionally in 88_vector.sql.
-- ---------------------------------------------------------------------------
CREATE TABLE public.documents (
    document_id   VARCHAR(20)  NOT NULL,
    title         VARCHAR(300) NOT NULL,
    document_type VARCHAR(40)  NOT NULL,
    url           TEXT,
    rule_id_tags  TEXT,
    category_tags TEXT,

    CONSTRAINT pk_documents PRIMARY KEY (document_id),
    CONSTRAINT ck_doc_type CHECK (document_type IN
        ('peer_review', 'USDA', 'clinical_guideline', 'AI_doc'))
);

COMMENT ON COLUMN public.documents.rule_id_tags IS 'CSV of rule_ids this document supports. Denormalised for RAG recall; not an FK.';
