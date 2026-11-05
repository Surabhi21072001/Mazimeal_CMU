-- 15_user_credentials.sql
-- Minimal login credentials for user_profile (MVP, no sessions/tokens).
--
-- Adds a username and a salted password hash. Passwords are NEVER stored in
-- plaintext: password_hash holds a PBKDF2-HMAC-SHA256 digest in the format
--   pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>
-- produced by scripts/auth.py (stdlib hashlib, no extra dependency).
--
-- Columns are nullable and added with IF NOT EXISTS so existing rows and
-- re-runs are safe. A user without credentials simply cannot log in yet.

ALTER TABLE user_profile ADD COLUMN IF NOT EXISTS username      VARCHAR(100);
ALTER TABLE user_profile ADD COLUMN IF NOT EXISTS password_hash TEXT;

-- Usernames must be unique when present (NULLs allowed for credential-less users).
CREATE UNIQUE INDEX IF NOT EXISTS uq_user_profile_username
    ON user_profile (lower(username))
    WHERE username IS NOT NULL;

COMMENT ON COLUMN user_profile.username      IS 'Login username (case-insensitive unique). NULL = no login set.';
COMMENT ON COLUMN user_profile.password_hash IS 'PBKDF2-HMAC-SHA256 digest: pbkdf2_sha256$iterations$salt$hash. Never plaintext.';
