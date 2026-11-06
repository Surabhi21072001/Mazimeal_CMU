"""The code vocabulary, for the people filling in the rule form.

A rule names three codes and the form used to ask for all three as free text.
business_rules has no foreign key on any of them, so a typo does not fail -
it produces a rule that is stored, looks finished, and can never fire,
because no ingredient carries a code that does not exist. That is the worst
kind of mistake to make quietly, and it is what this module exists to stop.

Two things are served here.

  codes()     the vocabulary, with what each code reaches: how many
              ingredients carry it and how many rules already use it. A
              person choosing a trigger needs the reach more than the name -
              "ING_CRUCIFER, 11 ingredients, 3 rules" says this will fire,
              and "ING_SEAWEED, 0 ingredients" says it will not.

  next_rule_id()  the next free id for a category. The prefix is not a free
              choice: BIO is bioavailability, GLY glycemic, INH inhibitor,
              SYN food_synergy, and every existing rule follows it.

Creating a code is allowed, and deliberately not reviewed. A code with no
tagged ingredients does nothing at all - it fires on nothing, so it cannot
produce a wrong suggestion. The act with consequences is tagging ingredients
to it, which happens in scripts/tag_ingredients.py where the choice is
written down and reviewable. So the vocabulary can grow without a deployment,
and nothing fires until someone says which foods the new word means.
"""
from __future__ import annotations

import re

from fastapi import HTTPException

from .supabase_repo import _connect

# rule_id prefix per category, from every rule in the table: all 54 follow it.
CATEGORY_PREFIX = {
    "bioavailability": "BIO",
    "food_synergy": "SYN",
    "inhibitor": "INH",
    "glycemic": "GLY",
}

# Which code_type belongs in which column of business_rules, taken from the
# types the 54 existing rules actually use. The form filters its candidate
# list by these, so an action code cannot be offered as a trigger.
FIELD_TYPES = {
    "trigger_code": ("ING", "NUT", "CMP", "MACRO", "CARB", "CALC", "BEV", "BEH", "MED", "PROC", "MEAL", "RULE"),
    "target_code": ("NUT", "CMP", "OUT"),
    "action_code": ("ADD", "PAIR", "SUB", "PROC", "SEP", "SEQ", "PORTION", "AVOID", "CHECK", "FLAG", "MITIGATE", "SAFETY", "BEH"),
}

CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+$")


def _rows(cursor) -> list[dict]:
    names = [c.name for c in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def codes(field: str | None = None, query: str | None = None) -> dict:
    """The vocabulary, with reach, newest-useful first.

    Ordered by whether the code reaches anything, because a list sorted
    alphabetically buries the codes that work among the ones that do not.
    """
    where, args = [], []
    if field:
        types = FIELD_TYPES.get(field)
        if not types:
            raise HTTPException(
                status_code=400,
                detail={"error": "bad_field", "field": field, "fields": sorted(FIELD_TYPES)},
            )
        where.append("rc.code_type = ANY(%s)")
        args.append(list(types))
    if query:
        where.append("(rc.code ILIKE %s OR rc.display_name ILIKE %s)")
        args += [f"%{query}%", f"%{query}%"]

    clause = f"WHERE {' AND '.join(where)}" if where else ""
    with _connect() as conn:
        items = _rows(
            conn.execute(
                f"""
                SELECT rc.code, rc.code_type, rc.display_name, rc.description,
                       rc.needs_review,
                       (SELECT count(*) FROM ingredient_rule_tags t
                         WHERE t.rule_code = rc.code) AS ingredients,
                       (SELECT count(*) FROM business_rules br
                         WHERE br.is_active AND br.trigger_code = rc.code) AS trigger_rules,
                       (SELECT count(*) FROM business_rules br
                         WHERE br.is_active AND br.target_code = rc.code) AS target_rules,
                       (SELECT count(*) FROM business_rules br
                         WHERE br.is_active AND br.action_code = rc.code) AS action_rules,
                       (SELECT array_agg(rcc.component_code ORDER BY rcc.component_code)
                          FROM rule_code_components rcc
                         WHERE rcc.composite_code = rc.code) AS components
                  FROM rule_codes rc
                  {clause}
                 ORDER BY (SELECT count(*) FROM ingredient_rule_tags t
                            WHERE t.rule_code = rc.code) DESC,
                          rc.code_type, rc.code
                """,
                args,
            )
        )

    for item in items:
        item["components"] = list(item["components"] or [])
        # A composite is satisfied by its components, so it is not tagged
        # itself and its own ingredient count is always zero. Saying "0
        # ingredients" about it would read as "this will never fire".
        item["reaches"] = bool(item["ingredients"]) or bool(item["components"])
    return {
        "count": len(items),
        "items": items,
        "field": field,
        "field_types": {k: list(v) for k, v in FIELD_TYPES.items()},
    }


def next_rule_id(category: str) -> dict:
    """The next free rule_id for a category, and what it was derived from."""
    prefix = CATEGORY_PREFIX.get((category or "").strip())
    if not prefix:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "bad_category",
                "category": category,
                "categories": sorted(CATEGORY_PREFIX),
            },
        )

    with _connect() as conn:
        used = {
            int(m.group(1))
            for (rule_id,) in conn.execute(
                "SELECT rule_id FROM business_rules WHERE rule_id LIKE %s", (f"{prefix}-%",)
            ).fetchall()
            if (m := re.match(rf"^{prefix}-(\d+)$", rule_id))
        }
        # A pending request has an id reserved but no row yet; offering it
        # again would collide at approval time, not at submission.
        pending = {
            int(m.group(1))
            for (rule_id,) in conn.execute(
                """SELECT rule_id FROM rule_change_requests
                    WHERE status = 'pending' AND kind = 'create' AND rule_id LIKE %s""",
                (f"{prefix}-%",),
            ).fetchall()
            if (m := re.match(rf"^{prefix}-(\d+)$", rule_id))
        }

    taken = used | pending
    nxt = 1
    while nxt in taken:
        nxt += 1
    return {
        "rule_id": f"{prefix}-{nxt:03d}",
        "prefix": prefix,
        "category": category,
        "existing": len(used),
        "pending": sorted(f"{prefix}-{n:03d}" for n in pending - used),
    }


def create_code(code: str, code_type: str, display_name: str, description: str | None, by: str) -> dict:
    """Add a word to the vocabulary.

    Not reviewed, because an untagged code has no effect: nothing carries it,
    so no rule naming it can fire. needs_review is set, which is how the
    existing imported codes are marked, so the ones added here are visible as
    unconfirmed rather than indistinguishable from the curated set.
    """
    code = (code or "").strip().upper()
    if not CODE_PATTERN.match(code):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "bad_code",
                "code": code,
                "hint": "Uppercase, a type prefix, then at least one underscore part: "
                        "ING_SEAWEED, NUT_IODINE.",
            },
        )

    code_type = (code_type or "").strip().upper() or code.split("_", 1)[0]
    prefix = code.split("_", 1)[0]
    if code_type != prefix:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "type_prefix_mismatch",
                "code": code,
                "code_type": code_type,
                "hint": f"{code} must have code_type {prefix}, because the prefix is what the "
                        "form filters candidates by.",
            },
        )

    name = (display_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail={"error": "display_name_required"})

    note = (description or "").strip() or None
    with _connect() as conn:
        existing = conn.execute(
            "SELECT code_type, display_name FROM rule_codes WHERE code = %s", (code,)
        ).fetchone()
        if existing:
            raise HTTPException(
                status_code=409,
                detail={"error": "code_exists", "code": code, "display_name": existing[1]},
            )
        conn.execute(
            """INSERT INTO rule_codes (code, code_type, display_name, description, needs_review)
               VALUES (%s, %s, %s, %s, TRUE)""",
            (code, code_type, name,
             note or f"Added from the admin screen by {by}. No ingredient carries it yet, "
                     f"so no rule naming it can fire until scripts/tag_ingredients.py "
                     f"says which foods it means."),
        )
        conn.commit()

    return {
        "code": code,
        "code_type": code_type,
        "display_name": name,
        "ingredients": 0,
        "reaches": False,
        "added_by": by,
    }


def validate_rule_codes(fields: dict) -> None:
    """Refuse a rule whose codes are not in the vocabulary.

    business_rules has no foreign key on these columns, so without this a
    mistyped trigger is accepted and the rule is simply dead. The error names
    the closest existing codes, because the mistake is nearly always a
    spelling.
    """
    named = {f: fields[f] for f in FIELD_TYPES if fields.get(f)}
    if not named:
        return

    with _connect() as conn:
        known = {
            row[0]
            for row in conn.execute(
                "SELECT code FROM rule_codes WHERE code = ANY(%s)", (list(named.values()),)
            ).fetchall()
        }
        for field, value in named.items():
            if value in known:
                continue
            stem = str(value).split("_", 1)[0]
            near = [
                row[0]
                for row in conn.execute(
                    """SELECT code FROM rule_codes
                        WHERE code LIKE %s ORDER BY code LIMIT 8""",
                    (f"{stem}%",),
                ).fetchall()
            ]
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "unknown_code",
                    "field": field,
                    "code": value,
                    "nearest": near,
                    "hint": "No ingredient can carry a code that does not exist, so a rule "
                            "naming one can never fire. Pick an existing code, or add the "
                            "new one first.",
                },
            )
