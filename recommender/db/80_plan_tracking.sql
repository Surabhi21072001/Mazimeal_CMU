-- ============================================================================
--  Sheet 08 · Meal Planning & Nutrition Tracking
--  household_recipe_plan · profile_recipe_history · nutrient_daily_log
--
--  The highest write-volume domain in the system.
--  SCALE: household_recipe_plan  -> HASH(household_id) x16
--         profile_recipe_history -> HASH(household_id) x16  (co-located, so
--                                    plan-vs-history joins stay on one shard)
--         nutrient_daily_log     -> RANGE(log_date), monthly, 24-month rolling
-- ============================================================================

-- ---------------------------------------------------------------------------
-- household_recipe_plan · ~10M rows · the weekly meal plan
-- ---------------------------------------------------------------------------
CREATE TABLE public.household_recipe_plan (
    plan_id          UUID         NOT NULL DEFAULT public.gen_ulid(),
    household_id     UUID         NOT NULL,
    recipe_id        UUID         NOT NULL,
    planned_date     DATE         NOT NULL,
    meal_type        VARCHAR(20)  NOT NULL,
    servings_planned SMALLINT     NOT NULL DEFAULT 4,
    is_ai_suggested  BOOLEAN      NOT NULL DEFAULT TRUE,
    status           VARCHAR(20)  NOT NULL DEFAULT 'planned',
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT pk_household_recipe_plan PRIMARY KEY (:pk_hrp),
    CONSTRAINT ck_hrp_meal_type CHECK (meal_type IN ('Breakfast', 'Lunch', 'Dinner', 'Snack')),
    CONSTRAINT ck_hrp_status    CHECK (status IN ('planned', 'cooked', 'skipped')),
    CONSTRAINT ck_hrp_servings  CHECK (servings_planned > 0)
) :part_hrp ;

COMMENT ON TABLE  public.household_recipe_plan IS 'Primary query: WHERE household_id = ? AND planned_date BETWEEN ? AND ?. Redis: plan:{household_id}:{week}, TTL 600s.';
COMMENT ON COLUMN public.household_recipe_plan.status IS 'planned -> cooked writes a profile_recipe_history row per eating member.';

-- ---------------------------------------------------------------------------
-- profile_recipe_history · ~50M rows after one year @ 1M users
--
-- Per-member consumption log. nutrient_snapshot is JSONB by design: the
-- nutrient set expands from the MVP 25 to the Phase 2 polyphenol list without a
-- migration, and the values are frozen at eat-time rather than recomputed from
-- a recipe that may since have changed.
-- ---------------------------------------------------------------------------
CREATE TABLE public.profile_recipe_history (
    history_id        UUID          NOT NULL DEFAULT public.gen_ulid(),
    member_id         UUID          NOT NULL,
    household_id      UUID          NOT NULL,
    recipe_id         UUID,
    eaten_at          TIMESTAMPTZ   NOT NULL,
    actual_servings   DECIMAL(4,2),
    nutrient_snapshot JSONB,
    threshold_alerts  JSONB,
    meal_type         VARCHAR(20),
    week_number       SMALLINT,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),

    CONSTRAINT pk_profile_recipe_history PRIMARY KEY (:pk_prh),
    CONSTRAINT ck_prh_servings  CHECK (actual_servings IS NULL OR actual_servings > 0),
    CONSTRAINT ck_prh_meal_type CHECK (meal_type IS NULL
                                       OR meal_type IN ('Breakfast', 'Lunch', 'Dinner', 'Snack')),
    CONSTRAINT ck_prh_week      CHECK (week_number IS NULL OR week_number BETWEEN 1 AND 53),
    CONSTRAINT ck_prh_snapshot  CHECK (nutrient_snapshot IS NULL
                                       OR jsonb_typeof(nutrient_snapshot) = 'object'),
    CONSTRAINT ck_prh_alerts    CHECK (threshold_alerts IS NULL
                                       OR jsonb_typeof(threshold_alerts) = 'object')
) :part_prh ;

COMMENT ON COLUMN public.profile_recipe_history.recipe_id         IS 'NULL for manually logged meals with no matching recipe.';
COMMENT ON COLUMN public.profile_recipe_history.nutrient_snapshot IS '{nutrient_id: consumed_value} frozen at eat-time. GIN-indexed for per-nutrient queries.';
COMMENT ON COLUMN public.profile_recipe_history.week_number       IS 'ISO week. Denormalised so weekly summaries avoid a date function per row.';

-- ---------------------------------------------------------------------------
-- nutrient_daily_log · ~365M rows/year @ 1M users
--
-- Daily running totals per member per nutrient, maintained by the
-- nutrient-daily-log-aggregate worker with the atomic upsert:
--
--   INSERT INTO nutrient_daily_log (member_id, log_date, nutrient_id,
--                                   consumed_value, target_value)
--   VALUES (...)
--   ON CONFLICT (member_id, log_date, nutrient_id)
--   DO UPDATE SET consumed_value = nutrient_daily_log.consumed_value
--                                  + EXCLUDED.consumed_value,
--                 updated_at     = now();
--
-- target_value is denormalised on purpose: it captures the target as it stood
-- when the meal was logged, so history stays truthful after a profile change.
-- ---------------------------------------------------------------------------
CREATE TABLE public.nutrient_daily_log (
    log_id          UUID           NOT NULL DEFAULT public.gen_ulid(),
    member_id       UUID           NOT NULL,
    log_date        DATE           NOT NULL,
    nutrient_id     VARCHAR(40)    NOT NULL,
    consumed_value  DECIMAL(10,4)  NOT NULL DEFAULT 0,
    target_value    DECIMAL(10,4)  NOT NULL,
    pct_of_target   DECIMAL(5,2),
    alert_triggered BOOLEAN        NOT NULL DEFAULT FALSE,
    updated_at      TIMESTAMPTZ    NOT NULL DEFAULT now(),

    CONSTRAINT pk_nutrient_daily_log PRIMARY KEY (:pk_ndl),
    CONSTRAINT uq_ndl_member_date_nut UNIQUE (member_id, log_date, nutrient_id),
    CONSTRAINT ck_ndl_consumed CHECK (consumed_value >= 0),
    CONSTRAINT ck_ndl_target   CHECK (target_value   >= 0)
) :part_ndl ;

COMMENT ON TABLE  public.nutrient_daily_log               IS 'Dashboard read path. Redis: ndl:{member_id}:{date} HASH, TTL 600s.';
COMMENT ON COLUMN public.nutrient_daily_log.target_value  IS 'Snapshot of the target at log time. Denormalised for single-seek dashboard reads.';
COMMENT ON COLUMN public.nutrient_daily_log.pct_of_target IS 'consumed / target * 100. Maintained by trigger — see 94_maintenance.sql.';
