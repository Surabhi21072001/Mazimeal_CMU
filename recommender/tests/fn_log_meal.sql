-- Checks for fn_log_meal / fn_unlog_meal / fn_member_meals. Needs the full
-- schema with the seed files loaded. Leaves the database as it found it.
--   psql -d <db> -v ON_ERROR_STOP=1 -f recommender/tests/fn_log_meal.sql

\set ON_ERROR_STOP on
\set QUIET on

DO $$
DECLARE
    rid      UUID;
    jeff     UUID;
    maya     UUID;
    log1     UUID := gen_random_uuid();
    log2     UUID := gen_random_uuid();
    j        JSONB;
    before_e NUMERIC;
    after_e  NUMERIC;
    gap_b    NUMERIC;
    gap_a    NUMERIC;
    kcal     NUMERIC;
    n        INT;
BEGIN
    SELECT recipe_id INTO rid FROM recipes WHERE recipe_name = 'Bourbon Chicken';
    SELECT member_id INTO jeff FROM household_members WHERE member_name = 'Jeff';
    SELECT member_id INTO maya FROM household_members WHERE member_name = 'Maya';
    IF rid IS NULL OR jeff IS NULL OR maya IS NULL THEN RAISE EXCEPTION 'seed data missing'; END IF;

    SELECT (e ->> 'per_serving')::numeric INTO kcal
    FROM jsonb_array_elements(fn_recipe_nutrition(rid) -> 'nutrients') e WHERE e ->> 'nutrient' = 'Energy';
    SELECT coalesce(consumed_value, 0) INTO before_e FROM nutrient_daily_log
    WHERE member_id = jeff AND log_date = current_date AND nutrient_id = 'Energy';
    SELECT gap INTO gap_b FROM fn_member_gap(jeff, current_date) WHERE nutrient_id = 'Energy';

    -- 1. log for two people, different portions
    j := fn_log_meal(rid, jsonb_build_array(
             jsonb_build_object('member_id', jeff, 'servings', 1.5),
             jsonb_build_object('member_id', maya, 'servings', 1)), 'Dinner', now(), '[]', log1);
    IF (j ->> 'already_logged')::boolean THEN RAISE EXCEPTION 'first log reported as already logged'; END IF;
    IF jsonb_array_length(j -> 'members') <> 2 THEN RAISE EXCEPTION 'expected 2 member rows'; END IF;
    SELECT count(*) INTO n FROM profile_recipe_history WHERE log_id = log1;
    IF n <> 2 THEN RAISE EXCEPTION 'expected 2 history rows, got %', n; END IF;
    RAISE NOTICE 'ok  logged for 2 members';

    -- 2. snapshot = per-serving x servings, frozen as a plain object
    SELECT (nutrient_snapshot ->> 'Energy')::numeric INTO after_e FROM profile_recipe_history WHERE log_id = log1 AND member_id = jeff;
    IF abs(after_e - kcal * 1.5) > 0.05 THEN RAISE EXCEPTION 'snapshot energy % <> % x 1.5', after_e, kcal; END IF;
    RAISE NOTICE 'ok  snapshot: % kcal for 1.5 servings', round(after_e);

    -- 3. daily totals moved by the same amount, and the gap closed by it
    SELECT consumed_value INTO after_e FROM nutrient_daily_log
    WHERE member_id = jeff AND log_date = current_date AND nutrient_id = 'Energy';
    IF abs((after_e - before_e) - kcal * 1.5) > 0.05 THEN RAISE EXCEPTION 'daily log moved by % not %', after_e - before_e, kcal * 1.5; END IF;
    SELECT gap INTO gap_a FROM fn_member_gap(jeff, current_date) WHERE nutrient_id = 'Energy';
    IF gap_a > gap_b THEN RAISE EXCEPTION 'gap did not close'; END IF;
    RAISE NOTICE 'ok  daily total +% kcal, energy gap % -> %', round(kcal * 1.5), round(gap_b), round(gap_a);

    -- 4. same log_id again: no double count
    j := fn_log_meal(rid, jsonb_build_array(jsonb_build_object('member_id', jeff, 'servings', 1.5)), 'Dinner', now(), '[]', log1);
    IF NOT (j ->> 'already_logged')::boolean THEN RAISE EXCEPTION 'retry not detected'; END IF;
    SELECT consumed_value INTO n FROM nutrient_daily_log WHERE member_id = jeff AND log_date = current_date AND nutrient_id = 'Energy';
    IF abs(n - after_e) > 1 THEN RAISE EXCEPTION 'retry double counted'; END IF;
    RAISE NOTICE 'ok  retry with same log_id is a no-op';

    -- 5. the day's meals for Jeff include it
    IF NOT EXISTS (SELECT 1 FROM jsonb_array_elements(fn_member_meals(jeff, current_date)) m WHERE (m ->> 'log_id')::uuid = log1) THEN
        RAISE EXCEPTION 'fn_member_meals missing the meal';
    END IF;
    RAISE NOTICE 'ok  fn_member_meals lists it';

    -- 6. undo restores the totals
    n := fn_unlog_meal(log1);
    IF n <> 2 THEN RAISE EXCEPTION 'unlog removed % rows, expected 2', n; END IF;
    SELECT consumed_value INTO after_e FROM nutrient_daily_log
    WHERE member_id = jeff AND log_date = current_date AND nutrient_id = 'Energy';
    IF abs(after_e - before_e) > 0.05 THEN RAISE EXCEPTION 'unlog left % instead of %', after_e, before_e; END IF;
    IF EXISTS (SELECT 1 FROM profile_recipe_history WHERE log_id = log1) THEN RAISE EXCEPTION 'history rows remain'; END IF;
    RAISE NOTICE 'ok  unlog restores daily totals';

    -- 7. a big portion against a small target (a child's B12) must not overflow pct_of_target
    j := fn_log_meal(rid, jsonb_build_array(jsonb_build_object('member_id', maya, 'servings', 25)), 'Dinner', now(), '[]', log2);
    SELECT max(pct_of_target) INTO after_e FROM nutrient_daily_log WHERE member_id = maya AND log_date = current_date;
    IF after_e IS NULL OR after_e < 1000 THEN RAISE EXCEPTION 'expected a pct over 1000, got %', after_e; END IF;
    n := fn_unlog_meal(log2);
    IF n <> 1 THEN RAISE EXCEPTION 'unlog of big portion removed % rows', n; END IF;
    RAISE NOTICE 'ok  big portion: max pct % without overflow, undone', round(after_e);

    -- 8. bad input is rejected
    BEGIN
        PERFORM fn_log_meal(rid, '[]'::jsonb, 'Dinner');
        RAISE EXCEPTION 'empty portions accepted';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM LIKE '%non-empty%' THEN RAISE NOTICE 'ok  empty portions rejected'; ELSE RAISE; END IF;
    END;
    BEGIN
        PERFORM fn_log_meal(rid, jsonb_build_array(jsonb_build_object('member_id', jeff, 'servings', 1)), 'Brunch');
        RAISE EXCEPTION 'bad meal type accepted';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM LIKE '%meal_type%' THEN RAISE NOTICE 'ok  bad meal type rejected'; ELSE RAISE; END IF;
    END;
END $$;
