-- ============================================================================
--  013 · Reviewed suggestion text, as versions
--
--  The review screen's edits used to live in the reviewer's own browser
--  (localStorage, key "mazimeal:review"). That made every correction private
--  to one machine: a second reviewer saw the model's text again, the cook
--  screen showed the edit only to the person who made it, and clearing site
--  data threw the work away. A correction is a statement about the recipe, so
--  it belongs where the recipe is.
--
--  Why versions and not one current row
--  ------------------------------------
--  The number this screen exists to produce is "how often was the model left
--  alone". That is only countable if a review which changed nothing still
--  writes something: an absence of rows cannot be told apart from an absence
--  of reviewers. So every decision appends a row, including "confirmed, no
--  change" and including a revert. Version 1 is always what the model wrote,
--  and it is kept forever so a diff is readable years later.
--
--  Nothing is ever updated in place. Two reviewers who disagree both leave a
--  row, in order.
--
--  What a version is allowed to say
--  --------------------------------
--  suggestions / summary        the text, as shown
--  rules_removed                "this rule does not apply to THIS recipe".
--                               It never touches business_rules, which the
--                               research workstream owns and which applies to
--                               400 other recipes.
--  status_overrides             per rule, the reviewer's own satisfied /
--                               not_satisfied call
--  position_overrides           which step or ingredient line a tip belongs on
--  headline_rule_id             which rule the cook screen should lead with
--  not_optimizable              nothing here is worth saying at all
--
--  JSONB rather than child tables because none of it is queried by field: the
--  screen reads a whole version or none of it, and the shape is still moving.
--
--  reviewer comes from the verified Supabase JWT in the API, never from the
--  request body, the same rule as rule_change_requests and the nutrition
--  verdicts.
--
--  Additive only. Safe to re-run.
--
--      psql "$SUPABASE_DB_URL" -f schema/migrations/013_recipe_content_versions.sql
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.recipe_content_versions (
    version_id          UUID        NOT NULL DEFAULT public.gen_ulid(),
    recipe_id           UUID        NOT NULL,

    -- Per recipe, starting at 1. Allocated by the API inside one transaction
    -- against the unique constraint below, so two reviewers saving at the same
    -- moment cannot both write version 4.
    version             INT         NOT NULL,
    parent              INT,

    -- 'model:<name>' on version 1, 'human:<email>' on a review.
    author              TEXT        NOT NULL,

    -- recipe_id | sorted rule ids | model, as the screen computed it. A
    -- version whose fingerprint no longer matches the recipe was written
    -- against different rules, and saying so is the only way to tell a stale
    -- edit from a current one.
    inputs_fingerprint  TEXT,

    suggestions         JSONB       NOT NULL DEFAULT '[]'::jsonb,
    summary             JSONB,
    rules_removed       JSONB       NOT NULL DEFAULT '[]'::jsonb,
    status_overrides    JSONB       NOT NULL DEFAULT '{}'::jsonb,
    position_overrides  JSONB       NOT NULL DEFAULT '{}'::jsonb,
    headline_rule_id    TEXT,
    not_optimizable     BOOLEAN     NOT NULL DEFAULT FALSE,

    -- The decision. NULL on version 1: the model's own output is not a review
    -- of itself, and counting it as one would inflate every ratio.
    outcome             TEXT,
    tags                JSONB       NOT NULL DEFAULT '[]'::jsonb,
    note                TEXT,
    reviewer            TEXT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT pk_recipe_content_versions PRIMARY KEY (version_id),
    CONSTRAINT uq_rcv_recipe_version UNIQUE (recipe_id, version),
    CONSTRAINT fk_rcv_recipe FOREIGN KEY (recipe_id)
        REFERENCES public.recipes (recipe_id) ON DELETE CASCADE,
    CONSTRAINT ck_rcv_version CHECK (version >= 1),
    CONSTRAINT ck_rcv_outcome CHECK (
        outcome IS NULL
        OR outcome IN ('confirmed_unchanged', 'edited', 'rejected', 'reverted_to_original')
    ),
    -- Version 1 is the model's; every later one is somebody's decision. Both
    -- halves matter: a review with no outcome is uncountable, and an outcome
    -- on version 1 would mean the model reviewed itself.
    CONSTRAINT ck_rcv_outcome_on_review CHECK ((version = 1) = (outcome IS NULL)),
    CONSTRAINT ck_rcv_reviewer CHECK (
        outcome IS NULL OR nullif(btrim(reviewer), '') IS NOT NULL
    ),
    CONSTRAINT ck_rcv_parent CHECK ((version = 1) = (parent IS NULL))
);

COMMENT ON TABLE  public.recipe_content_versions                    IS 'Reviewed suggestion text, appended as versions. Version 1 is the model''s; the highest version is current.';
COMMENT ON COLUMN public.recipe_content_versions.outcome            IS 'confirmed_unchanged | edited | rejected | reverted_to_original. NULL only on version 1.';
COMMENT ON COLUMN public.recipe_content_versions.rules_removed      IS 'Rule ids that do not apply to THIS recipe. Never changes business_rules.';
COMMENT ON COLUMN public.recipe_content_versions.inputs_fingerprint IS 'recipe_id|sorted rule ids|model at the time of writing. A mismatch means the version is about older rules.';
COMMENT ON COLUMN public.recipe_content_versions.reviewer           IS 'Email from the verified Supabase JWT. Never taken from the request body.';

-- The one read that happens on every cook-screen visit: the newest version of
-- one recipe.
CREATE INDEX IF NOT EXISTS ix_rcv_recipe ON public.recipe_content_versions (recipe_id, version DESC);

-- API-only, like rule_change_requests and recipe_nutrition_reviews: RLS on
-- with no policy, so neither the anon nor the authenticated key reaches this
-- table from a browser. A reviewer identity the browser could set is not an
-- identity, and these rows are the record of who decided what.
ALTER TABLE public.recipe_content_versions ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON public.recipe_content_versions FROM anon, authenticated;
    END IF;
END $$;

COMMIT;
