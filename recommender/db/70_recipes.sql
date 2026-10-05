-- ============================================================================
--  Sheet 07 · Recipes, Videos & Cultural Categories   (formerly DB3)
--  cultural_categories · recipes · recipe_ingredients · recipe_steps
--  recipe_videos · recipe_rules_map
--
--  SCALE: recipes -> LIST(data_source), 5 partitions
--         (USDA | Open_Food_Facts | Manual | AI_generated)
--
--  NAME COLLISION: cultural_categories.category_id (UUID) and
--  categories.category_id (VARCHAR(10), C001-C021) are unrelated keys sharing a
--  column name across domains. recipes.cultural_category_id disambiguates on
--  the referencing side; the reference side should be renamed to
--  cultural_category_id before this reaches application code.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- cultural_categories · ~100 rows · regional cuisine tags
-- ---------------------------------------------------------------------------
CREATE TABLE public.cultural_categories (
    category_id   UUID         NOT NULL DEFAULT public.gen_ulid(),
    category_name VARCHAR(100) NOT NULL,
    region        VARCHAR(100),
    style_tags    TEXT[],
    cuisine_notes TEXT,

    CONSTRAINT pk_cultural_categories PRIMARY KEY (category_id),
    CONSTRAINT uq_cc_name UNIQUE (category_name)
);

COMMENT ON COLUMN public.cultural_categories.style_tags    IS 'quick_easy | comfort_food | family_friendly. GIN-indexed.';
COMMENT ON COLUMN public.cultural_categories.cuisine_notes IS 'Free-text context handed to the AI for personalisation.';

-- ---------------------------------------------------------------------------
-- recipes · ~500K rows
-- embedding_vector VECTOR(1536) is added conditionally in 88_vector.sql.
-- ---------------------------------------------------------------------------
CREATE TABLE public.recipes (
    recipe_id               UUID          NOT NULL DEFAULT public.gen_ulid(),
    external_source_id      VARCHAR(100),
    recipe_name             VARCHAR(300)  NOT NULL,
    recipe_description      TEXT,
    prep_time_min           SMALLINT,
    cook_time_min           SMALLINT,
    difficulty_level        VARCHAR(20),
    servings                SMALLINT      NOT NULL DEFAULT 4,
    calories_per_serving    DECIMAL(8,2),
    glycemic_index_estimate DECIMAL(5,2),
    cultural_category_id    UUID,
    regional_origin         VARCHAR(100),
    meal_category           VARCHAR(20),
    dietary_tags            TEXT[],
    data_source             VARCHAR(80)   NOT NULL DEFAULT 'USDA',
    is_ai_generated         BOOLEAN       NOT NULL DEFAULT FALSE,
    active_rule_ids_csv     TEXT,
    created_at              TIMESTAMPTZ   NOT NULL DEFAULT now(),
    deleted_at              TIMESTAMPTZ,

    CONSTRAINT pk_recipes      PRIMARY KEY (:pk_recipes),
    CONSTRAINT ck_rec_source   CHECK (data_source IN
        ('USDA', 'Open_Food_Facts', 'Manual', 'AI_generated', 'Food.com')),
    CONSTRAINT ck_rec_meal     CHECK (meal_category IS NULL
                                      OR meal_category IN ('Breakfast', 'Lunch', 'Dinner', 'Snack')),
    CONSTRAINT ck_rec_diff     CHECK (difficulty_level IS NULL
                                      OR difficulty_level IN ('Easy', 'Medium', 'Hard')),
    CONSTRAINT ck_rec_servings CHECK (servings > 0),
    CONSTRAINT ck_rec_prep     CHECK (prep_time_min IS NULL OR prep_time_min >= 0),
    CONSTRAINT ck_rec_cook     CHECK (cook_time_min IS NULL OR cook_time_min >= 0),
    CONSTRAINT ck_rec_cal      CHECK (calories_per_serving IS NULL OR calories_per_serving >= 0),
    CONSTRAINT ck_rec_gi       CHECK (glycemic_index_estimate IS NULL
                                      OR glycemic_index_estimate BETWEEN 0 AND 100),
    -- The partition key and the boolean must agree, or AI recipes land in the
    -- wrong partition and the "reference data only" filter silently leaks.
    CONSTRAINT ck_rec_ai_flag  CHECK (is_ai_generated = (data_source = 'AI_generated'))
) :part_recipes ;

COMMENT ON COLUMN public.recipes.external_source_id      IS 'Upstream id when imported. Unique among non-NULL values.';
COMMENT ON COLUMN public.recipes.meal_category           IS 'Breakfast | Lunch | Dinner | Snack. Same as the week-1 schema.';
COMMENT ON COLUMN public.recipes.dietary_tags            IS 'vegan, gluten_free, etc.';
COMMENT ON COLUMN public.recipes.glycemic_index_estimate IS 'Carb-weighted average GI. Used to filter recipes for diabetic profiles.';
COMMENT ON COLUMN public.recipes.active_rule_ids_csv     IS 'Denormalised summary of demonstrated rules. recipe_rules_map is the normalised source of truth.';

-- ---------------------------------------------------------------------------
-- recipe_ingredients · ~5M rows
-- ---------------------------------------------------------------------------
CREATE TABLE public.recipe_ingredients (
    line_id          UUID           NOT NULL DEFAULT public.gen_ulid(),
    recipe_id        UUID           NOT NULL,
    ingredient_id    UUID           NOT NULL,
    quantity         DECIMAL(10,3)  NOT NULL,
    unit             VARCHAR(30)    NOT NULL,
    measure          VARCHAR(40),
    quantity_g       DECIMAL(10,2),
    grams_source     VARCHAR(20)    NOT NULL DEFAULT 'none',
    quantity_aligned BOOLEAN,
    preparation_note VARCHAR(200),
    is_optional      BOOLEAN        NOT NULL DEFAULT FALSE,
    can_substitute   BOOLEAN        NOT NULL DEFAULT TRUE,
    synergy_role     VARCHAR(50),
    sequence_order   SMALLINT,

    CONSTRAINT pk_recipe_ingredients PRIMARY KEY (line_id),
    -- one line per ingredient per recipe; also what makes seed loads idempotent
    CONSTRAINT uq_ri_recipe_ingredient UNIQUE (recipe_id, ingredient_id),
    CONSTRAINT ck_ri_quantity CHECK (quantity > 0),
    CONSTRAINT ck_ri_grams    CHECK (quantity_g IS NULL OR quantity_g > 0),
    CONSTRAINT ck_ri_grams_src CHECK (grams_source IN ('manual', 'measure', 'assumed', 'none')),
    CONSTRAINT ck_ri_sequence CHECK (sequence_order IS NULL OR sequence_order > 0)
);

COMMENT ON COLUMN public.recipe_ingredients.quantity_g       IS 'Grams for this line. What nutrition is calculated from. NULL = unknown, never 0.';
COMMENT ON COLUMN public.recipe_ingredients.measure          IS 'Household measure the quantity is in (cup, tbsp, each). Weight comes from ingredient_measures.';
COMMENT ON COLUMN public.recipe_ingredients.grams_source     IS 'manual: entered in grams. measure: quantity x measure weight. assumed: no quantity in the source, 1 measure assumed. none: unknown.';
COMMENT ON COLUMN public.recipe_ingredients.quantity_aligned IS 'Imported recipes only. FALSE when the source quantity list did not line up with its ingredient list, so the number may belong to another line.';

COMMENT ON COLUMN public.recipe_ingredients.synergy_role   IS 'iron_source | vit_c_enhancer | resistant_starch — feeds synergy scoring.';
COMMENT ON COLUMN public.recipe_ingredients.sequence_order IS 'Eating order for rule R596 food sequencing: 1 = vegetables first, 3 = carbohydrates last.';

-- ---------------------------------------------------------------------------
-- recipe_steps · ~3M rows
-- ---------------------------------------------------------------------------
CREATE TABLE public.recipe_steps (
    step_id          UUID         NOT NULL DEFAULT public.gen_ulid(),
    recipe_id        UUID         NOT NULL,
    step_number      SMALLINT     NOT NULL,
    instruction      TEXT         NOT NULL,
    bioavail_rule_id VARCHAR(30),
    duration_min     SMALLINT,
    timing_note      VARCHAR(150),

    CONSTRAINT pk_recipe_steps PRIMARY KEY (step_id),
    CONSTRAINT uq_rs_recipe_step UNIQUE (recipe_id, step_number),
    CONSTRAINT ck_rs_number   CHECK (step_number > 0),
    CONSTRAINT ck_rs_duration CHECK (duration_min IS NULL OR duration_min >= 0)
);

COMMENT ON COLUMN public.recipe_steps.bioavail_rule_id IS 'Bioavailability rule embedded in this step, e.g. "rest garlic 10 min (allicin)".';

-- ---------------------------------------------------------------------------
-- recipe_videos · ~200K rows
-- ---------------------------------------------------------------------------
CREATE TABLE public.recipe_videos (
    video_id         UUID         NOT NULL DEFAULT public.gen_ulid(),
    recipe_id        UUID         NOT NULL,
    platform         VARCHAR(30)  NOT NULL DEFAULT 'YouTube',
    youtube_video_id VARCHAR(20),
    video_url        TEXT         NOT NULL,
    title            VARCHAR(300) NOT NULL,
    channel_name     VARCHAR(150),
    duration_sec     INTEGER,
    language         VARCHAR(10)  NOT NULL DEFAULT 'en',
    is_primary       BOOLEAN      NOT NULL DEFAULT FALSE,

    CONSTRAINT pk_recipe_videos PRIMARY KEY (video_id),
    CONSTRAINT ck_rv_platform CHECK (platform IN ('YouTube', 'Vimeo', 'Internal')),
    CONSTRAINT ck_rv_duration CHECK (duration_sec IS NULL OR duration_sec > 0),
    CONSTRAINT ck_rv_yt_id    CHECK (platform <> 'YouTube'
                                     OR youtube_video_id ~ '^[A-Za-z0-9_-]{11}$')
);

COMMENT ON COLUMN public.recipe_videos.youtube_video_id IS '11-char id. Embed as youtube.com/embed/{id}. Unique among YouTube rows.';
COMMENT ON COLUMN public.recipe_videos.is_primary       IS 'Featured video. 90_indexes.sql enforces at most one per recipe.';

-- ---------------------------------------------------------------------------
-- recipe_rules_map · ~1M rows · which rules each recipe satisfies or triggers
-- ---------------------------------------------------------------------------
CREATE TABLE public.recipe_rules_map (
    map_id           UUID          NOT NULL DEFAULT public.gen_ulid(),
    recipe_id        UUID          NOT NULL,
    rule_id          VARCHAR(30)   NOT NULL,
    rule_satisfied   BOOLEAN       NOT NULL DEFAULT TRUE,
    confidence_score DECIMAL(4,3),
    notes            TEXT,

    CONSTRAINT pk_recipe_rules_map PRIMARY KEY (map_id),
    CONSTRAINT uq_rrm_recipe_rule UNIQUE (recipe_id, rule_id),
    CONSTRAINT ck_rrm_confidence  CHECK (confidence_score IS NULL
                                         OR confidence_score BETWEEN 0 AND 1)
);

COMMENT ON COLUMN public.recipe_rules_map.rule_satisfied   IS 'TRUE = the recipe satisfies the rule. FALSE = it triggers/violates it.';
COMMENT ON COLUMN public.recipe_rules_map.confidence_score IS '0.000-1.000 AI confidence. Low-confidence mappings should not drive hard constraints.';

-- ---------------------------------------------------------------------------
-- recipe_nutrition · per-serving values as published by the source dataset
-- (Food.com gives these directly). Preferred over computing from ingredients
-- when present. FKs in 85_foreign_keys.sql.
-- ---------------------------------------------------------------------------
CREATE TABLE public.recipe_nutrition (
    recipe_id    UUID           NOT NULL,
    nutrient_id  VARCHAR(40)    NOT NULL,
    per_serving  DECIMAL(12,4)  NOT NULL,
    unit         VARCHAR(20)    NOT NULL,
    source       VARCHAR(50)    NOT NULL DEFAULT 'Food.com',

    CONSTRAINT pk_recipe_nutrition PRIMARY KEY (recipe_id, nutrient_id),
    CONSTRAINT ck_rn_value CHECK (per_serving >= 0)
);

COMMENT ON TABLE public.recipe_nutrition IS 'Published per-serving nutrition. Overrides ingredient-derived values in the recommender.';
