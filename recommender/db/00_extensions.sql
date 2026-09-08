-- ============================================================================
--  SYNERGIA · Unified Database Schema
--  00_extensions.sql — extensions, helper functions, build-mode configuration
-- ----------------------------------------------------------------------------
--  Source of truth: Synergia_Unified_DB_Schema.xlsx (9 sheets, 33 tables)
--
--  BUILD MODES
--    psql -v scale=false -f install.sql   -> MVP  (default; plain tables, all FKs)
--    psql -v scale=true  -f install.sql   -> SCALE (partitioned per sheet 09)
--
--  The two modes produce the SAME logical schema. SCALE mode adds declarative
--  partitioning, which forces two changes Postgres requires:
--    1. Every PRIMARY KEY / UNIQUE constraint on a partitioned table must
--       contain the partition key, so PKs become composite.
--    2. A foreign key cannot reference a partitioned table unless it targets
--       that full composite key. ~20 FKs are therefore dropped in SCALE mode
--       and must be enforced in the application layer. See 85_foreign_keys.sql
--       for the exact list — this is a real cost of the sheet 09 design and the
--       team should make that trade-off deliberately.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Build-mode resolution. Defaults to MVP when -v scale=... is not supplied.
-- ---------------------------------------------------------------------------
\if :{?scale}
\else
  \set scale false
\endif

\if :scale
  \echo '>> Building in SCALE mode (partitioned, 1M-user target)'
\else
  \echo '>> Building in MVP mode (plain tables, full referential integrity)'
\endif

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_bytes(), PHI encryption

-- pgvector is required for the RAG / recipe-similarity features (sheets 03, 07).
-- It ships with Supabase and Postgres 15+ images, but is absent from a stock
-- apt install, so it is probed rather than assumed. When missing, the two
-- embedding columns and their HNSW indexes are skipped (see 88_vector.sql) and
-- everything else still builds.
DO $$
BEGIN
  CREATE EXTENSION IF NOT EXISTS vector;
  RAISE NOTICE 'pgvector enabled — embedding columns and HNSW indexes will be created.';
EXCEPTION WHEN OTHERS THEN
  RAISE WARNING 'pgvector NOT available (%). Embedding columns and HNSW indexes '
                'will be SKIPPED. Install pgvector before enabling AI search.',
                SQLERRM;
END
$$;

-- ---------------------------------------------------------------------------
-- gen_ulid() — time-ordered UUID generator
--
-- The workbook specifies "UUID v7 / ULID — time-ordered, avoids hot spots" as
-- the default for every surrogate key. Postgres 18 ships uuidv7() natively;
-- on 16/17 (and Supabase today) we generate a spec-compliant UUIDv7 by hand.
-- Both produce values that sort by creation time, which is what the B-tree
-- insert pattern depends on.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.gen_ulid()
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
  ts_millis  bigint;
  uuid_bytes bytea;
BEGIN
  -- Postgres 18+ has a native, faster implementation.
  BEGIN
    RETURN uuidv7();
  EXCEPTION WHEN undefined_function THEN
    NULL;  -- fall through to the manual path
  END;

  ts_millis  := floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint;

  -- 48-bit big-endian timestamp (bytes 3..8 of an int8) + 10 random bytes
  uuid_bytes := substring(int8send(ts_millis) FROM 3 FOR 6) || gen_random_bytes(10);

  -- byte 6: high nibble = version 7
  uuid_bytes := set_byte(uuid_bytes, 6, (get_byte(uuid_bytes, 6) & 15)  | 112);
  -- byte 8: high two bits = RFC 4122 variant
  uuid_bytes := set_byte(uuid_bytes, 8, (get_byte(uuid_bytes, 8) & 63)  | 128);

  RETURN encode(uuid_bytes, 'hex')::uuid;
END
$$;

COMMENT ON FUNCTION public.gen_ulid() IS
  'Time-ordered UUIDv7. Sequential inserts, no B-tree hot spots, safe across shards.';

-- ---------------------------------------------------------------------------
-- set_updated_at() — generic updated_at trigger
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END
$$;

-- ---------------------------------------------------------------------------
-- Partition / primary-key toggles.
--
-- Each pair below controls one table. In MVP mode the partition clause is
-- empty and the PK is the natural single surrogate column; in SCALE mode the
-- partition clause is emitted and the partition key is appended to the PK
-- because Postgres requires it.
-- ---------------------------------------------------------------------------
\if :scale
  \set part_sessions            'PARTITION BY RANGE (created_at)'
  \set pk_sessions              'session_id, created_at'

  \set part_audit_log           'PARTITION BY RANGE (occurred_at)'
  \set pk_audit_log             'log_id, occurred_at'

  \set part_household_members   'PARTITION BY HASH (household_id)'
  \set pk_household_members     'member_id, household_id'

  \set part_member_conditions   'PARTITION BY HASH (member_id)'
  \set pk_member_conditions     'record_id, member_id'

  \set part_pnt                 'PARTITION BY HASH (member_id)'
  \set pk_pnt                   'target_id, member_id'

  \set part_ingredients         'PARTITION BY LIST (food_category)'
  \set pk_ingredients           'ingredient_id, food_category'

  \set part_ing_nutrition       'PARTITION BY HASH (ingredient_id)'
  \set pk_ing_nutrition         'nutrition_id, ingredient_id'

  \set part_recipes             'PARTITION BY LIST (data_source)'
  \set pk_recipes               'recipe_id, data_source'

  \set part_hrp                 'PARTITION BY HASH (household_id)'
  \set pk_hrp                   'plan_id, household_id'

  \set part_prh                 'PARTITION BY HASH (household_id)'
  \set pk_prh                   'history_id, household_id'

  \set part_ndl                 'PARTITION BY RANGE (log_date)'
  \set pk_ndl                   'log_id, log_date'
\else
  \set part_sessions            ''
  \set pk_sessions              'session_id'

  \set part_audit_log           ''
  \set pk_audit_log             'log_id'

  \set part_household_members   ''
  \set pk_household_members     'member_id'

  \set part_member_conditions   ''
  \set pk_member_conditions     'record_id'

  \set part_pnt                 ''
  \set pk_pnt                   'target_id'

  \set part_ingredients         ''
  \set pk_ingredients           'ingredient_id'

  \set part_ing_nutrition       ''
  \set pk_ing_nutrition         'nutrition_id'

  \set part_recipes             ''
  \set pk_recipes               'recipe_id'

  \set part_hrp                 ''
  \set pk_hrp                   'plan_id'

  \set part_prh                 ''
  \set pk_prh                   'history_id'

  \set part_ndl                 ''
  \set pk_ndl                   'log_id'
\endif
