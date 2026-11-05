"""The reviewer list, as data.

auth.py decides whether a caller may approve a rule change. It asks two
places: MAZI_ADMIN_EMAILS in the server's environment, and the app_admins
table this module reads and writes.

The two are not interchangeable, and the difference is the whole point. The
environment list cannot be changed by any request, so it is the way back in
when the table is wrong. The table can be changed from the screen, which is
what makes growing the reviewer list not require a deployment.

Three rules keep the table from being a way to lock everyone out:

  * You cannot revoke yourself. The mistake is easy, silent, and - if you were
    the last one - unrecoverable from the screen.
  * You cannot revoke the last remaining reviewer, even if it is not you.
  * An address in MAZI_ADMIN_EMAILS is not in this table and cannot be removed
    through it. The refusal says so rather than reporting "not found", because
    the two mean different things to whoever is looking at the list.

Reads are not cached. One indexed primary-key scan per authenticated request
is cheaper than reasoning about how long a revoked reviewer keeps approving.
"""
from __future__ import annotations

from fastapi import HTTPException

from .supabase_repo import _connect

COLUMNS = ("email", "granted_by", "granted_at", "note")


def _normalise(email: str) -> str:
    cleaned = (email or "").strip().lower()
    if not cleaned:
        raise HTTPException(status_code=400, detail={"error": "email_required"})
    # The same shape the table's CHECK enforces, refused here so the caller is
    # told what was wrong with it instead of reading a constraint name.
    if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@") or " " in cleaned:
        raise HTTPException(
            status_code=400, detail={"error": "bad_email", "email": cleaned}
        )
    local, _, domain = cleaned.partition("@")
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise HTTPException(
            status_code=400, detail={"error": "bad_email", "email": cleaned}
        )
    return cleaned


def granted_emails() -> set[str]:
    """Every address in the table. Called once per authenticated request.

    Returns an empty set rather than raising when the table is missing, so a
    deployment whose migrations have not run still honours MAZI_ADMIN_EMAILS
    and serves every unauthenticated endpoint.
    """
    try:
        with _connect() as conn:
            return {row[0] for row in conn.execute("SELECT email FROM app_admins").fetchall()}
    except Exception:
        return set()


def listing(env_emails: set[str]) -> dict:
    """The reviewer list as the screen shows it: both sources, labelled.

    env_emails is passed in rather than read here because auth.py owns what
    the environment says; this module owns the table.
    """
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT {', '.join(COLUMNS)} FROM app_admins ORDER BY granted_at"
        ).fetchall()

    granted = [
        {
            "email": email,
            "granted_by": granted_by,
            "granted_at": granted_at.isoformat() if granted_at else None,
            "note": note,
            "source": "table",
            "removable": True,
        }
        for email, granted_by, granted_at, note in rows
    ]
    in_table = {entry["email"] for entry in granted}
    from_env = [
        {
            "email": email,
            "granted_by": None,
            "granted_at": None,
            "note": "Set in the server's environment. Cannot be changed from this screen.",
            "source": "environment",
            "removable": False,
        }
        for email in sorted(env_emails)
        if email not in in_table
    ]
    people = from_env + granted
    return {
        "count": len(people),
        "items": people,
        "from_environment": len(from_env),
        "from_table": len(granted),
    }


def grant(email: str, by: str, note: str | None) -> dict:
    """Add a reviewer. Idempotent: granting an existing one updates the note."""
    address = _normalise(email)
    with _connect() as conn:
        row = conn.execute(
            """INSERT INTO app_admins (email, granted_by, note)
               VALUES (%s, %s, %s)
               ON CONFLICT (email) DO UPDATE
                   SET note = coalesce(excluded.note, app_admins.note)
            RETURNING email, granted_by, granted_at, note""",
            (address, by, (note or "").strip() or None),
        ).fetchone()
        conn.commit()
    return {
        "email": row[0],
        "granted_by": row[1],
        "granted_at": row[2].isoformat() if row[2] else None,
        "note": row[3],
        "source": "table",
    }


def revoke(email: str, by: str, env_emails: set[str]) -> dict:
    """Remove a reviewer, unless that would strand the list."""
    address = _normalise(email)
    if address == (by or "").strip().lower():
        raise HTTPException(
            status_code=400,
            detail={
                "error": "cannot_revoke_self",
                "hint": "ask another reviewer to remove you, so the list is never "
                        "emptied by one click",
            },
        )

    with _connect() as conn:
        # One statement, so two reviewers revoking each other at the same
        # moment cannot both pass the count check and leave nobody behind.
        row = conn.execute(
            """DELETE FROM app_admins
                WHERE email = %s
                  AND (SELECT count(*) FROM app_admins) > 1
            RETURNING email""",
            (address,),
        ).fetchone()
        if row is None:
            exists = conn.execute(
                "SELECT 1 FROM app_admins WHERE email = %s", (address,)
            ).fetchone()
            conn.rollback()
            if exists:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "last_reviewer",
                        "hint": "add another reviewer first; an empty list can only be "
                                "refilled from the database or MAZI_ADMIN_EMAILS",
                    },
                )
            if address in env_emails:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "set_in_environment",
                        "hint": "this address is in MAZI_ADMIN_EMAILS on the server, not "
                                "in the table, so it cannot be removed from here",
                    },
                )
            raise HTTPException(
                status_code=404, detail={"error": "not_a_reviewer", "email": address}
            )
        conn.commit()
    return {"email": address, "revoked_by": by}
