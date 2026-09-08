-- ============================================================================
--  Triggers, partition lifecycle, and integrity checks
--
--  Everything here corresponds to a queue topic or cache-invalidation event in
--  sheet 09. The database's job is to detect the change and announce it; the
--  actual work happens in a worker.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- household_members: maintain updated_at, derive category_id, announce change
--
-- The pg_notify payload is what the nutrient-target-recompute worker listens
-- on. Recomputing inline in the trigger would put a 25-nutrient rule fold in
-- the path of a profile save; sheet 09 explicitly requires it be async.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.trg_household_members_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();

    -- Auto-derive the DRI category when the caller did not supply one, or when
    -- the inputs it depends on have changed.
    IF NEW.category_id IS NULL
       OR TG_OP = 'INSERT'
       OR NEW.age IS DISTINCT FROM OLD.age
       OR NEW.sex_at_birth IS DISTINCT FROM OLD.sex_at_birth
    THEN
        NEW.category_id := COALESCE(
            public.fn_derive_category_id(NEW.age, NEW.sex_at_birth),
            NEW.category_id
        );
    END IF;

    -- Announce for: nutrient-target-recompute queue + Redis nt:/hm: invalidation
    PERFORM pg_notify('member_profile_changed', NEW.member_id::text);

    RETURN NEW;
END
$$;

CREATE TRIGGER trg_hm_change
    BEFORE INSERT OR UPDATE ON public.household_members
    FOR EACH ROW EXECUTE FUNCTION public.trg_household_members_change();

-- ---------------------------------------------------------------------------
-- member_conditions: allergen set is stale whenever a condition row changes
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.trg_member_conditions_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_member UUID := COALESCE(NEW.member_id, OLD.member_id);
BEGIN
    -- Announce for: household-allergen-cache-warm queue + Redis al: invalidation
    PERFORM pg_notify('member_conditions_changed', v_member::text);
    RETURN COALESCE(NEW, OLD);
END
$$;

CREATE TRIGGER trg_mc_change
    AFTER INSERT OR UPDATE OR DELETE ON public.member_conditions
    FOR EACH ROW EXECUTE FUNCTION public.trg_member_conditions_change();

-- ---------------------------------------------------------------------------
-- nutrient_daily_log: keep pct_of_target and updated_at consistent
--
-- Computed in a trigger rather than the application because this table is
-- written by an upsert that increments consumed_value in place — the
-- application never holds the resulting total and so cannot compute the
-- percentage itself.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.trg_ndl_derive()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();

    IF NEW.target_value > 0 THEN
        NEW.pct_of_target := round((NEW.consumed_value / NEW.target_value) * 100, 2);
    ELSE
        NEW.pct_of_target := NULL;
    END IF;

    RETURN NEW;
END
$$;

CREATE TRIGGER trg_ndl_derive
    BEFORE INSERT OR UPDATE ON public.nutrient_daily_log
    FOR EACH ROW EXECUTE FUNCTION public.trg_ndl_derive();

-- ---------------------------------------------------------------------------
-- Generic audit trigger — HIPAA change tracking
--
-- Attached to the PHI tables. The acting user is read from a session GUC that
-- the application sets on connection checkout:
--     SET LOCAL app.user_id = '<uuid>';
-- Nothing breaks if it is absent; the row is simply logged with a NULL actor.
--
-- Only changed keys are stored, per sheet 01 — a full before/after row image on
-- 15M PHI rows would dominate the database's size.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.trg_audit_row()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_user   UUID;
    v_old    JSONB;
    v_new    JSONB;
    v_record UUID;
BEGIN
    BEGIN
        v_user := nullif(current_setting('app.user_id', true), '')::UUID;
    EXCEPTION WHEN OTHERS THEN
        v_user := NULL;
    END;

    IF TG_OP = 'INSERT' THEN
        v_new := to_jsonb(NEW);
    ELSIF TG_OP = 'DELETE' THEN
        v_old := to_jsonb(OLD);
    ELSE
        -- changed keys only
        v_old := (SELECT jsonb_object_agg(key, value)
                  FROM jsonb_each(to_jsonb(OLD))
                  WHERE to_jsonb(NEW) -> key IS DISTINCT FROM value);
        v_new := (SELECT jsonb_object_agg(key, value)
                  FROM jsonb_each(to_jsonb(NEW))
                  WHERE to_jsonb(OLD) -> key IS DISTINCT FROM value);

        IF v_new IS NULL OR v_new = '{}'::jsonb THEN
            RETURN COALESCE(NEW, OLD);   -- nothing actually changed
        END IF;
    END IF;

    v_record := COALESCE(to_jsonb(NEW) ->> TG_ARGV[0], to_jsonb(OLD) ->> TG_ARGV[0])::UUID;

    INSERT INTO public.audit_log (user_id, action, table_name, record_id, old_values, new_values)
    VALUES (v_user,
            TG_TABLE_NAME || '.' || lower(TG_OP),
            TG_TABLE_NAME,
            v_record,
            v_old,
            v_new);

    RETURN COALESCE(NEW, OLD);
END
$$;

COMMENT ON FUNCTION public.trg_audit_row() IS
  'HIPAA audit trigger. TG_ARGV[0] is the name of the row''s primary-key column.';

CREATE TRIGGER trg_audit_member_conditions
    AFTER INSERT OR UPDATE OR DELETE ON public.member_conditions
    FOR EACH ROW EXECUTE FUNCTION public.trg_audit_row('record_id');

CREATE TRIGGER trg_audit_household_members
    AFTER INSERT OR UPDATE OR DELETE ON public.household_members
    FOR EACH ROW EXECUTE FUNCTION public.trg_audit_row('member_id');

-- ---------------------------------------------------------------------------
-- fn_ensure_time_partitions(months_ahead) — SCALE mode
--
-- Creates monthly partitions for the RANGE-partitioned tables. Schedule this
-- daily; it is idempotent. Creating partitions ahead of time is not optional —
-- without it the DEFAULT partition silently absorbs new rows and, once it holds
-- data, attaching the real partition for that month requires a full scan.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.fn_ensure_time_partitions(p_months_ahead int DEFAULT 3)
RETURNS int
LANGUAGE plpgsql
AS $$
DECLARE
    tbl        text;
    m          int;
    v_start    date;
    v_end      date;
    v_name     text;
    v_created  int := 0;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['sessions', 'audit_log', 'nutrient_daily_log'] LOOP
        -- Skip when the table is not partitioned (MVP mode).
        CONTINUE WHEN NOT EXISTS (
            SELECT 1 FROM pg_partitioned_table pt
            JOIN pg_class c ON c.oid = pt.partrelid
            WHERE c.relname = tbl
        );

        FOR m IN -1 .. p_months_ahead LOOP
            v_start := date_trunc('month', current_date) + (m || ' month')::interval;
            v_end   := v_start + interval '1 month';
            v_name  := tbl || '_p' || to_char(v_start, 'YYYYMM');

            IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = v_name) THEN
                EXECUTE format(
                    'CREATE TABLE public.%I PARTITION OF public.%I FOR VALUES FROM (%L) TO (%L)',
                    v_name, tbl, v_start, v_end);
                v_created := v_created + 1;
            END IF;
        END LOOP;
    END LOOP;

    RETURN v_created;
END
$$;

-- ---------------------------------------------------------------------------
-- fn_drop_old_partitions(table, retain_months) — SCALE mode
--
-- Dropping a partition is O(1); DELETE over the same rows is O(n) plus vacuum.
-- That difference is the whole reason these tables are RANGE-partitioned.
--
-- HIPAA: audit_log partitions must be exported to S3 BEFORE being dropped. This
-- function refuses to touch audit_log unless p_i_have_archived is explicitly
-- true, so a scheduled cleanup cannot quietly destroy the compliance record.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.fn_drop_old_partitions(
    p_table            text,
    p_retain_months    int,
    p_i_have_archived  boolean DEFAULT false
)
RETURNS TABLE (dropped_partition text)
LANGUAGE plpgsql
AS $$
DECLARE
    v_cutoff date := date_trunc('month', current_date) - (p_retain_months || ' month')::interval;
    r        RECORD;
BEGIN
    IF p_table = 'audit_log' AND NOT p_i_have_archived THEN
        RAISE EXCEPTION
            'Refusing to drop audit_log partitions: export to S3 first, then '
            'call with p_i_have_archived => true (HIPAA retention).';
    END IF;

    FOR r IN
        SELECT c.relname
        FROM   pg_class c
        WHERE  c.relname ~ ('^' || p_table || '_p[0-9]{6}$')
          AND  to_date(right(c.relname, 6), 'YYYYMM') < v_cutoff
    LOOP
        EXECUTE format('DROP TABLE public.%I', r.relname);
        dropped_partition := r.relname;
        RETURN NEXT;
    END LOOP;
END
$$;

-- ---------------------------------------------------------------------------
-- Integrity checks — run these on a schedule and alert on any non-empty result
-- ---------------------------------------------------------------------------

-- Rows that fell into a DEFAULT partition are rows whose partition key was not
-- anticipated. Harmless individually, but they defeat partition pruning and
-- block attaching the correct partition later.
CREATE OR REPLACE FUNCTION public.fn_check_default_partitions()
RETURNS TABLE (partition_name text, row_count bigint)
LANGUAGE plpgsql
AS $$
DECLARE
    r RECORD;
    n bigint;
BEGIN
    FOR r IN
        SELECT relname FROM pg_class
        WHERE relname LIKE '%\_p\_default' AND relkind = 'r'
    LOOP
        EXECUTE format('SELECT count(*) FROM public.%I', r.relname) INTO n;
        IF n > 0 THEN
            partition_name := r.relname;
            row_count      := n;
            RETURN NEXT;
        END IF;
    END LOOP;
END
$$;

-- SCALE mode weakens the usda_fdc_id uniqueness guarantee to
-- (usda_fdc_id, food_category). This detects the case that weakening allows.
CREATE OR REPLACE FUNCTION public.fn_check_duplicate_fdc_ids()
RETURNS TABLE (usda_fdc_id bigint, occurrences bigint)
LANGUAGE sql
STABLE
AS $$
    SELECT i.usda_fdc_id, count(*)
    FROM   public.ingredients i
    WHERE  i.usda_fdc_id IS NOT NULL
    GROUP  BY i.usda_fdc_id
    HAVING count(*) > 1;
$$;

-- Members whose targets predate their last profile edit are serving stale
-- nutrition guidance. This should always return zero rows; if it does not, the
-- nutrient-target-recompute worker is behind or dead.
CREATE OR REPLACE FUNCTION public.fn_check_stale_targets()
RETURNS TABLE (member_id uuid, profile_updated_at timestamptz, targets_computed_at timestamptz)
LANGUAGE sql
STABLE
AS $$
    SELECT m.member_id, m.updated_at, max(t.computed_at)
    FROM   public.household_members m
    JOIN   public.profile_nutrient_targets t ON t.member_id = m.member_id
    WHERE  m.deleted_at IS NULL
    GROUP  BY m.member_id, m.updated_at
    HAVING m.updated_at > max(t.computed_at);
$$;

-- ---------------------------------------------------------------------------
-- Seed the initial time partitions (no-op in MVP mode)
-- ---------------------------------------------------------------------------
SELECT public.fn_ensure_time_partitions(3) AS time_partitions_created;
