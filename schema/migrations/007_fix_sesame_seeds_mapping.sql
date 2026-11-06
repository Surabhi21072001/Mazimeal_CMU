-- 007_fix_sesame_seeds_mapping.sql
-- `sesame seeds` was pointing at rice cakes.
--
-- Found while surveying nutrition gaps: ingredients.usda_fdc_id for
-- `sesame seeds` was 167557, which USDA calls
--
--     Snacks, rice cakes, brown rice, sesame seed
--
-- a rice cake with sesame on it. Every one of the 24 nutrition rows for this
-- ingredient was therefore describing a rice cake:
--
--     Macro_Fat    3.8 g per 100 g   sesame seeds are about 50
--     Calcium     12.0 mg            sesame seeds are about 975
--
-- so calcium was out by a factor of roughly eighty, on 90 g of a recipe. This
-- is worse than the gaps the survey was looking for. A missing value
-- announces itself - the cook screen marks the nutrient unavailable - while a
-- wrong one is indistinguishable from a right one and propagates into every
-- total, ratio and recommendation computed from it.
--
-- The correct entry is 170150, "Seeds, sesame seeds, whole, dried", which
-- SR Legacy profiles for all 28 nutrients the database tracks.
--
-- This migration only corrects the mapping and removes the rows that came
-- from the wrong food. It deliberately does not insert replacements: the
-- values belong to a fetch that can be re-run and cited, so
--
--     python3 scripts/fill_ingredient_nutrition.py --apply
--
-- imports all 28 from the corrected id afterwards. Hard-coding 28 numbers
-- here would put values in the schema with no record of where they came from,
-- which is the habit this whole exercise is trying to avoid.
--
-- How many other mappings are wrong is not known. scripts/audit_ingredient_fdc_ids.py
-- checks all 93 that have an id and finds nothing else, but it cannot find
-- this class of error either: "Snacks, rice cakes, brown rice, sesame seed"
-- does contain the word "sesame", so no cheap text rule separates it from a
-- real match. The list needs a human pass.

BEGIN;

-- Fail rather than guess if the data is not what this migration was written
-- against: already corrected, or changed by someone else in the meantime.
DO $$
DECLARE
    v_id   UUID;
    v_fdc  BIGINT;
BEGIN
    SELECT ingredient_id, usda_fdc_id INTO v_id, v_fdc
      FROM ingredients WHERE ingredient_name = 'sesame seeds';

    IF v_id IS NULL THEN
        RAISE EXCEPTION 'no ingredient named "sesame seeds"';
    END IF;

    IF v_fdc = 170150 THEN
        RAISE NOTICE 'already corrected; nothing to do';
        RETURN;
    END IF;

    IF v_fdc IS DISTINCT FROM 167557 THEN
        RAISE EXCEPTION 'expected usda_fdc_id 167557 (the rice cake) or 170150 '
                        '(the correction), found %', v_fdc;
    END IF;

    UPDATE ingredients
       SET usda_fdc_id = 170150,
           -- food_category was copied from the wrong food along with
           -- everything else, so it said "Snacks".
           food_category = 'Nut and Seed Products'
     WHERE ingredient_id = v_id;

    DELETE FROM ingredient_nutrition
     WHERE ingredient_id = v_id
       AND source_id = 'usda_sr_legacy';

    RAISE NOTICE 'sesame seeds remapped to 170150; its old nutrition rows removed. '
                 'Run scripts/fill_ingredient_nutrition.py --apply to import the real values.';
END;
$$;

COMMIT;
