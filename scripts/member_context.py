#!/usr/bin/env python3
"""Load an EvaluationContext for a household member, for an AUTHORIZED caller only.

Schemas read (migration 001): households(created_by_user_id), household_members(activity_level,
life_stage, goal), member_conditions(condition_type, condition_code, value_text). Every row of
member_conditions is PHI.

Authorization
-------------
A member may be read only by the account that owns their household:
households.created_by_user_id must equal the caller's verified user id. This is checked here,
in the query, because the API connects as a database owner and row-level security does not
protect that connection. 'No such member' and 'not your member' are the same error, so a
caller cannot learn which member ids exist.

The caller's id must come from the verified token (api/app/auth.py), never from the request
body. scripts/api.py identifies people by a bare ?user_id= and has no verified identity, so it
must not use this function.

What 'not recorded' means
-------------------------
A member with no condition rows gets conditions=None (unknown), NOT (). The database cannot
tell 'has no conditions' from 'was never asked', and the engine must not assume absence. A
caller who knows better can supply the context directly, with an explicit empty tuple.

user_profile (the legacy single-user table) is deliberately not read: it has no conditions,
and the only path to it is the unauthenticated ?user_id= query.
"""
from __future__ import annotations

from detect_rules import _q
from evaluation_context import EvaluationContext, MealContext, normalize_token


class MemberAccessDenied(PermissionError):
    """The member does not exist or does not belong to the caller. Deliberately the same."""

    def __init__(self):
        super().__init__("member not found")


def _invalid_id(exc: Exception) -> bool:
    sqlstate = getattr(exc, "sqlstate", None) or getattr(getattr(exc, "diag", None), "sqlstate", None)
    return sqlstate in {"22P02", "22023"} or "invalid input syntax for type uuid" in str(exc).lower()


def _tokens(rows) -> tuple[str, ...] | None:
    """Normalised tokens from (condition_code, value_text) rows; None when there are no rows."""
    if not rows:
        return None
    out: list[str] = []
    for code, text in rows:
        for part in (code, text):
            if part and normalize_token(part) not in out:
                out.append(normalize_token(part))
    return tuple(out)


def load_member_context(conn, member_id, caller_user_id,
                        meal_context: MealContext | None = None) -> EvaluationContext:
    """The member's context, or MemberAccessDenied. Never logs or prints what it reads."""
    if not member_id or not caller_user_id:
        raise MemberAccessDenied()
    cur = conn.cursor()
    try:
        cur.execute(_q(conn, """
            SELECT m.member_id, m.activity_level, m.life_stage, m.goal
            FROM household_members m
            JOIN households h ON h.household_id = m.household_id
            WHERE m.member_id = ?
              AND h.created_by_user_id = ?
              AND m.deleted_at IS NULL
              AND h.deleted_at IS NULL
        """), (str(member_id), str(caller_user_id)))
        row = cur.fetchone()
    except Exception as exc:
        if _invalid_id(exc):
            if hasattr(conn, "rollback"):
                conn.rollback()
            raise MemberAccessDenied() from None
        raise
    if row is None:
        raise MemberAccessDenied()
    member, activity, life_stage, goal = row

    cur = conn.cursor()
    cur.execute(_q(conn, """
        SELECT condition_type, condition_code, value_text
        FROM member_conditions
        WHERE member_id = ?
          AND condition_type IN ('condition', 'medication', 'supplement')
        ORDER BY condition_type, created_at, record_id
    """), (str(member),))
    by_type: dict[str, list] = {}
    for ctype, code, text in cur.fetchall():
        by_type.setdefault(ctype, []).append((code, text))

    return EvaluationContext(
        member_id=str(member),
        conditions=_tokens(by_type.get("condition")),
        medications=_tokens(by_type.get("medication")),
        supplements=_tokens(by_type.get("supplement")),
        goals=(goal,) if goal else None,
        activity_level=activity,
        life_stage=life_stage,
        meal_context=meal_context,
    )
