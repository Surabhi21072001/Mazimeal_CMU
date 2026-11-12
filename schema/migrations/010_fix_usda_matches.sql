-- 010_fix_usda_matches.sql
-- Point fifteen ingredients (nine distinct wrong matches) at the USDA food they are named for.
--
-- Found by reading every source_description against the ingredient name for the
-- ingredients that scripts/tag_ingredients.py proposes tags for. Fuzzy matching
-- produced these, and none of them can be caught by a text rule, because each
-- wrong description shares a word with the right one:
--
--   grapes              Grape leaves, raw                          (vitamin A 1376 mcg/100 g;
--                                                                   grapes are ~3, so it was
--                                                                   proposed as a carotenoid food)
--   orange              Tomatoes, orange, raw                      (vitamin C 16 mg; an orange is 53)
--   strawberry          Guavas, strawberry, raw                    (a guava, not a strawberry)
--   sweet potatoes      Sweet potato leaves, raw                   (leaves; vitamin K 302 mcg)
--   sun-dried tomatoes  Tomatoes, red, ripe, raw                   (sun-dried is ~10x as dense)
--   tomato paste        Tomato products, canned, puree             (paste is about twice the puree)
--   parsley flakes      Parsley, fresh                             (dried flakes, a different food)
--   oats, oatmeal, rolled oats, old fashioned oats, quick-cooking
--   oatmeal, Old mill oats, Robin Hood oats
--                       Breakfast bars, oats, sugar, raisins, ...  (a snack bar, not oats)
--   sesame seeds        Snacks, rice cakes ... (provenance only)   (migration 007 corrected
--                                                                   ingredients.usda_fdc_id but left
--                                                                   ingredient_source_map pointing at
--                                                                   the rice cake)
--
-- Two kinds of correction, kept apart on purpose:
--
--   copy      The right USDA record is ALREADY loaded under another ingredient
--             (grapes, strawberry, parsley flakes, the oats). Its usda_sr_legacy
--             rows are copied across, so the values keep the provenance they have
--             today and no number is typed or fetched here.
--   pending   The right record is known but nothing under that record is loaded
--             (orange, sweet potatoes, sun-dried tomatoes, tomato paste). The wrong
--             rows are removed and the ingredient shows as unavailable until
--             scripts/fill_ingredient_nutrition.py --apply imports the real values,
--             the same choice migration 007 made: a missing value announces itself,
--             a wrong one does not.
--
-- The FDC ids below were checked against the descriptions the USDA API returns
-- (api.nal.usda.gov, SR Legacy), not written from memory.
--
-- Not changed here, and why:
--   milk, 1% / 2% / nonfat / skim / evaporated milks
--             They map to "Milk, buttermilk, fluid, whole". That is a different
--             dairy product, but its calcium is within a few percent of milk's, and
--             removing nutrition from the 60+ recipes that use milk until an import
--             runs would be a larger regression than the error. Verified ids for
--             the next pass: 171265 whole, 171267 2%, 170872 1%. nonfat and
--             evaporated ids were not verified (API quota). scripts/tag_ingredients.py
--             refuses to use these ingredients as nutrient evidence meanwhile.
--   cheese    "cheese" alone names no single USDA record; it maps to Swiss, low
--             sodium (961 mg calcium/100 g). It needs a decision about which cheese
--             the recipes mean, not a lookup. Also excluded as tagging evidence.
--   unsweetened applesauce, frozen blueberries
--             Right food, different preparation (added ascorbic acid; sweetened).
--             That affects vitamin C and sugar, not identity. Excluded as evidence
--             for the affected nutrient only.
--
-- Fails rather than guesses if an ingredient is not in the state this was written
-- against, as 007 does. Safe to run again: an ingredient already corrected is skipped.
BEGIN;

CREATE TEMP TABLE _usda_fix (
    ingredient_name  TEXT NOT NULL,
    expected_record  TEXT NOT NULL,   -- what ingredient_source_map holds today
    new_record       TEXT NOT NULL,   -- the USDA FDC id it should hold
    new_description  TEXT NOT NULL,
    new_category     TEXT NOT NULL,
    donor_name       TEXT             -- ingredient already holding new_record, or NULL (pending import)
) ON COMMIT DROP;

INSERT INTO _usda_fix VALUES
    ('grapes',             '168575', '174683', 'Grapes, red or green (European type, such as Thompson seedless), raw', 'Fruits and Fruit Juices', 'green seedless grapes'),
    ('strawberry',         '173045', '167762', 'Strawberries, raw',                                                   'Fruits and Fruit Juices', 'strawberries'),
    ('parsley flakes',     '170416', '170930', 'Spices, parsley, dried',                                              'Spices and Herbs',        'dried parsley flakes'),
    ('oats',               '169063', '173904', 'Cereals, oats, regular and quick, not fortified, dry',                'Breakfast Cereals',       'quick oats'),
    ('oatmeal',            '169063', '173904', 'Cereals, oats, regular and quick, not fortified, dry',                'Breakfast Cereals',       'quick oats'),
    ('old fashioned oats', '169063', '173904', 'Cereals, oats, regular and quick, not fortified, dry',                'Breakfast Cereals',       'quick oats'),
    ('quick-cooking oatmeal','169063','173904','Cereals, oats, regular and quick, not fortified, dry',                'Breakfast Cereals',       'quick oats'),
    ('rolled oats',        '169063', '173904', 'Cereals, oats, regular and quick, not fortified, dry',                'Breakfast Cereals',       'quick oats'),
    ('Old mill oats',      '169063', '173904', 'Cereals, oats, regular and quick, not fortified, dry',                'Breakfast Cereals',       'quick oats'),
    ('Robin Hood oats',    '169063', '173904', 'Cereals, oats, regular and quick, not fortified, dry',                'Breakfast Cereals',       'quick oats'),
    ('orange',             '170502', '169097', 'Oranges, raw, all commercial varieties',                              'Fruits and Fruit Juices', NULL),
    ('sweet potatoes',     '169303', '168482', 'Sweet potato, raw, unprepared (Includes foods for USDA''s Food Distribution Program)', 'Vegetables and Vegetable Products', NULL),
    ('sun-dried tomatoes', '170457', '168567', 'Tomatoes, sun-dried',                                                 'Vegetables and Vegetable Products', NULL),
    ('tomato paste',       '170460', '170459', 'Tomato products, canned, paste, without salt added (Includes foods for USDA''s Food Distribution Program)', 'Vegetables and Vegetable Products', NULL),
    -- Provenance only: the nutrition rows were already removed by 007 and await the import.
    ('sesame seeds',       '167557', '170150', 'Seeds, sesame seeds, whole, dried',                                   'Nut and Seed Products',   NULL);

DO $$
DECLARE
    r        RECORD;
    v_id     UUID;
    v_old    TEXT;
    v_donor  UUID;
    v_dold   TEXT;
    v_copied INT;
    v_pending TEXT[] := '{}';
BEGIN
    FOR r IN SELECT * FROM _usda_fix LOOP
        SELECT ingredient_id INTO v_id FROM ingredients WHERE ingredient_name = r.ingredient_name;
        IF v_id IS NULL THEN
            RAISE EXCEPTION 'no ingredient named "%"', r.ingredient_name;
        END IF;
        SELECT source_record_id INTO v_old FROM ingredient_source_map
         WHERE ingredient_id = v_id AND source_id = 'usda_sr_legacy';
        IF v_old = r.new_record THEN
            RAISE NOTICE '"%" already corrected; skipped', r.ingredient_name;
            CONTINUE;
        END IF;
        IF v_old IS DISTINCT FROM r.expected_record THEN
            RAISE EXCEPTION '"%": expected source record % (the wrong one) or % (the correction), found %',
                r.ingredient_name, r.expected_record, r.new_record, v_old;
        END IF;

        IF r.donor_name IS NOT NULL THEN
            SELECT ingredient_id INTO v_donor FROM ingredients WHERE ingredient_name = r.donor_name;
            SELECT source_record_id INTO v_dold FROM ingredient_source_map
             WHERE ingredient_id = v_donor AND source_id = 'usda_sr_legacy';
            IF v_donor IS NULL OR v_dold IS DISTINCT FROM r.new_record THEN
                RAISE EXCEPTION '"%": donor "%" does not hold record % (holds %)',
                    r.ingredient_name, r.donor_name, r.new_record, v_dold;
            END IF;
        END IF;

        -- ingredients.usda_fdc_id is unique where set, so an id already held by the
        -- donor cannot be repeated. The wrong id is cleared either way.
        UPDATE ingredients
           SET usda_fdc_id = CASE WHEN EXISTS (SELECT 1 FROM ingredients o
                                                WHERE o.usda_fdc_id = r.new_record::bigint
                                                  AND o.ingredient_id <> v_id)
                                  THEN NULL ELSE r.new_record::bigint END,
               food_category = r.new_category
         WHERE ingredient_id = v_id;

        UPDATE ingredient_source_map
           SET source_record_id = r.new_record, source_description = r.new_description,
               match_score = NULL, matched_by = 'manual', matched_at = current_date
         WHERE ingredient_id = v_id AND source_id = 'usda_sr_legacy';

        DELETE FROM ingredient_nutrition WHERE ingredient_id = v_id AND source_id = 'usda_sr_legacy';
        IF r.donor_name IS NOT NULL THEN
            INSERT INTO ingredient_nutrition
                   (ingredient_id, nutrient_id, value_per_100g, unit, bioavailability_pct,
                    bioavailability_notes, usda_nutrient_code, data_quality_flag, source_id)
            SELECT v_id, nutrient_id, value_per_100g, unit, bioavailability_pct,
                   bioavailability_notes, usda_nutrient_code, data_quality_flag, source_id
              FROM ingredient_nutrition
             WHERE ingredient_id = v_donor AND source_id = 'usda_sr_legacy';
            GET DIAGNOSTICS v_copied = ROW_COUNT;
            IF v_copied = 0 THEN
                RAISE EXCEPTION '"%": donor "%" has no usda_sr_legacy rows to copy', r.ingredient_name, r.donor_name;
            END IF;
        ELSIF r.ingredient_name <> 'sesame seeds' THEN
            v_pending := v_pending || r.ingredient_name;
        END IF;
    END LOOP;

    IF array_length(v_pending, 1) > 0 THEN
        RAISE NOTICE 'No nutrition loaded for: %. Run scripts/fill_ingredient_nutrition.py --apply to import the real USDA values (also needed for sesame seeds).',
                     array_to_string(v_pending, ', ');
    END IF;
END;
$$;

COMMIT;
