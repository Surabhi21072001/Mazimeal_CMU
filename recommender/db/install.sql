-- ============================================================================
--  SYNERGIA · Unified Database Schema — installer
--
--    psql -d synergia -f db/install.sql                    # MVP mode (default)
--    psql -d synergia -v scale=true -f db/install.sql      # SCALE mode
--
--  Everything runs in one transaction: either the whole schema is created or
--  nothing is. Re-running against a database that already has the schema will
--  fail on the first duplicate object, by design — use a migration tool for
--  incremental changes, not this file.
-- ============================================================================

\set ON_ERROR_STOP on
\set QUIET on

-- Supabase keeps extensions (pgvector) in their own schema. Harmless elsewhere.
SET search_path = public, extensions;

BEGIN;

\ir 00_extensions.sql

\echo '   tables...'
\ir 10_identity_auth.sql
\ir 20_household_profile.sql
\ir 30_conditions_rules.sql
\ir 40_nutrition_baselines.sql
\ir 50_ingredients_nutrition.sql
\ir 60_food_science.sql
\ir 70_recipes.sql
\ir 80_plan_tracking.sql

\echo '   foreign keys...'
\ir 85_foreign_keys.sql

\echo '   pgvector...'
\ir 88_vector.sql

\echo '   indexes...'
\ir 90_indexes.sql

\echo '   partitions...'
\ir 91_partitions.sql

\echo '   functions...'
\ir 93_functions.sql

\echo '   triggers and maintenance...'
\ir 94_maintenance.sql

\echo '   row level security...'
\ir 95_rls.sql

\echo '   legacy compatibility...'
\ir 96_compat_weekly_plans.sql

\echo '   recommender...'
\ir 97_recommender.sql
\ir 98_home.sql
\ir 98_recipe.sql
\ir 98_log.sql

COMMIT;

\echo ''
\echo '=============================================================='
\echo ' Schema installed.'
\echo ''
\echo ' Next:'
\echo '   psql -f seed/00_reference.sql     -- reference data'
\echo '   SELECT * FROM v_unenforced_fks;      -- integrity gaps (empty in MVP)'
\echo '   SELECT * FROM v_phi_columns;         -- HIPAA data inventory'
\echo '=============================================================='
