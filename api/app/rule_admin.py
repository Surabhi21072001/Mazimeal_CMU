"""The rules table, for the people who maintain it.

Three things live here: counting and listing business_rules, proposing a
change to one, and approving a proposal. The split matters - proposing is
open to any signed-in account, approving is not - but both end up in
rule_change_requests, and business_rules is only ever written by _apply()
below, inside the same transaction that records the decision.

What the counts are for
-----------------------
A rule does nothing until an ingredient carries its trigger_code, so "54
active rules" overstates the engine by a wide margin: on this database 44
distinct trigger codes are needed and 11 are tagged, which leaves most rules
unreachable on every recipe. The listing therefore reports, per rule, how many
ingredients carry its trigger code and how many recipes contain one. A rule
with zero is not broken - it is waiting on the tagging work - and the
difference is the single most useful thing an admin page can show.
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import HTTPException

from .rule_codes import validate_rule_codes
from .supabase_repo import _connect

# Columns a request may set. business_rules has 24; these are the ones that
# describe the rule rather than bookkeeping. rule_id is excluded because
# changing it would orphan every ingredient_rule_tags row pointing at the old
# trigger code, and created_at/updated_at are the database's to maintain.
EDITABLE = (
    "rule_name",
    "rule_category",
    "rule_type",
    "trigger_food_or_pattern",
    "trigger_code",
    "target_nutrient_or_outcome",
    "target_code",
    "action",
    "action_code",
    "mechanism",
    "recipe_engine_instruction",
    "conditions_and_limits",
    "population_scope",
    "evidence_tier",
    "evidence_summary",
    "automation_status",
    "source_title",
    "source_type",
    "source_url",
    "review_date",
    "is_active",
)

# Everything a reviewer needs to see, in a stable order.
RULE_COLUMNS = ("rule_id",) + EDITABLE + ("created_at", "updated_at")

# These three mirror check constraints on business_rules. Validating here as
# well is not duplication: a value caught at submission time tells the person
# writing the request which field is wrong, while the same value caught by the
# constraint surfaces at approval time, to a reviewer who cannot fix it.
AUTOMATION_STATUSES = ("recipe_safe", "conditional", "instruction_only", "do_not_automate")
EVIDENCE_TIERS = ("A", "B", "C")
RULE_CATEGORIES = ("bioavailability", "food_synergy", "inhibitor", "glycemic")


def _rows(cur):
    names = [c.name for c in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def _jsonable(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):  # date
        return value.isoformat()
    return value


def _rule_json(row: dict) -> dict:
    return {key: _jsonable(value) for key, value in row.items()}


# ---------------------------------------------------------------------- reading
def summary() -> dict:
    """How many rules there are, and how many of them the engine can reach."""
    with _connect() as conn:
        cur = conn.execute(
            """
            SELECT
              (SELECT count(*) FROM business_rules)                            AS rules,
              (SELECT count(*) FROM business_rules WHERE is_active)             AS active,
              (SELECT count(DISTINCT trigger_code) FROM business_rules
                WHERE is_active AND trigger_code IS NOT NULL)                  AS trigger_codes,
              (SELECT count(DISTINCT rule_code) FROM ingredient_rule_tags)      AS tagged_codes,
              (SELECT count(*) FROM ingredient_rule_tags)                       AS tags,
              (SELECT count(DISTINCT ingredient_id) FROM ingredient_rule_tags)  AS tagged_ingredients,
              (SELECT count(*) FROM ingredients)                                AS ingredients,
              (SELECT count(*) FROM business_rules br WHERE br.is_active
                 AND EXISTS (SELECT 1 FROM ingredient_rule_tags t
                              WHERE t.rule_code = br.trigger_code))            AS reachable,
              (SELECT count(*) FROM rule_change_requests WHERE status = 'pending') AS pending
            """
        )
        totals = _rows(cur)[0]
        by_category = _rows(
            conn.execute(
                """SELECT rule_category AS name, count(*) AS rules,
                          count(*) FILTER (WHERE is_active) AS active
                     FROM business_rules GROUP BY 1 ORDER BY 2 DESC"""
            )
        )
        by_status = _rows(
            conn.execute(
                """SELECT coalesce(automation_status, '(unset)') AS name, count(*) AS rules
                     FROM business_rules WHERE is_active GROUP BY 1 ORDER BY 2 DESC"""
            )
        )
    totals["unreachable"] = totals["active"] - totals["reachable"]
    return {"totals": totals, "by_category": by_category, "by_automation_status": by_status}


def rules(
    query: str | None = None,
    category: str | None = None,
    status: str | None = None,
    reach: str | None = None,
    active: bool | None = None,
    limit: int = 200,
) -> list[dict]:
    """business_rules, filtered, each row carrying what the engine can do with it.

    `reach` is "reachable" or "unreachable": whether any ingredient in this
    database carries the rule's trigger code. It is the filter an admin wants
    first and cannot get from the rule row alone.
    """
    where = ["TRUE"]
    args: list = []
    if query:
        where.append(
            "(br.rule_id ILIKE %s OR br.rule_name ILIKE %s OR br.trigger_code ILIKE %s"
            " OR br.rule_category ILIKE %s)"
        )
        args += [f"%{query}%"] * 4
    if category:
        where.append("br.rule_category = %s")
        args.append(category)
    if status:
        where.append("br.automation_status = %s")
        args.append(status)
    if active is not None:
        where.append("br.is_active = %s")
        args.append(active)
    if reach == "reachable":
        where.append("t.ingredients > 0")
    elif reach == "unreachable":
        where.append("coalesce(t.ingredients, 0) = 0")

    sql = f"""
        SELECT br.rule_id, br.rule_name, br.rule_category, br.rule_type,
               br.trigger_code, br.target_code, br.action_code,
               br.automation_status, br.evidence_tier, br.is_active,
               br.source_title, br.source_url, br.review_date, br.updated_at,
               coalesce(t.ingredients, 0) AS tagged_ingredients,
               coalesce(t.recipes, 0)     AS recipes_with_trigger,
               (SELECT count(*) FROM rule_change_requests r
                 WHERE r.rule_id = br.rule_id AND r.status = 'pending') AS pending_requests
          FROM business_rules br
          LEFT JOIN (
               SELECT tg.rule_code,
                      count(DISTINCT tg.ingredient_id) AS ingredients,
                      count(DISTINCT ri.recipe_id)     AS recipes
                 FROM ingredient_rule_tags tg
                 LEFT JOIN recipe_ingredients ri USING (ingredient_id)
                GROUP BY 1
          ) t ON t.rule_code = br.trigger_code
         WHERE {' AND '.join(where)}
         ORDER BY br.is_active DESC, coalesce(t.ingredients, 0) DESC, br.rule_id
         LIMIT %s
    """
    args.append(max(1, min(limit, 1000)))
    with _connect() as conn:
        return [_rule_json(r) for r in _rows(conn.execute(sql, args))]


def rule(rule_id: str) -> dict | None:
    """One rule in full, plus which ingredients actually carry its trigger."""
    with _connect() as conn:
        rows = _rows(
            conn.execute(
                f"SELECT {', '.join(RULE_COLUMNS)} FROM business_rules WHERE rule_id = %s",
                (rule_id,),
            )
        )
        if not rows:
            return None
        row = rows[0]
        ingredients = _rows(
            conn.execute(
                """SELECT i.ingredient_name AS name,
                          (SELECT count(*) FROM recipe_ingredients ri
                            WHERE ri.ingredient_id = i.ingredient_id) AS recipes
                     FROM ingredient_rule_tags t
                     JOIN ingredients i USING (ingredient_id)
                    WHERE t.rule_code = %s
                    ORDER BY 2 DESC, 1""",
                (row["trigger_code"],),
            )
        )
        history = _rows(
            conn.execute(
                """SELECT request_id, kind, status, submitted_by, submitted_at,
                          decided_by, decided_at, note, decision_note, applied_at
                     FROM rule_change_requests WHERE rule_id = %s
                    ORDER BY submitted_at DESC LIMIT 25""",
                (rule_id,),
            )
        )
    return {
        "rule": _rule_json(row),
        "tagged_ingredients": ingredients,
        "history": [_rule_json(h) for h in history],
        "editable": list(EDITABLE),
    }


def categories() -> list[str]:
    """The categories a rule may have - the constraint's list, not the table's.

    DISTINCT over business_rules would only ever offer categories already in
    use, which silently makes an empty category unaddable.
    """
    return list(RULE_CATEGORIES)


# --------------------------------------------------------------------- proposing
def _clean(proposed: dict) -> dict:
    """The subset of `proposed` that may be written, validated.

    Unknown keys are rejected rather than ignored: a typo in a field name
    would otherwise read as a successful change that did nothing.
    """
    unknown = sorted(set(proposed) - set(EDITABLE))
    if unknown:
        raise HTTPException(
            status_code=400,
            detail={"error": "not_editable", "fields": unknown, "editable": list(EDITABLE)},
        )
    out = {}
    for key, value in proposed.items():
        if isinstance(value, str):
            value = value.strip() or None
        out[key] = value
    status = out.get("automation_status")
    if status is not None and status not in AUTOMATION_STATUSES:
        raise HTTPException(
            status_code=400,
            detail={"error": "bad_automation_status", "allowed": list(AUTOMATION_STATUSES)},
        )
    tier = out.get("evidence_tier")
    if tier is not None and tier not in EVIDENCE_TIERS:
        raise HTTPException(
            status_code=400, detail={"error": "bad_evidence_tier", "allowed": list(EVIDENCE_TIERS)}
        )
    category = out.get("rule_category")
    if category is not None and category not in RULE_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail={"error": "bad_rule_category", "allowed": list(RULE_CATEGORIES)},
        )
    if "is_active" in out and not isinstance(out["is_active"], bool):
        raise HTTPException(status_code=400, detail={"error": "is_active_must_be_boolean"})
    return out


def submit(kind: str, rule_id: str, proposed: dict, note: str | None, by: str) -> dict:
    """Record a proposed change. Writes nothing to business_rules."""
    if kind not in ("create", "update", "activate", "deactivate"):
        raise HTTPException(status_code=400, detail={"error": "bad_kind", "kind": kind})
    rule_id = (rule_id or "").strip()
    if not rule_id:
        raise HTTPException(status_code=400, detail={"error": "rule_id_required"})

    fields = _clean(proposed or {})
    # business_rules has no foreign key on trigger_code, target_code or
    # action_code, so a mistyped one is stored and the rule is simply dead.
    # Refusing at submission is the only point where the person who made the
    # typo is still looking at it.
    validate_rule_codes(fields)
    if kind == "activate":
        fields["is_active"] = True
    elif kind == "deactivate":
        fields["is_active"] = False

    with _connect() as conn:
        current = _rows(
            conn.execute(
                f"SELECT {', '.join(RULE_COLUMNS)} FROM business_rules WHERE rule_id = %s",
                (rule_id,),
            )
        )
        if kind == "create":
            if current:
                raise HTTPException(
                    status_code=409, detail={"error": "rule_exists", "rule_id": rule_id}
                )
            missing = [f for f in ("rule_name", "rule_category") if not fields.get(f)]
            if missing:
                raise HTTPException(
                    status_code=400, detail={"error": "missing_fields", "fields": missing}
                )
            before = None
        else:
            if not current:
                raise HTTPException(
                    status_code=404, detail={"error": "no_such_rule", "rule_id": rule_id}
                )
            if not fields:
                raise HTTPException(status_code=400, detail={"error": "nothing_proposed"})
            before = _rule_json(current[0])

        rows = _rows(
            conn.execute(
                """INSERT INTO rule_change_requests (kind, rule_id, proposed, before, submitted_by, note)
                   VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING request_id, kind, rule_id, status, submitted_by, submitted_at""",
                (
                    kind,
                    rule_id,
                    json.dumps(fields, default=_jsonable),
                    json.dumps(before, default=_jsonable) if before is not None else None,
                    by,
                    (note or "").strip() or None,
                ),
            )
        )
        conn.commit()
    return _rule_json(rows[0])


def requests(status: str | None = "pending", limit: int = 100) -> list[dict]:
    sql = """SELECT request_id, kind, rule_id, proposed, before, submitted_by, submitted_at,
                    note, status, decided_by, decided_at, decision_note, applied_at,
                    (SELECT rule_name FROM business_rules br WHERE br.rule_id = r.rule_id) AS current_name
               FROM rule_change_requests r"""
    args: list = []
    if status and status != "all":
        sql += " WHERE status = %s"
        args.append(status)
    sql += " ORDER BY submitted_at DESC LIMIT %s"
    args.append(max(1, min(limit, 500)))
    with _connect() as conn:
        return [_rule_json(r) for r in _rows(conn.execute(sql, args))]


# --------------------------------------------------------------------- deciding
def _apply(conn, request: dict) -> None:
    """Write the request into business_rules. Caller holds the transaction.

    Column names come from EDITABLE, never from the request, so the JSONB
    cannot name a column - the keys were checked against EDITABLE when the
    request was submitted, and are checked again here because a row could have
    been written by an older version of that check.
    """
    fields = _clean(request["proposed"] or {})
    if request["kind"] == "create":
        columns = ["rule_id"] + list(fields)
        values = [request["rule_id"]] + [fields[k] for k in fields]
        placeholders = ", ".join(["%s"] * len(columns))
        conn.execute(
            f"INSERT INTO business_rules ({', '.join(columns)}) VALUES ({placeholders})",
            values,
        )
        return

    assignments = ", ".join(f"{key} = %s" for key in fields)
    conn.execute(
        f"UPDATE business_rules SET {assignments}, updated_at = now() WHERE rule_id = %s",
        [fields[key] for key in fields] + [request["rule_id"]],
    )


def decide(request_id: str, approve: bool, by: str, note: str | None) -> dict:
    """Approve and apply, or reject. One transaction either way.

    An approval re-reads the rule and compares it with the snapshot taken when
    the request was made. If they differ, the reviewer was shown text that is
    no longer in the database, so the request is marked stale and nothing is
    written - deciding on stale text is how two reviewers silently undo each
    other.
    """
    with _connect() as conn:
        rows = _rows(
            conn.execute(
                """SELECT request_id, kind, rule_id, proposed, before, status
                     FROM rule_change_requests WHERE request_id = %s FOR UPDATE""",
                (request_id,),
            )
        )
        if not rows:
            raise HTTPException(status_code=404, detail={"error": "no_such_request"})
        request = rows[0]
        if request["status"] != "pending":
            raise HTTPException(
                status_code=409,
                detail={"error": "already_decided", "status": request["status"]},
            )

        if not approve:
            conn.execute(
                """UPDATE rule_change_requests
                      SET status = 'rejected', decided_by = %s, decided_at = now(),
                          decision_note = %s
                    WHERE request_id = %s""",
                (by, (note or "").strip() or None, request_id),
            )
            conn.commit()
            return {"request_id": str(request_id), "status": "rejected", "applied": False}

        if request["kind"] != "create":
            current = _rows(
                conn.execute(
                    f"SELECT {', '.join(RULE_COLUMNS)} FROM business_rules"
                    " WHERE rule_id = %s FOR UPDATE",
                    (request["rule_id"],),
                )
            )
            if not current:
                raise HTTPException(
                    status_code=404,
                    detail={"error": "rule_disappeared", "rule_id": request["rule_id"]},
                )
            if _rule_json(current[0]) != request["before"]:
                conn.execute(
                    """UPDATE rule_change_requests
                          SET status = 'stale', decided_by = %s, decided_at = now(),
                              decision_note = %s
                        WHERE request_id = %s""",
                    (
                        by,
                        "The rule changed after this request was made; resubmit against the"
                        " current text.",
                        request_id,
                    ),
                )
                conn.commit()
                raise HTTPException(
                    status_code=409,
                    detail={"error": "rule_changed_since_request", "rule_id": request["rule_id"]},
                )

        try:
            _apply(conn, request)
        except Exception as exc:
            # A check constraint on business_rules rejecting the write is a
            # fact about the request, not a server fault, so it reads as 400
            # with the constraint's own message rather than a 500.
            conn.rollback()
            if type(exc).__module__.startswith("psycopg"):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "database_refused_the_change",
                        "constraint": getattr(getattr(exc, "diag", None), "constraint_name", None),
                        "message": str(exc).strip().splitlines()[0],
                    },
                ) from None
            raise
        conn.execute(
            """UPDATE rule_change_requests
                  SET status = 'approved', decided_by = %s, decided_at = now(),
                      decision_note = %s, applied_at = now()
                WHERE request_id = %s""",
            (by, (note or "").strip() or None, request_id),
        )
        conn.commit()
    return {"request_id": str(request_id), "status": "approved", "applied": True}
