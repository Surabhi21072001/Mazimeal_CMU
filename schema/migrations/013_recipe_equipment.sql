-- 013_recipe_equipment.sql
-- Equipment a recipe uses, so SYN-012 (iron cookware with moist acidic foods) can be decided.
--
-- SYN-012's trigger is PROC_COOKWARE, which is a fact about HOW a recipe is cooked, not
-- about any ingredient, so it can never be an ingredient_rule_tags row. Two things are
-- missing for it:
--
--   1. a vocabulary for cookware (rule_codes has PAIR_CAST_IRON, the action, but nothing
--      that names the equipment itself), and
--   2. somewhere to keep what is known about a recipe's equipment, with where it came from
--      and whether a person has looked at it.
--
-- What this does NOT do: it does not populate recipe_equipment from the recipe text. The
-- engine extracts equipment from the steps at evaluation time (scripts/equipment_facts.py),
-- deterministically, and does not write what it finds. This table holds only what a person
-- or a structured import states, plus corrections: a 'rejected' row suppresses the same
-- equipment_code from extraction for that recipe.
--
-- Additive and idempotent: safe to run more than once. Touches no existing row.
--
--     psql -d <disposable local db> -v ON_ERROR_STOP=1 -f schema/migrations/013_recipe_equipment.sql
BEGIN;

-- Equipment vocabulary. Each code says what the recipe text can establish, not what it
-- means for a nutrient; the rule decides that.
INSERT INTO rule_codes (code, code_type, display_name, description, needs_review)
VALUES
    ('EQUIP_CAST_IRON', 'EQUIP', 'Cast iron cookware',
     'Bare cast iron: a recipe step names cast iron cookware. The SYN-012 recommendation is already followed.', FALSE),
    ('EQUIP_ENAMELED_CAST_IRON', 'EQUIP', 'Enameled cast iron cookware',
     'Cast iron with an enamel coating. SYN-012 does not say whether a coated vessel counts, so it is held for review.', TRUE),
    ('EQUIP_DUTCH_OVEN', 'EQUIP', 'Dutch oven',
     'A Dutch oven can be bare or enameled cast iron, or another metal; the step does not say which, so it is held for review.', TRUE),
    ('EQUIP_NONIRON_COOKWARE', 'EQUIP', 'Named non-iron cookware',
     'A step names a cooking vessel with a non-iron material (nonstick, stainless steel, aluminum, ceramic, copper).', FALSE),
    ('EQUIP_COOKWARE_UNSPECIFIED', 'EQUIP', 'Cookware, material not stated',
     'A step names a cooking vessel (skillet, pot, pan...) without a material. Not evidence that it is, or is not, iron.', FALSE)
ON CONFLICT (code) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.recipe_equipment (
    recipe_id      UUID        NOT NULL,
    equipment_code TEXT        NOT NULL,
    -- Where the row came from. Instruction extraction at evaluation time is NOT stored here;
    -- 'instruction_extraction' is for an extraction a person chose to persist.
    source         TEXT        NOT NULL,
    confidence     TEXT        NOT NULL,
    review_status  TEXT        NOT NULL DEFAULT 'auto',
    evidence_step  SMALLINT,
    evidence_text  TEXT,
    reviewed_by    TEXT,
    reviewed_at    TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_recipe_equipment PRIMARY KEY (recipe_id, equipment_code, source),
    CONSTRAINT fk_re_recipe FOREIGN KEY (recipe_id)
        REFERENCES public.recipes (recipe_id) ON DELETE CASCADE,
    CONSTRAINT fk_re_code FOREIGN KEY (equipment_code)
        REFERENCES public.rule_codes (code),
    CONSTRAINT ck_re_source CHECK (source IN ('structured', 'instruction_extraction', 'admin_review')),
    CONSTRAINT ck_re_confidence CHECK (confidence IN ('high', 'medium', 'low')),
    CONSTRAINT ck_re_review CHECK (review_status IN ('auto', 'pending_review', 'confirmed', 'rejected')),
    CONSTRAINT ck_re_step CHECK (evidence_step IS NULL OR evidence_step > 0),
    -- A person's decision must say whose it was and when.
    CONSTRAINT ck_re_reviewer CHECK (
        review_status NOT IN ('confirmed', 'rejected') OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)),
    -- Only equipment codes belong here.
    CONSTRAINT ck_re_equip_code CHECK (equipment_code LIKE 'EQUIP\_%')
);
CREATE INDEX IF NOT EXISTS ix_re_recipe ON public.recipe_equipment (recipe_id);
CREATE INDEX IF NOT EXISTS ix_re_pending ON public.recipe_equipment (recipe_id) WHERE review_status = 'pending_review';

COMMENT ON TABLE public.recipe_equipment IS
    'Equipment a recipe uses, from structured data or a reviewer. Read by scripts/recipe_facts.py; consumed by SYN-012.';
COMMENT ON COLUMN public.recipe_equipment.review_status IS
    'auto | pending_review | confirmed | rejected. A rejected row suppresses extraction of the same code for this recipe.';
COMMENT ON COLUMN public.recipe_equipment.evidence_step IS
    'recipe_steps.step_number that mentions the equipment.';

-- Written by the API and by reviewers only: RLS on with no policy, like rule_change_requests
-- and recipe_nutrition_reviews. The engine connects as the table owner and is unaffected.
ALTER TABLE public.recipe_equipment ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON public.recipe_equipment FROM anon, authenticated;
    END IF;
END $$;

COMMIT;
