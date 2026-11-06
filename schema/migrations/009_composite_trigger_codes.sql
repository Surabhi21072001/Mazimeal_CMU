-- 009_composite_trigger_codes.sql
-- Let a trigger code require two ingredient classes present together.
--
-- Two rules cannot be matched by the current mechanism, and it is not a
-- tagging problem. ingredient_rule_tags holds one ingredient and one code, so
-- it can say "this ingredient is a legume"; it cannot say "this recipe has a
-- legume and a grain". The two rules that need that are:
--
--   SYN-007  ING_LEGUME_GRAIN         "legumes and grains"
--            Complete limiting amino acids across the day
--   SYN-009  ING_ALLIUM_GRAIN_LEGUME  "garlic/onion plus grain or legume"
--            Allium with iron/zinc-rich grains or legumes
--
-- Tagging the union instead - every legume and every grain with the same code
-- - makes the rule fire when either is present. Measured over the 50 seed
-- recipes: SYN-009 would fire on 46 of them while only 17 contain both, wrong
-- 63% of the time, and SYN-007 on 25 against 5, wrong 80%.
--
-- So a composite code is defined as a set of component codes, and fires only
-- when every component is tagged on some ingredient of the recipe. The
-- components are ordinary codes, tagged the ordinary way, so nothing about
-- ingredient_rule_tags changes and a composite needs no tags of its own.
--
-- This table is the only new concept. detect_rules.py reads it and adds the
-- composites whose components are all present; a database without the table
-- behaves exactly as before.

BEGIN;

-- Two component classes the rules need and rule_codes did not have. Alliums
-- existed only as ING_GARLIC, which excludes onion, and grains existed only
-- inside the ING_GRAIN_LEGUME union, which cannot be used as a component of
-- "legume AND grain" because it already includes legumes.
INSERT INTO rule_codes (code, code_type, display_name, description, needs_review)
VALUES
    ('ING_ALLIUM', 'ING', 'Allium',
     'Garlic, onion, shallot, leek, scallion, chive. Component of '
     'ING_ALLIUM_GRAIN_LEGUME. Broader than ING_GARLIC, which is garlic only.',
     FALSE),
    ('ING_GRAIN', 'ING', 'Grain',
     'Cereal grains and products made from them. Component of '
     'ING_LEGUME_GRAIN. Distinct from ING_GRAIN_LEGUME, which is the union of '
     'grains and legumes and so cannot express "grain and legume".',
     FALSE)
ON CONFLICT (code) DO NOTHING;

CREATE TABLE IF NOT EXISTS rule_code_components (
    composite_code TEXT        NOT NULL,
    component_code TEXT        NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT pk_rule_code_components PRIMARY KEY (composite_code, component_code),

    CONSTRAINT fk_rcc_composite FOREIGN KEY (composite_code)
        REFERENCES rule_codes (code) ON DELETE CASCADE,
    CONSTRAINT fk_rcc_component FOREIGN KEY (component_code)
        REFERENCES rule_codes (code) ON DELETE CASCADE,

    -- A code cannot be its own component: that would make it fire on itself
    -- and the engine would never be able to satisfy it.
    CONSTRAINT ck_rcc_not_self CHECK (composite_code <> component_code)
);

COMMENT ON TABLE rule_code_components IS
    'A composite trigger code and the codes that must all be present for it to fire. Read by scripts/detect_rules.py.';
COMMENT ON COLUMN rule_code_components.composite_code IS
    'The trigger_code a rule names. It is never tagged on an ingredient itself.';
COMMENT ON COLUMN rule_code_components.component_code IS
    'An ordinary code, tagged on ingredients as usual. All of a composite''s components must be present.';

INSERT INTO rule_code_components (composite_code, component_code)
VALUES
    -- SYN-007: legumes and grains, for complementary amino acids.
    ('ING_LEGUME_GRAIN',        'ING_LEGUME'),
    ('ING_LEGUME_GRAIN',        'ING_GRAIN'),
    -- SYN-009: an allium with a grain or legume. The second component is the
    -- existing union code, because the rule itself says "grain or legume".
    ('ING_ALLIUM_GRAIN_LEGUME', 'ING_ALLIUM'),
    ('ING_ALLIUM_GRAIN_LEGUME', 'ING_GRAIN_LEGUME')
ON CONFLICT (composite_code, component_code) DO NOTHING;

-- A composite must not also be tagged directly: the engine would then report
-- it both ways and the "all components present" guarantee would be a lie.
DELETE FROM ingredient_rule_tags
 WHERE rule_code IN (SELECT composite_code FROM rule_code_components);

COMMIT;
