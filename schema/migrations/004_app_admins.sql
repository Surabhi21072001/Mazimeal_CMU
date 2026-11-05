-- 004_app_admins.sql
-- Who may approve a rule change, as a table the admin screen can edit.
--
-- This replaces nothing: MAZI_ADMIN_EMAILS still works and still counts. It
-- adds a second source so that growing the reviewer list does not need a
-- deployment, which was the only way to do it before.
--
-- The obvious objection is the one that kept the allowlist in the environment
-- in the first place: a table the admin screen can edit is a table that
-- whoever reaches the admin screen can add themselves to. That is true, and
-- the answer is not to make the table safe - it cannot be - but to keep a
-- source of authority outside it:
--
--   * MAZI_ADMIN_EMAILS is read from the server's environment. No request can
--     change it, so a deployment always retains a way back in even if every
--     row here is wrong.
--   * The first row comes from this migration, run by someone with the
--     database password. Bootstrapping from inside the page is impossible by
--     construction: granting requires already being an admin.
--
-- So the escalation that remains is admin -> admin, which is what the feature
-- is for. What it does not allow is stranger -> admin.
--
-- Revocation is immediate: auth.py reads this table per request rather than
-- caching it, because a cache would mean a removed reviewer keeps approving
-- for the length of the cache.

BEGIN;

CREATE TABLE IF NOT EXISTS app_admins (
    email       TEXT        NOT NULL,
    granted_by  TEXT        NOT NULL,
    granted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    note        TEXT,

    CONSTRAINT pk_app_admins PRIMARY KEY (email),

    -- Stored lowercase and trimmed, because the comparison in auth.py
    -- lowercases the token's email and a stray capital would silently mean
    -- "this person is not an admin" with the row sitting right there.
    CONSTRAINT ck_app_admins_email_normal CHECK (email = lower(btrim(email))),

    -- Not an attempt to validate an address - that is not something a CHECK
    -- can do. It only rejects the shapes that are certainly not one, so a
    -- typo'd row cannot sit in the list looking like a reviewer.
    CONSTRAINT ck_app_admins_email_shape CHECK (email LIKE '%_@_%.__%'),

    CONSTRAINT ck_app_admins_granted_by CHECK (nullif(btrim(granted_by), '') IS NOT NULL)
);

COMMENT ON TABLE  app_admins            IS 'Who may approve a rule change, in addition to MAZI_ADMIN_EMAILS. Editable from the admin screen.';
COMMENT ON COLUMN app_admins.granted_by IS 'The email of the admin who added this row, or ''bootstrap migration'' for the first one.';
COMMENT ON COLUMN app_admins.note       IS 'Why, in the granting admin''s words. Optional.';

-- Closed to the browser. The anon and authenticated keys reach Postgres
-- directly, so a table with no policy and no grant is the only kind they
-- cannot read: row-level security with zero policies denies everything, and
-- the API connects as the owner, which RLS does not apply to.
ALTER TABLE app_admins ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON app_admins FROM anon, authenticated;

-- The bootstrap. Everything else is granted from the screen; this one cannot
-- be, because granting requires an admin and at this point there is none.
INSERT INTO app_admins (email, granted_by, note)
VALUES ('caliber1385@gmail.com', 'bootstrap migration',
        'First reviewer. Added by 004_app_admins.sql so the screen has somewhere to start.')
ON CONFLICT (email) DO NOTHING;

COMMIT;
