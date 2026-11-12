-- 011_retract_cellophane_pasta_tag.sql
-- "cellophane noodle" is not pasta.
--
-- GLY-007 ("use al dente pasta", trigger ING_PASTA) is about wheat pasta. A
-- cellophane noodle is a mung-bean starch noodle: it has no al dente stage and
-- no USDA nutrition in this database (it matched nothing). The keyword "noodle"
-- tagged it anyway.
--
-- scripts/import_rules.py now excludes "cellophane", and
-- schema/seed/ingredient_rule_tags.sql was regenerated from it, so a fresh
-- load no longer carries the tag (the name is in ingredient_rule_tags_review.csv
-- instead). But that seed is "ON CONFLICT DO NOTHING": it never removes a row,
-- so a database that was loaded before the fix still has the tag. This removes
-- exactly that one row.
--
-- Deliberately narrow. It deletes one (ingredient, code) pair by name and code,
-- reports how many rows it removed, and does nothing if the ingredient or the
-- tag is absent, so running it twice is harmless.
BEGIN;

DO $$
DECLARE
    v_id UUID;
    v_removed INT;
BEGIN
    SELECT ingredient_id INTO v_id FROM ingredients WHERE ingredient_name = 'cellophane noodle';
    IF v_id IS NULL THEN
        RAISE NOTICE 'no ingredient named "cellophane noodle"; nothing to do';
        RETURN;
    END IF;
    DELETE FROM ingredient_rule_tags WHERE ingredient_id = v_id AND rule_code = 'ING_PASTA';
    GET DIAGNOSTICS v_removed = ROW_COUNT;
    RAISE NOTICE 'removed % ING_PASTA tag(s) from "cellophane noodle"', v_removed;
END;
$$;

COMMIT;
