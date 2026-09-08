-- ============================================================================
--  Sheet 09 · Partition Scheme  —  SCALE MODE ONLY
--
--  A partitioned parent table cannot hold rows. Until child partitions exist,
--  every INSERT fails with "no partition of relation ... found for row". This
--  file creates them.
--
--  RANGE tables also need new partitions created before time reaches them —
--  fn_ensure_time_partitions() in 94_maintenance.sql is the scheduled job that
--  does it, and this file simply calls it once to seed the initial window.
--
--  In MVP mode this file is a no-op.
-- ============================================================================

\if :scale

-- ---------------------------------------------------------------------------
-- HASH partitions — 16 per table, created up front and never changed.
--
-- Changing the modulus later requires rewriting the whole table, so 16 is a
-- one-way decision. It is chosen to divide evenly into common shard counts
-- (2, 4, 8, 16) should these tables later move to separate hosts.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    tbl  text;
    i    int;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'household_members',
        'member_conditions',
        'profile_nutrient_targets',
        'ingredient_nutrition',
        'household_recipe_plan',
        'profile_recipe_history'
    ]
    LOOP
        FOR i IN 0..15 LOOP
            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS public.%I PARTITION OF public.%I '
                'FOR VALUES WITH (MODULUS 16, REMAINDER %s)',
                tbl || '_p' || lpad(i::text, 2, '0'), tbl, i);
        END LOOP;
        RAISE NOTICE 'hash partitions ready: % (16)', tbl;
    END LOOP;
END
$$;

-- ---------------------------------------------------------------------------
-- LIST partitions · ingredients by USDA food group
--
-- The DEFAULT partition is deliberate. A LIST partition set must be exhaustive
-- or inserts fail, and the USDA food-group list is not under our control — a
-- new group appearing in an import would otherwise break ingestion in
-- production. Rows landing in the default are a signal, not a resting place:
-- fn_check_default_partitions() reports them.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    cats text[] := ARRAY[
        'Dairy and Egg Products',
        'Spices and Herbs',
        'Baby Foods',
        'Fats and Oils',
        'Poultry Products',
        'Soups Sauces and Gravies',
        'Cereal Grains and Pasta',
        'Breakfast Cereals',
        'Fruits and Fruit Juices',
        'Pork Products',
        'Vegetables and Vegetable Products',
        'Nut and Seed Products',
        'Beef Products',
        'Beverages',
        'Finfish and Shellfish Products',
        'Legumes and Legume Products'
    ];
    c text;
    i int := 0;
BEGIN
    FOREACH c IN ARRAY cats LOOP
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS public.%I PARTITION OF public.ingredients '
            'FOR VALUES IN (%L)',
            'ingredients_p' || lpad(i::text, 2, '0'), c);
        i := i + 1;
    END LOOP;

    EXECUTE 'CREATE TABLE IF NOT EXISTS public.ingredients_p_default '
            'PARTITION OF public.ingredients DEFAULT';

    RAISE NOTICE 'ingredients: % list partitions + default', i;
END
$$;

-- ---------------------------------------------------------------------------
-- LIST partitions · recipes by data_source
--
-- The point of this split is that AI-generated content lives in its own
-- physical table: it can be reindexed, audited, or truncated without touching
-- the curated reference data.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.recipes_usda
    PARTITION OF public.recipes FOR VALUES IN ('USDA');
CREATE TABLE IF NOT EXISTS public.recipes_off
    PARTITION OF public.recipes FOR VALUES IN ('Open_Food_Facts');
CREATE TABLE IF NOT EXISTS public.recipes_manual
    PARTITION OF public.recipes FOR VALUES IN ('Manual');
CREATE TABLE IF NOT EXISTS public.recipes_ai
    PARTITION OF public.recipes FOR VALUES IN ('AI_generated');

-- ---------------------------------------------------------------------------
-- RANGE partitions · monthly, seeded here and extended by the scheduled job.
--
-- fn_ensure_time_partitions() is defined in 94_maintenance.sql, which runs
-- after this file, so the seeding call lives there. This block only creates a
-- DEFAULT partition per table so that an insert can never fail outright while
-- waiting for the job — a row in the default is recoverable; a rejected
-- INSERT on the audit log is not.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.sessions_p_default
    PARTITION OF public.sessions DEFAULT;
CREATE TABLE IF NOT EXISTS public.audit_log_p_default
    PARTITION OF public.audit_log DEFAULT;
CREATE TABLE IF NOT EXISTS public.nutrient_daily_log_p_default
    PARTITION OF public.nutrient_daily_log DEFAULT;

\echo '   SCALE: partitions created (96 hash + 17 ingredient + 4 recipe + 3 default).'

\else
  \echo '   MVP mode: no partitions to create.'
\endif
