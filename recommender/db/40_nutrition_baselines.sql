-- ============================================================================
--  Sheet 04 · Nutrition Baselines, Targets & Master Tables
--  categories · nutrients_master · profile_nutrient_baselines
--  profile_nutrient_targets
--
--  The computation chain this domain exists to serve:
--
--    household_members (age, sex)  ->  categories.category_id (C001-C021)
--    categories + nutrients_master ->  profile_nutrient_baselines (USDA DRI)
--    baseline + nutrient_modifiers ->  profile_nutrient_targets (final value)
--
--  The last step is asynchronous: a member profile UPDATE fires pg_notify,
--  which enqueues nutrient-target-recompute. Targets are never computed inline
--  on a request.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- categories · C001-C021 · age + sex groups · <100 rows, fully cached
-- ---------------------------------------------------------------------------
CREATE TABLE public.categories (
    category_id   VARCHAR(10) NOT NULL,
    category_name VARCHAR(80) NOT NULL,
    age_group     VARCHAR(20) NOT NULL,
    sex           CHAR(1)     NOT NULL,
    description   TEXT,

    CONSTRAINT pk_categories      PRIMARY KEY (category_id),
    CONSTRAINT uq_categories_name UNIQUE (category_name),
    -- One category per (age_group, sex) pair — the derivation must be unambiguous.
    CONSTRAINT uq_categories_grp  UNIQUE (age_group, sex),
    CONSTRAINT ck_categories_code CHECK (category_id ~ '^C[0-9]{3}$'),
    CONSTRAINT ck_categories_sex  CHECK (sex IN ('M', 'F'))
);

COMMENT ON TABLE  public.categories           IS 'USDA DRI age/sex bands. C001 = newborn F ... C016 = early adult F.';
COMMENT ON COLUMN public.categories.age_group IS 'Human-readable band: 0-6m, 1-3y, 19-50y.';

-- ---------------------------------------------------------------------------
-- nutrients_master · 25+ core nutrients
-- nutrient_id is the shared key joining this domain to ingredients, food
-- science, targets and daily logs. It is a readable string, not a surrogate.
-- ---------------------------------------------------------------------------
CREATE TABLE public.nutrients_master (
    nutrient_id       VARCHAR(40)  NOT NULL,
    nutrient_name     VARCHAR(100) NOT NULL,
    nutrient_category VARCHAR(50)  NOT NULL,
    default_unit      VARCHAR(20)  NOT NULL,
    usda_nutrient_code VARCHAR(20),
    phase             VARCHAR(20)  NOT NULL DEFAULT 'MVP',
    notes             TEXT,

    CONSTRAINT pk_nutrients_master PRIMARY KEY (nutrient_id),
    CONSTRAINT uq_nm_name  UNIQUE (nutrient_name),
    CONSTRAINT ck_nm_cat   CHECK (nutrient_category IN
        ('Macro', 'Fat-soluble', 'Water-soluble', 'Mineral', 'Other')),
    CONSTRAINT ck_nm_phase CHECK (phase IN ('MVP', 'Phase2'))
);

COMMENT ON COLUMN public.nutrients_master.nutrient_id IS 'Cross-domain shared key: Macro_Protein, Vitamin_D, Folate.';
COMMENT ON COLUMN public.nutrients_master.phase       IS 'MVP = core 25 nutrients. Phase2 = polyphenols and extended set.';

-- ---------------------------------------------------------------------------
-- profile_nutrient_baselines · ~25K rows · USDA DRI per category x nutrient
-- ---------------------------------------------------------------------------
CREATE TABLE public.profile_nutrient_baselines (
    baseline_id           UUID          NOT NULL DEFAULT public.gen_ulid(),
    category_id           VARCHAR(10)   NOT NULL,
    nutrient_id           VARCHAR(40)   NOT NULL,
    baseline_value        DECIMAL(10,4) NOT NULL,
    unit                  VARCHAR(20)   NOT NULL,
    per                   VARCHAR(10)   NOT NULL,
    lower_threshold_meal  DECIMAL(10,4),
    upper_threshold_day   DECIMAL(10,4),
    upper_threshold_meal  DECIMAL(10,4),
    source_url            TEXT,
    short_description     VARCHAR(250),
    long_description      TEXT,
    evidence_summary      TEXT,

    CONSTRAINT pk_profile_nutrient_baselines PRIMARY KEY (baseline_id),
    -- One baseline per category+nutrient. The sheet indexes this pair; without
    -- a UNIQUE constraint duplicate DRI rows silently double a target.
    CONSTRAINT uq_pnb_cat_nut UNIQUE (category_id, nutrient_id),
    CONSTRAINT ck_pnb_per     CHECK (per IN ('Day', 'Meal', 'Week')),
    CONSTRAINT ck_pnb_value   CHECK (baseline_value >= 0),
    CONSTRAINT ck_pnb_meal_band CHECK (
        lower_threshold_meal IS NULL OR upper_threshold_meal IS NULL
        OR lower_threshold_meal <= upper_threshold_meal)
);

COMMENT ON COLUMN public.profile_nutrient_baselines.upper_threshold_day IS 'Tolerable upper intake per day, e.g. the ~20g single-sitting protein cap.';

-- ---------------------------------------------------------------------------
-- profile_nutrient_targets · ~125M rows @ 1M users
-- SCALE: HASH(member_id) x16 · Redis nt:{member_id} HASH, TTL 300s
--
-- The workbook labels this "MATERIALIZED VIEW or table". It is built as a TABLE
-- here, deliberately: a Postgres MATERIALIZED VIEW can only be refreshed in
-- full, and refreshing 125M rows because one member edited their profile is not
-- viable. Per-member rows are recomputed by the async job instead.
-- ---------------------------------------------------------------------------
CREATE TABLE public.profile_nutrient_targets (
    target_id          UUID          NOT NULL DEFAULT public.gen_ulid(),
    member_id          UUID          NOT NULL,
    nutrient_id        VARCHAR(40)   NOT NULL,
    final_target_value DECIMAL(10,4) NOT NULL,
    unit               VARCHAR(20)   NOT NULL,
    per                VARCHAR(10)   NOT NULL,
    applied_rules_csv  TEXT,
    computed_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),

    CONSTRAINT pk_profile_nutrient_targets PRIMARY KEY (:pk_pnt),
    CONSTRAINT uq_pnt_member_nut UNIQUE (member_id, nutrient_id),
    CONSTRAINT ck_pnt_per        CHECK (per IN ('Day', 'Meal')),
    CONSTRAINT ck_pnt_value      CHECK (final_target_value >= 0)
) :part_pnt ;

COMMENT ON TABLE  public.profile_nutrient_targets                    IS 'Baseline DRI with every applicable modifier applied. Recomputed async, never inline.';
COMMENT ON COLUMN public.profile_nutrient_targets.applied_rules_csv  IS 'Audit trail of contributing rule_ids — required to explain a target to a dietitian.';
COMMENT ON COLUMN public.profile_nutrient_targets.computed_at        IS 'Stale when older than household_members.updated_at.';
