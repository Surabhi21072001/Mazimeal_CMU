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

Two environment variables:

    SUPABASE_URL          the project, e.g. https://abc.supabase.co
    MAZI_ADMIN_EMAILS     comma-separated, who may approve a rule change

The allowlist lives in the environment rather than in a table on purpose: a
table that the admin page can edit is a table that an attacker who reaches the
admin page can add themselves to.
"""
from __future__ import annotations

import os

from fastapi import Header, HTTPException

SUPABASE_URL = (os.environ.get("SUPABASE_URL") or "").rstrip("/")

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
                detail={"error": "auth_not_configured", "hint": "SUPABASE_URL is not set"},
            )
        from jwt import PyJWKClient

        _jwk_client = PyJWKClient(
            f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json",
            cache_keys=True,
            lifespan=3600,
        )
    return _jwk_client


def admin_emails() -> set[str]:
    raw = os.environ.get("MAZI_ADMIN_EMAILS", "")
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


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
