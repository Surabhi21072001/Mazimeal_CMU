-- ============================================================================
--  003 · Nutrition plausibility reviews
--
--  A person's judgement on whether a recipe's nutrition can be right. It is
--  not the same question as whether the suggestion text is good, which the
--  review screen already asks: this one is about the numbers, and the answer
--  is what tells the data workstream which recipes to open first.
--
--  Why the numbers are stored with the verdict
--  -------------------------------------------
--  energy_ratio and flags are a snapshot of what the reviewer was looking at.
--  The whole point of the exercise is that the quantities get fixed, and once
--  they are, a bare "implausible" against a recipe that now computes correctly
--  is unreadable - there would be no way to tell a stale verdict from a
--  current one. With the snapshot, a verdict whose ratio no longer matches is
--  visibly about an older version of the data.
--
--  Reviews accumulate; the newest per recipe is the current one. Nothing is
--  updated in place, so disagreement between two reviewers survives.
--
--  Additive only. Safe to re-run.
--
--      psql "$SUPABASE_DB_URL" -f schema/migrations/003_nutrition_reviews.sql
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.recipe_nutrition_reviews (
    review_id    UUID         NOT NULL DEFAULT public.gen_ulid(),
    recipe_id    UUID         NOT NULL,
    verdict      TEXT         NOT NULL,
    reason       TEXT,

    -- What the screen showed at the time: computed energy over published
    -- energy, and the per-line counts behind it.
    energy_ratio NUMERIC(8,3),
    flags        JSONB,

    reviewer     TEXT         NOT NULL,
    reviewed_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT pk_recipe_nutrition_reviews PRIMARY KEY (review_id),
    CONSTRAINT fk_rnr_recipe FOREIGN KEY (recipe_id)
        REFERENCES public.recipes (recipe_id) ON DELETE CASCADE,
    CONSTRAINT ck_rnr_verdict CHECK (verdict IN ('plausible', 'implausible', 'needs_data')),
    -- "Implausible" without a reason is an opinion nobody can act on, and
    -- acting on it is the only reason to record it.
    CONSTRAINT ck_rnr_reason CHECK (verdict = 'plausible' OR nullif(btrim(reason), '') IS NOT NULL)
);

COMMENT ON TABLE  public.recipe_nutrition_reviews              IS 'Human verdicts on whether a recipe''s nutrition can be right. Newest row per recipe is current.';
COMMENT ON COLUMN public.recipe_nutrition_reviews.verdict      IS 'plausible | implausible | needs_data. needs_data means the numbers cannot be judged yet, not that they are wrong.';
COMMENT ON COLUMN public.recipe_nutrition_reviews.energy_ratio IS 'Computed energy / published energy as shown to the reviewer. A verdict whose ratio no longer matches is about older data.';
COMMENT ON COLUMN public.recipe_nutrition_reviews.reviewer     IS 'Email from the verified Supabase JWT. Never taken from the request body.';

CREATE INDEX IF NOT EXISTS ix_rnr_recipe ON public.recipe_nutrition_reviews (recipe_id, reviewed_at DESC);

-- API-only, like rule_change_requests: RLS on with no policy, so neither the
-- anon nor the authenticated key reaches this table from a browser. A reviewer
-- identity the browser could set is not an identity.
ALTER TABLE public.recipe_nutrition_reviews ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON public.recipe_nutrition_reviews FROM anon, authenticated;
    END IF;
END $$;

COMMIT;
