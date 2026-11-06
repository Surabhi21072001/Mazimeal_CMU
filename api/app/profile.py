"""The signed-in person's own profile.

The rules engine identifies a person with ?user_id=<uuid> in the query string,
which works but makes the identifier the credential: it never expires, and a
URL travels into access logs, Referer headers and browser history. That is
fine for the demo row and for their Postman collection, so it stays.

This is the path the app uses instead. The account comes from the verified
token and the profile is looked up from it, so nothing about who is asking is
in the request. The lookup is possible because migration 005 links
user_profile.auth_user_id to auth.users and sets user_profile.user_id to
household_members.member_id - one identifier across both systems.

A person may have no profile yet: signing up writes only the account, and the
profile appears when the onboarding questionnaire is finished. That is not an
error, and this reports it as a null profile rather than a 404, so the app can
tell "not signed up for a profile yet" apart from "something went wrong".
"""
from __future__ import annotations

from .supabase_repo import _connect

PROFILE_COLUMNS = (
    "user_id",
    "name",
    "age_years",
    "sex",
    "height_cm",
    "weight_kg",
    "activity_level",
    "goal",
    "diet_type",
    "allergies",
    "preferences",
    "username",
    "updated_at",
)


def _number(value):
    return float(value) if value is not None else None


def _profile_json(row: dict) -> dict:
    out = dict(row)
    out["user_id"] = str(out["user_id"])
    for key in ("height_cm", "weight_kg"):
        out[key] = _number(out.get(key))
    out["allergies"] = list(out.get("allergies") or [])
    out["preferences"] = list(out.get("preferences") or [])
    updated = out.get("updated_at")
    out["updated_at"] = updated.isoformat() if updated else None
    return out


def _rows(cursor) -> list[dict]:
    names = [c.name for c in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def me(auth_user_id: str) -> dict:
    """The caller's profile, their daily targets, and the rest of the household.

    One round trip per part rather than one join, because the targets and the
    members are both one-to-many and a single query would multiply the rows.
    """
    with _connect() as conn:
        found = _rows(
            conn.execute(
                f"""SELECT {', '.join(PROFILE_COLUMNS)}
                      FROM user_profile WHERE auth_user_id = %s""",
                (auth_user_id,),
            )
        )
        if not found:
            return {"profile": None, "targets": [], "household": [], "source": "no_profile_yet"}

        profile = _profile_json(found[0])

        targets = [
            {
                "nutrient_id": nutrient_id,
                "daily_target": _number(daily),
                "unit": unit,
                "minimum_target": _number(minimum),
                "upper_limit": _number(upper),
                "target_source": source,
            }
            for nutrient_id, daily, unit, minimum, upper, source in conn.execute(
                """SELECT nutrient_id, daily_target, unit, minimum_target,
                          upper_limit, target_source
                     FROM user_nutrient_targets
                    WHERE user_id = %s ORDER BY nutrient_id""",
                (profile["user_id"],),
            ).fetchall()
        ]

        # Everyone else in the household, so a screen can switch between them
        # without a second request. They have profiles and no accounts.
        household = [
            {
                "user_id": str(member_id),
                "name": name,
                "age_years": age,
                "sex": sex,
                "is_you": str(member_id) == profile["user_id"],
            }
            for member_id, name, age, sex in conn.execute(
                """SELECT up.user_id, up.name, up.age_years, up.sex
                     FROM user_profile up
                     JOIN household_members hm ON hm.member_id = up.user_id
                    WHERE hm.deleted_at IS NULL
                      AND hm.household_id = (
                            SELECT household_id FROM household_members
                             WHERE member_id = %s)
                    -- member_id breaks the tie: every member inserted by one
                    -- saveHousehold() call shares a created_at, because now()
                    -- is fixed for the whole transaction in Postgres. Without
                    -- it the list order changes between requests, and the
                    -- order is what tells a screen who the account holder is.
                    ORDER BY hm.created_at, hm.member_id""",
                (profile["user_id"],),
            ).fetchall()
        ]

    return {
        "profile": profile,
        "targets": targets,
        "household": household,
        "source": "account",
    }
