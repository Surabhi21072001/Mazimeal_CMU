-- ============================================================================
--  002 · Rule change requests
--
--  Nothing writes to business_rules directly. A change is proposed as a row
--  here, a reviewer approves it, and only then does the rule table move - in
--  the same transaction that marks the request applied.
--
--  Two reasons it works this way rather than as a plain UPDATE behind an admin
--  form. The rules belong to the rules workstream, not to whoever has the
--  admin page open; and one rule applies to all 400 recipes, so a careless
--  edit changes every verdict in the product at once. The queue makes the
--  change reviewable before it is real, and because every applied change has
--  a row here with its before-snapshot, this table is also the audit log -
--  there is no second place to look.
--
--  Additive only. Safe to re-run.
--
--      psql "$SUPABASE_DB_URL" -f schema/migrations/002_rule_change_requests.sql
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.rule_change_requests (
    request_id     UUID         NOT NULL DEFAULT public.gen_ulid(),
    kind           TEXT         NOT NULL,
    rule_id        TEXT         NOT NULL,

    -- The fields the request would set, as submitted. JSONB rather than a
    -- mirror of business_rules' 24 columns: a request usually touches two or
    -- three of them, and a mirrored table would make every absent column
    -- indistinguishable from one deliberately set to NULL.
    proposed       JSONB        NOT NULL DEFAULT '{}'::jsonb,

    -- The whole business_rules row as it stood when the request was made.
    -- Compared again at approval time: if the rule has changed since, the
    -- reviewer is deciding about text that no longer exists, so applying it
    -- is refused rather than silently overwriting someone else's edit.
    before         JSONB,

    submitted_by   TEXT         NOT NULL,
    submitted_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    note           TEXT,

    status         TEXT         NOT NULL DEFAULT 'pending',
    decided_by     TEXT,
    decided_at     TIMESTAMPTZ,
    decision_note  TEXT,
    applied_at     TIMESTAMPTZ,

    CONSTRAINT pk_rule_change_requests PRIMARY KEY (request_id),
    CONSTRAINT ck_rcr_kind   CHECK (kind IN ('create', 'update', 'activate', 'deactivate')),
    CONSTRAINT ck_rcr_status CHECK (status IN ('pending', 'approved', 'rejected', 'stale')),
    -- A decision must say who made it, and an applied request must have been
    -- approved; neither is reconstructable afterwards if it is allowed to be
    -- missing.
    CONSTRAINT ck_rcr_decided CHECK (
        (status = 'pending' AND decided_by IS NULL AND decided_at IS NULL)
        OR (status <> 'pending' AND decided_by IS NOT NULL AND decided_at IS NOT NULL)),
    CONSTRAINT ck_rcr_applied CHECK (applied_at IS NULL OR status = 'approved'),
    -- 'create' invents a rule id, so there is no prior row to snapshot; every
    -- other kind edits one that must exist.
    CONSTRAINT ck_rcr_before CHECK ((kind = 'create') = (before IS NULL))
);

COMMENT ON TABLE  public.rule_change_requests            IS 'Proposed changes to business_rules, and the audit log of applied ones. Nothing edits business_rules outside this queue.';
COMMENT ON COLUMN public.rule_change_requests.proposed   IS 'Only the business_rules columns this request sets. Absent means unchanged.';
COMMENT ON COLUMN public.rule_change_requests.before     IS 'The target row at submission time. Re-checked on approval to refuse applying over a newer edit.';
COMMENT ON COLUMN public.rule_change_requests.submitted_by IS 'Email from the verified Supabase JWT. Never taken from the request body.';
COMMENT ON COLUMN public.rule_change_requests.status     IS 'pending | approved | rejected | stale. stale means the rule moved under the request before anyone decided.';

CREATE INDEX IF NOT EXISTS ix_rcr_pending ON public.rule_change_requests (submitted_at DESC)
    WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS ix_rcr_rule ON public.rule_change_requests (rule_id, submitted_at DESC);

-- ---------------------------------------------------------------------------
-- No policies, on purpose.
--
-- RLS on with nothing granted means the browser's anon and authenticated keys
-- cannot read or write this table at all. Every path to it goes through our
-- API, which connects as the owner and checks the caller's token against the
-- admin allowlist first. A reviewer identity that the browser could set is
-- not an identity.
-- ---------------------------------------------------------------------------
ALTER TABLE public.rule_change_requests ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON public.rule_change_requests FROM anon, authenticated;
    END IF;
END $$;

COMMIT;
