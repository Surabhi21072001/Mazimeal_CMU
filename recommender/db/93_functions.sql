-- ============================================================================
--  Derived values, PHI discovery, and the nutrient-target computation
-- ============================================================================

-- ---------------------------------------------------------------------------
-- fn_derive_category_id(age, sex) -> C001-C021
--
-- household_members.category_id is documented as "auto-derived from age+sex".
-- The only machine-readable input the workbook gives is categories.age_group,
-- a display string ('0-6m', '1-3y', '19-50y', '70+y'), so this function parses
-- it.
--
-- RECOMMENDED AMENDMENT: add age_min_months and age_max_months (SMALLINT) to
-- categories and index on them. Deriving a clinical category by regex over a
-- label is fragile — one hand-edited row reading '19 - 50 y' silently returns
-- NULL, and a member then gets no nutrient targets at all. The parser below is
-- defensive and raises rather than guessing, but the columns are the real fix.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.fn_derive_category_id(
    p_age_years SMALLINT,
    p_sex       CHAR(1)
)
RETURNS VARCHAR(10)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_age_months int;
    r            RECORD;
    v_lo         int;
    v_hi         int;
    m            text[];
BEGIN
    IF p_age_years IS NULL OR p_sex IS NULL THEN
        RETURN NULL;                       -- incomplete profile; not an error
    END IF;

    v_age_months := p_age_years * 12;

    FOR r IN
        SELECT category_id, age_group
        FROM   public.categories
        WHERE  sex = p_sex
        ORDER  BY category_id
    LOOP
        v_lo := NULL;
        v_hi := NULL;

        -- '0-6m' / '7-11m'  (months)
        m := regexp_match(r.age_group, '^([0-9]+)-([0-9]+)m$');
        IF m IS NOT NULL THEN
            v_lo := m[1]::int;
            v_hi := m[2]::int;
        END IF;

        -- '1-3y' / '19-50y'  (years -> months)
        IF v_lo IS NULL THEN
            m := regexp_match(r.age_group, '^([0-9]+)-([0-9]+)y$');
            IF m IS NOT NULL THEN
                v_lo := m[1]::int * 12;
                v_hi := m[2]::int * 12 + 11;
            END IF;
        END IF;

        -- '70+y'  (open-ended upper band)
        IF v_lo IS NULL THEN
            m := regexp_match(r.age_group, '^([0-9]+)\+y$');
            IF m IS NOT NULL THEN
                v_lo := m[1]::int * 12;
                v_hi := 2147483647;
            END IF;
        END IF;

        IF v_lo IS NULL THEN
            RAISE EXCEPTION
                'categories.age_group % (category %) does not match any known '
                'format (N-Nm, N-Ny, N+y). Fix the reference data.',
                r.age_group, r.category_id;
        END IF;

        IF v_age_months BETWEEN v_lo AND v_hi THEN
            RETURN r.category_id;
        END IF;
    END LOOP;

    RETURN NULL;   -- no band matched; caller decides whether that is an error
END
$$;

COMMENT ON FUNCTION public.fn_derive_category_id(SMALLINT, CHAR) IS
  'Maps age + sex to a DRI category. Returns NULL for incomplete profiles; raises on malformed reference data.';

-- ---------------------------------------------------------------------------
-- fn_compute_member_targets(member_id) -> rows written
--
-- The reference implementation of the chain sheet 04 describes:
--   baseline DRI  ->  apply matching modifiers by priority  ->  final target
--
-- This runs as the nutrient-target-recompute worker's SQL body. It is written
-- as a single set-based upsert rather than a row loop so that recomputing one
-- member costs one statement.
--
-- SCOPE NOTE: only modifiers whose rule_category is 'Activity_level' or 'Goal'
-- are matched here, because those are the only two whose condition_value maps
-- unambiguously onto a household_members column. Condition- and life-stage-
-- driven modifiers need the Q1-Q17 questionnaire mapping that was not supplied
-- with the schema; they are deliberately left unimplemented rather than
-- guessed at, since a wrong nutrient target is a clinical error, not a bug.
-- ---------------------------------------------------------------------------
-- Sequential fold helper: applies modifiers in the order given. Defined before
-- its caller for readability; plpgsql resolves at runtime either way.
CREATE OR REPLACE FUNCTION public.fn_fold_modifiers(
    p_base   DECIMAL,
    p_types  TEXT[],
    p_values DECIMAL[]
)
RETURNS DECIMAL
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v DECIMAL := p_base;
    i int;
BEGIN
    IF p_types IS NULL THEN
        RETURN p_base;
    END IF;

    FOR i IN 1 .. array_length(p_types, 1) LOOP
        v := CASE p_types[i]
                WHEN 'Add'      THEN v + p_values[i]
                WHEN 'Subtract' THEN v - p_values[i]
                WHEN 'Multiply' THEN v * p_values[i]
                WHEN 'Set'      THEN p_values[i]
             END;
    END LOOP;

    RETURN v;
END
$$;

CREATE OR REPLACE FUNCTION public.fn_compute_member_targets(p_member_id UUID)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_rows int;
BEGIN
    WITH member AS (
        SELECT member_id, category_id, sex_at_birth, activity_level, goal, weight_kg
        FROM   public.household_members
        WHERE  member_id = p_member_id
          AND  deleted_at IS NULL
    ),
    member_conds AS (
        SELECT condition_code FROM public.member_conditions
        WHERE  member_id = p_member_id AND condition_code IS NOT NULL
    ),
    base AS (
        SELECT m.member_id,
               b.nutrient_id,
               b.baseline_value,
               b.unit,
               b.per
        FROM   member m
        JOIN   public.profile_nutrient_baselines b ON b.category_id = m.category_id
    ),
    applicable AS (
        SELECT b.member_id,
               b.nutrient_id,
               md.rule_id,
               md.modifier_type,
               md.modifier_value,
               md.priority
        FROM   base b
        CROSS JOIN member m
        JOIN   public.nutrient_modifiers md
               ON  md.nutrient_id = b.nutrient_id
               AND md.status      = 'Validated'
               AND (md.sex IS NULL OR md.sex = m.sex_at_birth)
               AND (
                     (md.rule_category = 'Activity_level' AND md.condition_value = m.activity_level)
                  OR (md.rule_category = 'Goal'           AND md.condition_value = m.goal)
                  OR (md.rule_category = 'Condition'      AND md.condition_value IN (SELECT condition_code FROM member_conds))
                   )
    ),
    -- Apply in priority order. Multiply and Set are order-sensitive, so this
    -- folds sequentially rather than summing.
    grouped AS (
        SELECT member_id,
               nutrient_id,
               array_agg(modifier_type  ORDER BY priority DESC, rule_id) AS types,
               array_agg(modifier_value ORDER BY priority DESC, rule_id) AS vals,
               string_agg(rule_id, ','  ORDER BY priority DESC, rule_id) AS rules_csv
        FROM   applicable
        GROUP  BY member_id, nutrient_id
    ),
    folded AS (
        SELECT b.member_id,
               b.nutrient_id,
               b.unit,
               b.per,
               public.fn_fold_modifiers(b.baseline_value, g.types, g.vals) AS folded_value,
               g.rules_csv
        FROM   base b
        LEFT   JOIN grouped g
               ON g.member_id = b.member_id AND g.nutrient_id = b.nutrient_id
    )
    INSERT INTO public.profile_nutrient_targets
        (member_id, nutrient_id, final_target_value, unit, per, applied_rules_csv, computed_at)
    SELECT f.member_id,
           f.nutrient_id,
           -- per-kilogram targets (protein) become absolute grams using body weight
           CASE WHEN f.unit = 'g/kg/day' AND m.weight_kg IS NOT NULL
                THEN GREATEST(COALESCE(f.folded_value, 0), 0) * m.weight_kg
                ELSE GREATEST(COALESCE(f.folded_value, 0), 0) END,
           CASE WHEN f.unit = 'g/kg/day' AND m.weight_kg IS NOT NULL THEN 'g' ELSE f.unit END,
           f.per,
           f.rules_csv,
           now()
    FROM   folded f
    CROSS  JOIN member m
    ON CONFLICT (member_id, nutrient_id) DO UPDATE
        SET final_target_value = EXCLUDED.final_target_value,
            unit               = EXCLUDED.unit,
            per                = EXCLUDED.per,
            applied_rules_csv  = EXCLUDED.applied_rules_csv,
            computed_at        = now();

    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows;
END
$$;

-- ---------------------------------------------------------------------------
-- v_phi_columns — every column flagged as protected health information
--
-- Built from column comments so the list cannot drift from the schema. Use it
-- to drive encryption coverage tests, access-log review, and the HIPAA data
-- inventory rather than maintaining a separate spreadsheet.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_phi_columns AS
SELECT c.table_schema,
       c.table_name,
       c.column_name,
       c.data_type,
       col_description(pgc.oid, c.ordinal_position) AS column_comment
FROM   information_schema.columns c
JOIN   pg_class     pgc ON pgc.relname   = c.table_name
JOIN   pg_namespace pgn ON pgn.oid       = pgc.relnamespace
                       AND pgn.nspname   = c.table_schema
WHERE  c.table_schema = 'public'
  AND  col_description(pgc.oid, c.ordinal_position) LIKE '%PHI%';

COMMENT ON VIEW public.v_phi_columns IS
  'HIPAA data inventory, derived from column comments. Drives encryption-coverage checks.';
