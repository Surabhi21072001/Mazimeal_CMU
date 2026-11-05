"""Who is calling, decided by the server.

The browser signs in with Supabase and gets a JWT. Everything an admin request
claims about itself - the email on a submitted rule change, whether the caller
may approve one - is read out of that token here, after verifying its
signature. Nothing is read from the request body, because a field the browser
fills in is a field the browser can lie about.

Verification is local. The project issues ES256 tokens and publishes the
matching public keys at /auth/v1/.well-known/jwks.json, so this needs no
shared secret and no round trip to Supabase per request; PyJWKClient caches
the key set and refetches when a token arrives with an unknown `kid`, which is
what happens when the project rotates its signing key.

Which project to verify against is not configured separately. It is derived
from the database connection string the API is already using, because the two
have to be the same project: a token issued by project A says nothing about a
row in project B's tables. Deriving it makes that structural instead of a
convention someone has to keep. SUPABASE_URL still overrides, for a setup
where auth and data genuinely are split.

Who may approve a rule change comes from two places, and the difference
between them is deliberate:

    MAZI_ADMIN_EMAILS     comma-separated, in the server's environment
    app_admins            a table, editable from the admin screen

A table the admin screen can edit is a table that whoever reaches the admin
screen can add themselves to - which is why the environment list exists and
why nothing can change it through the API. It is the way back in when the
table is wrong. The table's first row comes from a migration, so becoming a
reviewer always starts outside the screen; what the screen allows is an
existing reviewer adding another, which is the feature.

The table is read per request rather than cached, so removing a reviewer takes
effect on their next call rather than whenever a cache would have expired.
"""
from __future__ import annotations

import os
from urllib.parse import unquote, urlsplit

from fastapi import Header, HTTPException

def _project_url() -> str:
    """The project's API root, e.g. https://abc.supabase.co.

    Taken from SUPABASE_URL when set. Otherwise read out of the Postgres
    connection string, which names the project in one of two places depending
    on how it connects:

        the pooler   postgresql://postgres.<ref>:...@aws-1-...pooler.supabase.com
        direct       postgresql://postgres:...@db.<ref>.supabase.co

    Returns "" when neither is available, which keeps every unauthenticated
    endpoint working and makes the authenticated ones answer 503.
    """
    explicit = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    if explicit:
        return explicit

    dsn = os.environ.get("SUPABASE_DB_URL") or os.environ.get("MAZIMEAL_DSN") or ""
    if not dsn:
        return ""
    # urlsplit, not string surgery: the password may contain @ or :.
    parts = urlsplit(dsn)
    user = unquote(parts.username or "")
    if user.startswith("postgres.") and len(user) > len("postgres."):
        return f"https://{user[len('postgres.'):]}.supabase.co"
    host = parts.hostname or ""
    if host.startswith("db.") and host.endswith(".supabase.co"):
        return f"https://{host[len('db.'):]}"
    return ""


SUPABASE_URL = _project_url()

# Supabase signs project tokens with "authenticated" as the audience.
AUDIENCE = "authenticated"

_jwk_client = None


def _client():
    """The cached JWKS client, built on first use.

    Built lazily so that importing this module - which api/app/main.py does at
    startup - never reaches the network, and a deployment with no SUPABASE_URL
    still serves every unauthenticated endpoint.
    """
    global _jwk_client
    if _jwk_client is None:
        if not SUPABASE_URL:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "auth_not_configured",
                    "hint": "no Supabase project found: set SUPABASE_URL, or a "
                            "SUPABASE_DB_URL this can read the project from",
                },
            )
        from jwt import PyJWKClient

        _jwk_client = PyJWKClient(
            f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json",
            cache_keys=True,
            lifespan=3600,
        )
    return _jwk_client


def env_admin_emails() -> set[str]:
    """Reviewers named in the server's environment.

    No request can change this, which is what makes it the way back in when
    the table below is wrong or empty.
    """
    raw = os.environ.get("MAZI_ADMIN_EMAILS", "")
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def admin_emails() -> set[str]:
    """Every reviewer: the environment list, plus the app_admins table.

    Imported inside the function because admin_people reaches the database and
    this module is imported at startup; keeping the import here means a
    deployment with no database still serves everything that needs no account.
    """
    from .admin_people import granted_emails

    return env_admin_emails() | granted_emails()


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail={"error": "no_token"})
    return authorization.split(" ", 1)[1].strip()


def verify(authorization: str | None) -> dict:
    """The token's claims, or 401.

    Signature, expiry and audience are all checked. A token this project did
    not issue fails at the signature; an expired one fails at `exp`; a token
    minted for another audience - a service key, say - fails at `aud`.
    """
    import jwt

    token = _bearer(authorization)
    try:
        key = _client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            key.key,
            algorithms=["ES256", "RS256"],
            audience=AUDIENCE,
            options={"require": ["exp", "sub"]},
        )
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail={"error": "token_expired"}) from None
    except Exception as exc:  # malformed, wrong key, wrong audience
        raise HTTPException(
            status_code=401, detail={"error": "bad_token", "reason": type(exc).__name__}
        ) from None


class Caller:
    """A verified identity, and whether it may approve."""

    def __init__(self, claims: dict):
        self.user_id = claims.get("sub")
        self.email = (claims.get("email") or "").lower()
        self.is_admin = bool(self.email) and self.email in admin_emails()

    def as_json(self) -> dict:
        return {"user_id": self.user_id, "email": self.email, "is_admin": self.is_admin}


def signed_in(authorization: str | None = Header(default=None)) -> Caller:
    """Any verified account. Enough to propose a rule change."""
    return Caller(verify(authorization))


def admin(authorization: str | None = Header(default=None)) -> Caller:
    """A verified account on the allowlist. Required to approve or reject one.

    A signed-in non-admin gets 403 rather than 401: the token was fine, the
    account simply is not a reviewer, and telling the two apart is what stops
    someone retrying with a fresh login.
    """
    caller = Caller(verify(authorization))
    if not caller.is_admin:
        raise HTTPException(
            status_code=403, detail={"error": "not_an_admin", "email": caller.email}
        )
    return caller
