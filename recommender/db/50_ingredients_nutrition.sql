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

    CONSTRAINT pk_ingredient_nutrition PRIMARY KEY (:pk_ing_nutrition),
    CONSTRAINT uq_in_ing_nut  UNIQUE (ingredient_id, nutrient_id),
    CONSTRAINT ck_in_value    CHECK (value_per_100g >= 0),
    CONSTRAINT ck_in_bioavail CHECK (bioavailability_pct IS NULL
                                     OR bioavailability_pct BETWEEN 0 AND 100),
    CONSTRAINT ck_in_quality  CHECK (data_quality_flag IN ('standard', 'estimated', 'measured'))
) :part_ing_nutrition ;

COMMENT ON COLUMN public.ingredient_nutrition.value_per_100g      IS 'Raw USDA value per 100g. Recipe totals scale this by recipe_ingredients.quantity.';
COMMENT ON COLUMN public.ingredient_nutrition.bioavailability_pct IS 'Baseline absorbed fraction, e.g. non-heme iron 5-10%. Prep-specific values live in ingredient_bioavailability.';

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
