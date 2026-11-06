-- 008_map_unmapped_ingredients.sql
-- Give three ingredients the USDA food they are named for.
--
-- Of the 206 ingredients the 50 seed recipes use, five had no usda_fdc_id at
-- all, so nothing could be imported for them and no check could tell whether
-- what they did hold was right. Three have an exact match in SR Legacy:
--
--   cellophane noodle   174258  Noodles, chinese, cellophane or long rice
--                               (mung beans), dehydrated
--   firm tofu           172448  Tofu, firm, prepared with calcium sulfate
--                               and magnesium chloride (nigari)
--   ground cardamom     170919  Spices, cardamom
--
-- cellophane noodle held nothing at all - 0 of 28 nutrients - so it was
-- contributing zero to every total it appears in. firm tofu is 3024 g of one
-- recipe, the largest single weight in the whole seed set, and was missing
-- four nutrients. Spices, cardamom reports only 23 of our 28, which is why
-- that ingredient was short five: the source is partial, as it was for beef.
--
-- Three are left unmapped, for two different reasons.
--
-- No USDA entry comes back from the API:
--
--   white pepper      1 g of one recipe. "Spices, pepper, white" does not
--                     come back; the search returns fresh peppers. Not worth
--                     a substitute at this weight.
--   orange, zest of   100 g of one recipe, and there is no orange-peel entry
--                     (there is a lemon-peel one). The 100 g is itself
--                     suspect - that is most of a cup of zest, which no
--                     recipe calls for - so the quantity wants reviewing
--                     before the nutrition does.
--
-- Blocked by a constraint that should probably not exist:
--
--   ground cardamom   its food is 170919, "Spices, cardamom", and the
--                     ingredient named plain `cardamom` already holds that
--                     id. uq_ingredients_fdc makes usda_fdc_id unique across
--                     the whole table, so two ingredient strings cannot share
--                     a USDA food - and "cardamom" and "ground cardamom" are
--                     exactly that: two things a recipe writes, one food.
--                     Recipe text is not a controlled vocabulary, so this
--                     will keep happening (`firm tofu` against `extra firm
--                     tofu` is the same shape).
--
--                     Nothing is lost today: ground cardamom already holds
--                     the same 23 nutrients, imported by name rather than by
--                     id, which is also why only 267 of 559 ingredients have
--                     an id at all. Dropping that constraint is a schema
--                     decision for whoever owns the table, so this migration
--                     skips the row and says so rather than forcing it.
--
-- No values are inserted here. After this,
--     python3 scripts/fill_ingredient_nutrition.py --apply
-- imports them from the newly correct ids, so every number stays traceable to
-- a fetch rather than being typed into a schema file.

BEGIN;

DO $$
DECLARE
    r RECORD;
    v_current BIGINT;
BEGIN
    FOR r IN
        SELECT * FROM (VALUES
            ('cellophane noodle', 174258::BIGINT, 'Cereal Grains and Pasta'),
            ('firm tofu',         172448::BIGINT, 'Legumes and Legume Products'),
            ('ground cardamom',   170919::BIGINT, 'Spices and Herbs')
        ) AS v(name, fdc_id, category)
    LOOP
        SELECT usda_fdc_id INTO v_current
          FROM ingredients WHERE ingredient_name = r.name;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'no ingredient named %', r.name;
        END IF;

        -- usda_fdc_id is unique table-wide, so another ingredient string
        -- naming the same food takes the id first. Skipping is correct here:
        -- the alternative is to fail the whole migration over a row that
        -- loses nothing by staying unmapped.
        IF v_current IS NULL AND EXISTS (
               SELECT 1 FROM ingredients
                WHERE usda_fdc_id = r.fdc_id AND ingredient_name <> r.name) THEN
            RAISE NOTICE '% skipped: % is already held by %', r.name, r.fdc_id,
                (SELECT ingredient_name FROM ingredients WHERE usda_fdc_id = r.fdc_id);
            CONTINUE;
        END IF;

        -- Only ever fills a blank. An id already set was either set by this
        -- migration or by someone who knew more than it does, and silently
        -- replacing it is how a correction becomes a regression.
        IF v_current IS NULL THEN
            UPDATE ingredients
               SET usda_fdc_id   = r.fdc_id,
                   food_category = CASE
                       WHEN food_category IS NULL OR food_category = 'Uncategorized'
                       THEN r.category ELSE food_category END
             WHERE ingredient_name = r.name;
            RAISE NOTICE '% -> %', r.name, r.fdc_id;
        ELSIF v_current = r.fdc_id THEN
            RAISE NOTICE '% already mapped to %', r.name, r.fdc_id;
        ELSE
            RAISE NOTICE '% already has id % - left alone', r.name, v_current;
        END IF;
    END LOOP;
END;
$$;

COMMIT;
