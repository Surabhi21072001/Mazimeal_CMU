#!/usr/bin/env python3
"""Minimal password hashing for the MVP login (stdlib only, no dependencies).

Passwords are stored as a salted PBKDF2-HMAC-SHA256 digest, never plaintext:

    pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>

hash_password() produces that string; verify_password() checks a candidate
against it using a constant-time compare. This is a reasonable baseline; a
production system would still add rate limiting, account lockout, and a
session/token layer (not in scope here).

CLI (set or reset a user's login):
    python3 scripts/auth.py set-password --dsn "dbname=mazimeal_dev" \
        --username maya --password maya123 \
        --user-id 11111111-1111-1111-1111-111111111111
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import os

ALGO = "pbkdf2_sha256"
ITERATIONS = 240_000


def hash_password(password: str, *, iterations: int = ITERATIONS,
                  salt: bytes | None = None) -> str:
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{ALGO}${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != ALGO:
            return False
        iterations = int(iters)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(dk, expected)  # constant-time


# --------------------------------------------------------------------------
# CLI: set a user's username + password hash
# --------------------------------------------------------------------------
def _connect(dsn: str):
    try:
        import psycopg
        return psycopg.connect(dsn)
    except ImportError:
        pass
    import psycopg2
    return psycopg2.connect(dsn)


def _q(conn, sql: str) -> str:
    module = type(conn).__module__.split(".")[0]
    return sql if module == "sqlite3" else sql.replace("?", "%s")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("set-password", help="set/reset a user's login")
    sp.add_argument("--dsn", default="dbname=mazimeal")
    sp.add_argument("--user-id", required=True)
    sp.add_argument("--username", required=True)
    sp.add_argument("--password", required=True)
    args = ap.parse_args(argv)

    digest = hash_password(args.password)
    conn = _connect(args.dsn)
    try:
        cur = conn.cursor()
        cur.execute(
            _q(conn, "UPDATE user_profile SET username = ?, password_hash = ? "
                     "WHERE user_id = ?"),
            (args.username, digest, args.user_id),
        )
        if cur.rowcount == 0:
            print(f"no user_profile row with user_id={args.user_id}")
            return 1
        conn.commit()
        print(f"login set for user_id={args.user_id} username={args.username!r}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
