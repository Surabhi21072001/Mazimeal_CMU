-- ============================================================================
--  Sheet 05 · Ingredients & Nutrition Values   (formerly DB2)
--  ingredients · ingredient_nutrition · usda_nutrient_ref · ingredient_attributes
--
--  SCALE: ingredients        -> LIST(food_category), 16 partitions
--         ingredient_nutrition -> HASH(ingredient_id), 16 partitions (~30M rows)
--
--  The LIST partition on food_category is the riskiest choice in sheet 09.
--  A LIST partition needs its value set declared up front, so every food
--  category must exist as a partition before any row using it can be inserted,
--  and a new USDA food group means a DDL change in production. 91_partitions.sql
--  therefore creates a DEFAULT partition as a safety net and 94_maintenance.sql
--  ships a check that flags rows that landed in it.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- data_sources · where ingredient data comes from
--
-- One row per upstream database (USDA SR Legacy today, CNF / AUSNUT / Fineli
-- later) plus one for our own estimates. Every nutrient value, measure and
-- match points at one of these, so attribution and licence are a join away
-- and a second source slots in without touching the fact tables.
-- precedence: lower wins when two sources give a value for the same nutrient.
-- ---------------------------------------------------------------------------
CREATE TABLE public.data_sources (
    source_id         VARCHAR(30)   NOT NULL,
    source_name       VARCHAR(120)  NOT NULL,
    publisher         VARCHAR(120),
    region            VARCHAR(60),
    release           VARCHAR(40),
    licence           VARCHAR(120),
    attribution_text  TEXT,
    url               TEXT,
    precedence        SMALLINT      NOT NULL,
    ingested_at       DATE,

    CONSTRAINT pk_data_sources PRIMARY KEY (source_id),
    CONSTRAINT uq_data_sources_precedence UNIQUE (precedence)
);

INSERT INTO public.data_sources VALUES
    ('usda_sr_legacy', 'USDA FoodData Central, SR Legacy', 'USDA Agricultural Research Service', 'United States',
     '2018-04 (FDC release 2019-04)', 'CC0 1.0 (public domain)',
     'U.S. Department of Agriculture, Agricultural Research Service. FoodData Central, SR Legacy. fdc.nal.usda.gov',
     'https://fdc.nal.usda.gov/', 10, '2026-09-08'),
    ('foodcom', 'Food.com recipes (Kaggle)', 'Food.com via Kaggle', 'United States',
     'irkaal/foodcom-recipes-and-reviews', 'scraped dataset; check terms before shipping',
     'Recipes and per-serving nutrition from Food.com', 'https://www.kaggle.com/datasets/irkaal/foodcom-recipes-and-reviews', 50, '2026-09-08'),
    ('mazi_estimate', 'MaziMeal estimate', 'MaziMeal', NULL, NULL, NULL,
     'Estimated by MaziMeal when no source publishes a value', NULL, 90, NULL);

-- ---------------------------------------------------------------------------
-- ingredients · ~1M rows · USDA FDC + Open Food Facts
-- ---------------------------------------------------------------------------
CREATE TABLE public.ingredients (
    ingredient_id           UUID          NOT NULL DEFAULT public.gen_ulid(),
    usda_fdc_id             BIGINT,
    ingredient_name         VARCHAR(200)  NOT NULL,
    ingredient_name_aliases TEXT[],
    food_category           VARCHAR(80)   NOT NULL,
    is_allergen             BOOLEAN       NOT NULL DEFAULT FALSE,
    allergen_type           VARCHAR(50),
    is_pet_toxic            BOOLEAN       NOT NULL DEFAULT FALSE,
    pet_toxic_notes         TEXT,
    typical_serving_g       DECIMAL(8,2),
    default_measure         VARCHAR(40),
    data_source             VARCHAR(50)   NOT NULL DEFAULT 'USDA',
    created_at              TIMESTAMPTZ   NOT NULL DEFAULT now(),

    CONSTRAINT pk_ingredients   PRIMARY KEY (:pk_ingredients),
    CONSTRAINT ck_ing_source    CHECK (data_source IN
        ('USDA', 'Open Food Facts', 'Nutritionix', 'Manual')),
    CONSTRAINT ck_ing_serving   CHECK (typical_serving_g IS NULL OR typical_serving_g > 0),
    -- An allergen row without a type cannot be matched against a member's
    -- allergy, which is the one failure mode with clinical consequences.
    CONSTRAINT ck_ing_allergen  CHECK (NOT is_allergen OR allergen_type IS NOT NULL),
    CONSTRAINT ck_ing_pet_toxic CHECK (NOT is_pet_toxic OR pet_toxic_notes IS NOT NULL)
) :part_ingredients ;

COMMENT ON COLUMN public.ingredients.usda_fdc_id             IS 'USDA FoodData Central id. NULL for manual and Open Food Facts entries.';
COMMENT ON COLUMN public.ingredients.ingredient_name_aliases IS 'Alternate names and translations. GIN-indexed for ANY() lookup.';
COMMENT ON COLUMN public.ingredients.food_category           IS 'USDA food group. SCALE: LIST partition key — see 91_partitions.sql.';
COMMENT ON COLUMN public.ingredients.is_allergen             IS 'Top-14 allergen flag. Partially indexed — only allergen rows.';
COMMENT ON COLUMN public.ingredients.is_pet_toxic            IS 'Onion, grapes, chocolate, xylitol. Surfaced when households.has_pets.';

-- ---------------------------------------------------------------------------
-- ingredient_nutrition · ~30M rows · one row per ingredient x nutrient, /100g
-- ---------------------------------------------------------------------------
CREATE TABLE public.ingredient_nutrition (
    nutrition_id          UUID           NOT NULL DEFAULT public.gen_ulid(),
    ingredient_id         UUID           NOT NULL,
    nutrient_id           VARCHAR(40)    NOT NULL,
    value_per_100g        DECIMAL(12,4)  NOT NULL,
    unit                  VARCHAR(20)    NOT NULL,
    bioavailability_pct   DECIMAL(5,2),
    bioavailability_notes TEXT,
    usda_nutrient_code    VARCHAR(20),
    data_quality_flag     VARCHAR(20)    NOT NULL DEFAULT 'standard',
    source_id             VARCHAR(30)    NOT NULL DEFAULT 'usda_sr_legacy',

    CONSTRAINT pk_ingredient_nutrition PRIMARY KEY (:pk_ing_nutrition),
    -- one value per nutrient per source; v_ingredient_nutrition picks by precedence
    CONSTRAINT uq_in_ing_nut  UNIQUE (ingredient_id, nutrient_id, source_id),
    CONSTRAINT ck_in_value    CHECK (value_per_100g >= 0),
    CONSTRAINT ck_in_bioavail CHECK (bioavailability_pct IS NULL
                                     OR bioavailability_pct BETWEEN 0 AND 100),
    CONSTRAINT ck_in_quality  CHECK (data_quality_flag IN ('standard', 'estimated', 'measured'))
) :part_ing_nutrition ;

COMMENT ON COLUMN public.ingredient_nutrition.value_per_100g      IS 'Raw USDA value per 100g. Recipe totals scale this by recipe_ingredients.quantity_g.';
COMMENT ON COLUMN public.ingredient_nutrition.bioavailability_pct IS 'Baseline absorbed fraction, e.g. non-heme iron 5-10%. Prep-specific values live in ingredient_bioavailability.';
COMMENT ON COLUMN public.ingredient_nutrition.source_id           IS 'Which data_sources row this value came from.';

-- ---------------------------------------------------------------------------
-- ingredient_measures · household measures and their weight in grams
--
-- "1 cup flour" is 125 g, "1 large egg" 50 g, "1 clove garlic" 3 g. Loaded
-- from USDA food_portion for the matched food; fallback rows are constants
-- for measures USDA doesn't publish. Recipe lines convert to grams through
-- this table, so a swap or a scaled amount recalculates nutrition.
-- ---------------------------------------------------------------------------
CREATE TABLE public.ingredient_measures (
    ingredient_id      UUID          NOT NULL,
    measure            VARCHAR(40)   NOT NULL,
    gram_weight        DECIMAL(8,2)  NOT NULL,
    source_id          VARCHAR(30)   NOT NULL DEFAULT 'usda_sr_legacy',
    source_portion_id  BIGINT,

    CONSTRAINT pk_ingredient_measures PRIMARY KEY (ingredient_id, measure),
    CONSTRAINT ck_im_grams CHECK (gram_weight > 0)
);

COMMENT ON TABLE  public.ingredient_measures                   IS 'Grams per one household measure of an ingredient. Source rows come from USDA food_portion; fallback rows are estimates.';
COMMENT ON COLUMN public.ingredient_measures.source_portion_id IS 'USDA food_portion.id when the weight came from USDA.';

-- ---------------------------------------------------------------------------
-- ingredient_source_map · which record in which upstream database an
-- ingredient was matched to. One row per ingredient per source.
-- ---------------------------------------------------------------------------
CREATE TABLE public.ingredient_source_map (
    ingredient_id       UUID          NOT NULL,
    source_id           VARCHAR(30)   NOT NULL,
    source_record_id    VARCHAR(60)   NOT NULL,
    source_description  TEXT,
    match_score         SMALLINT,
    matched_by          VARCHAR(20)   NOT NULL DEFAULT 'fuzzy',
    matched_at          DATE          NOT NULL DEFAULT current_date,

    CONSTRAINT pk_ingredient_source_map PRIMARY KEY (ingredient_id, source_id),
    CONSTRAINT ck_ism_matched_by CHECK (matched_by IN ('fuzzy', 'alias', 'manual'))
);

COMMENT ON TABLE public.ingredient_source_map IS 'Provenance: the upstream record each ingredient maps to, per source. source_record_id is the FDC id for USDA.';

-- ---------------------------------------------------------------------------
-- v_ingredient_nutrition · one value per ingredient and nutrient, from the
-- highest-precedence source that has one. Everything that calculates
-- nutrition reads this, never ingredient_nutrition directly.
-- ---------------------------------------------------------------------------
CREATE VIEW public.v_ingredient_nutrition AS
SELECT DISTINCT ON (n.ingredient_id, n.nutrient_id)
       n.ingredient_id, n.nutrient_id, n.value_per_100g, n.unit,
       n.bioavailability_pct, n.data_quality_flag, n.source_id
FROM   public.ingredient_nutrition n
JOIN   public.data_sources s ON s.source_id = n.source_id
ORDER  BY n.ingredient_id, n.nutrient_id, s.precedence;

-- ---------------------------------------------------------------------------
-- usda_nutrient_ref · ~300 rows · USDA code <-> internal nutrient_id
-- ---------------------------------------------------------------------------
CREATE TABLE public.usda_nutrient_ref (
    usda_nutrient_id   VARCHAR(20)    NOT NULL,
    nutrient_id        VARCHAR(40)    NOT NULL,
    usda_nutrient_name VARCHAR(150)   NOT NULL,
    usda_unit          VARCHAR(20)    NOT NULL,
    conversion_factor  DECIMAL(10,6)  NOT NULL DEFAULT 1.0,

    CONSTRAINT pk_usda_nutrient_ref PRIMARY KEY (usda_nutrient_id),
    CONSTRAINT ck_unr_factor CHECK (conversion_factor > 0)
);

COMMENT ON TABLE  public.usda_nutrient_ref                   IS 'Import-time mapping table. Fully Redis-cached.';
COMMENT ON COLUMN public.usda_nutrient_ref.conversion_factor IS 'Multiply the USDA value by this to reach the internal unit (e.g. IU -> mcg).';

-- ---------------------------------------------------------------------------
-- ingredient_attributes · ~2M rows · dietary flags, prep tags, cultural labels
-- ---------------------------------------------------------------------------
CREATE TABLE public.ingredient_attributes (
    attr_id         UUID         NOT NULL DEFAULT public.gen_ulid(),
    ingredient_id   UUID         NOT NULL,
    attribute_type  VARCHAR(50)  NOT NULL,
    attribute_value VARCHAR(100) NOT NULL,
    rule_id         VARCHAR(30),

    CONSTRAINT pk_ingredient_attributes PRIMARY KEY (attr_id),
    CONSTRAINT uq_ia_triplet UNIQUE (ingredient_id, attribute_type, attribute_value),
    CONSTRAINT ck_ia_type CHECK (attribute_type IN
        ('dietary_restriction', 'food_property', 'prep_method', 'cultural_tag'))
);

COMMENT ON COLUMN public.ingredient_attributes.attribute_value IS 'vegan | high_oxalate | raw_optimal | kosher ...';
COMMENT ON COLUMN public.ingredient_attributes.rule_id         IS 'Optional link into the rule engine (nutrient_rules).';
