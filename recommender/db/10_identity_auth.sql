-- ============================================================================
--  Sheet 01 · Identity & Authentication
--  users · sessions · audit_log
--
--  NOTE ON TIMESTAMPS: the workbook specifies TIMESTAMP. This build uses
--  TIMESTAMPTZ throughout. A nutrition app spanning US/GB/DE/CH (see
--  households.country_region) cannot store naive local timestamps without
--  eventually corrupting meal timing and DST-crossing daily logs. This is the
--  one deliberate, global deviation from the sheet.
--
--  Foreign keys are declared in 85_foreign_keys.sql, not inline, because the
--  workbook contains cross-domain references in both directions.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- users · ~1M rows · 1 row per registered account
-- ---------------------------------------------------------------------------
CREATE TABLE public.users (
    user_id         UUID          NOT NULL DEFAULT public.gen_ulid(),
    email           VARCHAR(255)  NOT NULL,
    email_verified  BOOLEAN       NOT NULL DEFAULT FALSE,
    username        VARCHAR(100)  NOT NULL,
    password_hash   VARCHAR(255)  NOT NULL,
    role            VARCHAR(20)   NOT NULL DEFAULT 'user',
    mfa_secret      VARCHAR(100),
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ,

    CONSTRAINT pk_users            PRIMARY KEY (user_id),
    CONSTRAINT uq_users_username   UNIQUE (username),
    CONSTRAINT ck_users_role       CHECK (role IN ('user', 'admin', 'dietitian', 'support')),
    -- "normalise to lowercase on insert" — enforced rather than trusted, so the
    -- unique index on lower(email) in 90_indexes.sql can never be bypassed.
    CONSTRAINT ck_users_email_lc   CHECK (email = lower(email)),
    CONSTRAINT ck_users_email_fmt  CHECK (email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'),
    CONSTRAINT ck_users_username   CHECK (username ~ '^[A-Za-z0-9_]{3,50}$')
);

COMMENT ON TABLE  public.users                IS 'Registered accounts. Soft-deleted only — never hard-delete (audit trail).';
COMMENT ON COLUMN public.users.password_hash  IS 'bcrypt cost>=12. Rehash on login when the stored cost is below current policy.';
COMMENT ON COLUMN public.users.mfa_secret     IS 'PHI-ADJACENT: TOTP secret. Encrypt at rest (AES-256) — see 94_security_phi.sql.';
COMMENT ON COLUMN public.users.deleted_at     IS 'Soft delete. Every query against this table must filter deleted_at IS NULL.';

-- ---------------------------------------------------------------------------
-- sessions · ~10M active rows · SCALE: RANGE(created_at), monthly partitions
-- ---------------------------------------------------------------------------
CREATE TABLE public.sessions (
    session_id          UUID          NOT NULL DEFAULT public.gen_ulid(),
    user_id             UUID          NOT NULL,
    device_fingerprint  VARCHAR(200),
    ip_address          INET,
    expires_at          TIMESTAMPTZ   NOT NULL,
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
    revoked_at          TIMESTAMPTZ,

    CONSTRAINT pk_sessions          PRIMARY KEY (:pk_sessions),
    CONSTRAINT ck_sessions_expiry   CHECK (expires_at > created_at)
) :part_sessions ;

COMMENT ON TABLE  public.sessions            IS 'Durable session records. Hot sessions live in Redis (session:{id}); this is the persistence tier.';
COMMENT ON COLUMN public.sessions.session_id IS 'JWT jti claim or opaque token id.';
COMMENT ON COLUMN public.sessions.ip_address IS 'GDPR: consider storing a salted hash rather than the raw address.';

-- ---------------------------------------------------------------------------
-- audit_log · ~50M rows/yr @ 1M users · HIPAA change tracking
-- SCALE: RANGE(occurred_at), monthly partitions, archived to S3 after 24 months
--
-- BIGINT identity rather than UUID: this table is append-only and never joined
-- on the surrogate key, so a sequential integer is both smaller and faster.
-- ---------------------------------------------------------------------------
CREATE TABLE public.audit_log (
    log_id      BIGINT       NOT NULL GENERATED ALWAYS AS IDENTITY,
    user_id     UUID,
    action      VARCHAR(80)  NOT NULL,
    table_name  VARCHAR(80),
    record_id   UUID,
    old_values  JSONB,
    new_values  JSONB,
    ip_address  INET,
    occurred_at TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT pk_audit_log PRIMARY KEY (:pk_audit_log)
) :part_audit_log ;

COMMENT ON TABLE  public.audit_log            IS 'HIPAA-compliant change log. Append-only; drop whole partitions rather than DELETE.';
COMMENT ON COLUMN public.audit_log.user_id    IS 'NULL for system-originated events. No FK cascade — audit rows outlive their subject.';
COMMENT ON COLUMN public.audit_log.action     IS 'Dotted event name, e.g. profile.update / condition.add / recipe.view.';
COMMENT ON COLUMN public.audit_log.old_values IS 'Changed keys only, not the whole row — keeps JSONB small at 1B+ rows.';
