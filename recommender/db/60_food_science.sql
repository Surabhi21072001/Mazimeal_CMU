-- ============================================================================
--  Sheet 06 · Food Science
--  ingredient_synergy_pairs · ingredient_bioavailability
--  ingredient_substitutions · glycemic_index_data
--
--  ~50K rows total. Read-heavy reference data on the recipe-scoring hot path;
--  loaded into Redis at startup. Not partitioned in either mode.
--
--  This domain is what differentiates the product: it encodes that vitamin C
--  triples non-heme iron absorption, that rested crushed garlic yields far more
--  allicin, and that cooked-then-cooled rice has materially lower GI.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- ingredient_synergy_pairs · ~5K bidirectional pairs
--
-- The pair (A,B) is identical to (B,A). Storing both directions would double
-- the table and let the two rows drift apart, so a single canonical row is
-- stored and 90_indexes.sql enforces uniqueness on
-- (LEAST(a,b), GREATEST(a,b)). Reads must therefore match on either column:
--     WHERE ingredient_id_a = $1 OR ingredient_id_b = $1
-- ---------------------------------------------------------------------------
CREATE TABLE public.ingredient_synergy_pairs (
    synergy_id           UUID          NOT NULL DEFAULT public.gen_ulid(),
    ingredient_id_a      UUID          NOT NULL,
    ingredient_id_b      UUID          NOT NULL,
    synergy_type         VARCHAR(60)   NOT NULL,
    affected_nutrient_id VARCHAR(40),
    effect_multiplier    DECIMAL(6,3)  NOT NULL,
    effect_description   TEXT          NOT NULL,
    preparation_required VARCHAR(200),
    rule_id              VARCHAR(30),
    evidence_level       VARCHAR(30)   NOT NULL,
    source               TEXT,

    CONSTRAINT pk_ingredient_synergy_pairs PRIMARY KEY (synergy_id),
    CONSTRAINT ck_syn_not_self   CHECK (ingredient_id_a <> ingredient_id_b),
    CONSTRAINT ck_syn_multiplier CHECK (effect_multiplier > 0),
    CONSTRAINT ck_syn_evidence   CHECK (evidence_level IN ('strong', 'moderate', 'emerging'))
);

COMMENT ON COLUMN public.ingredient_synergy_pairs.synergy_type       IS 'absorption_boost | antioxidant | glycemic_reduction ...';
COMMENT ON COLUMN public.ingredient_synergy_pairs.effect_multiplier  IS '3.0 = 3x non-heme iron absorption; 20.0 = curcumin with piperine.';
COMMENT ON COLUMN public.ingredient_synergy_pairs.effect_description IS 'User-facing synergy tip rendered in the recipe UI.';

-- ---------------------------------------------------------------------------
-- ingredient_bioavailability · ~10K rows · prep method x absorption
-- ---------------------------------------------------------------------------
CREATE TABLE public.ingredient_bioavailability (
    bioavail_id          UUID          NOT NULL DEFAULT public.gen_ulid(),
    ingredient_id        UUID          NOT NULL,
    prep_method          VARCHAR(80)   NOT NULL,
    affected_nutrient_id VARCHAR(40)   NOT NULL,
    bioavailability_pct  DECIMAL(5,2)  NOT NULL,
    vs_baseline_pct      DECIMAL(5,2),
    prep_instruction     TEXT          NOT NULL,
    rule_id              VARCHAR(30),
    evidence_level       VARCHAR(30)   NOT NULL,

    CONSTRAINT pk_ingredient_bioavailability PRIMARY KEY (bioavail_id),
    -- The sheet's unique index is (ingredient_id, prep_method), but a single
    -- prep method can affect more than one nutrient (steaming changes both
    -- folate and lycopene), so the nutrient is included in the key.
    CONSTRAINT uq_ib_ing_prep_nut UNIQUE (ingredient_id, prep_method, affected_nutrient_id),
    CONSTRAINT ck_ib_pct      CHECK (bioavailability_pct BETWEEN 0 AND 100),
    CONSTRAINT ck_ib_evidence CHECK (evidence_level IN ('strong', 'moderate', 'emerging'))
);

COMMENT ON COLUMN public.ingredient_bioavailability.prep_method      IS 'raw | steamed | boiled | crushed_rested_10min ...';
COMMENT ON COLUMN public.ingredient_bioavailability.prep_instruction IS 'Copied into recipe_steps at generation time.';
COMMENT ON COLUMN public.ingredient_bioavailability.vs_baseline_pct  IS 'Relative change against the raw/boiled baseline for this nutrient.';

-- ---------------------------------------------------------------------------
-- ingredient_substitutions · ~15K rows
-- ---------------------------------------------------------------------------
CREATE TABLE public.ingredient_substitutions (
    substitution_id          UUID          NOT NULL DEFAULT public.gen_ulid(),
    original_ingredient_id   UUID          NOT NULL,
    substitute_ingredient_id UUID          NOT NULL,
    reason_type              VARCHAR(50)   NOT NULL,
    condition_code           VARCHAR(20),
    nutrient_equivalence_pct DECIMAL(5,2),
    ratio                    DECIMAL(6,3)  NOT NULL DEFAULT 1.0,
    notes                    TEXT,
    rule_id                  VARCHAR(30),

    CONSTRAINT pk_ingredient_substitutions PRIMARY KEY (substitution_id),
    CONSTRAINT uq_is_pair_reason UNIQUE (original_ingredient_id, substitute_ingredient_id, reason_type),
    CONSTRAINT ck_is_not_self CHECK (original_ingredient_id <> substitute_ingredient_id),
    CONSTRAINT ck_is_reason   CHECK (reason_type IN
        ('allergen', 'dietary_pref', 'medical_condition', 'vegan')),
    CONSTRAINT ck_is_ratio    CHECK (ratio > 0),
    CONSTRAINT ck_is_equiv    CHECK (nutrient_equivalence_pct IS NULL
                                     OR nutrient_equivalence_pct BETWEEN 0 AND 100)
);

COMMENT ON COLUMN public.ingredient_substitutions.ratio IS '1.0 = 1:1 swap; 0.75 = use 75% of the original quantity.';
COMMENT ON COLUMN public.ingredient_substitutions.notes IS 'User-facing caveat, e.g. "lower in protein — add a supplement".';

-- ---------------------------------------------------------------------------
-- glycemic_index_data · ~20K rows · supports the R11 retrogradation rule
--
-- prep_method is the point of this table: cooked_cooled and
-- cooked_cooled_reheated raise resistant starch and drop effective GI by
-- roughly half for the same ingredient.
-- ---------------------------------------------------------------------------
CREATE TABLE public.glycemic_index_data (
    gi_id                UUID          NOT NULL DEFAULT public.gen_ulid(),
    ingredient_id        UUID          NOT NULL,
    prep_method          VARCHAR(80)   NOT NULL,
    glycemic_index       SMALLINT,
    glycemic_load        DECIMAL(6,2),
    resistant_starch_pct DECIMAL(5,2),
    notes                TEXT,

    CONSTRAINT pk_glycemic_index_data PRIMARY KEY (gi_id),
    CONSTRAINT uq_gi_ing_prep UNIQUE (ingredient_id, prep_method),
    CONSTRAINT ck_gi_index    CHECK (glycemic_index IS NULL OR glycemic_index BETWEEN 0 AND 100),
    CONSTRAINT ck_gi_load     CHECK (glycemic_load IS NULL OR glycemic_load >= 0),
    CONSTRAINT ck_gi_rs       CHECK (resistant_starch_pct IS NULL
                                     OR resistant_starch_pct BETWEEN 0 AND 100)
);

COMMENT ON COLUMN public.glycemic_index_data.prep_method          IS 'raw | cooked | cooked_cooled | cooked_cooled_reheated — the key to rule R11.';
COMMENT ON COLUMN public.glycemic_index_data.resistant_starch_pct IS 'Raised by retrogradation (cool then reheat).';
