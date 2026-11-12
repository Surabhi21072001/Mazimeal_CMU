"""Reviewed suggestion text, kept as versions in Postgres.

This used to live in the reviewer's browser. A correction is a statement about
the recipe, not about the machine it was typed on, so it belongs in the
database: a second reviewer picks up where the first left off, the cook screen
shows the corrected text to everyone, and clearing site data loses nothing.

Three rules the shape of this enforces, all of them deliberate:

  Version 1 is always the model's own output, and it is written HERE from the
  same pipeline the suggestions endpoint uses - never from the request body.
  It is the baseline every diff is read against, so a browser must not be able
  to decide what the model "originally" said.

  Every decision appends a version, including one that changed nothing. The
  number this screen exists to produce is how often the model was left alone,
  and that is only countable if agreement writes a row too.

  reviewer comes from the verified token. Who decided is the whole value of
  the record.

Removing a rule here means "this rule does not apply to this recipe". It never
touches business_rules, which the research workstream owns.
"""
from __future__ import annotations

import json

from fastapi import HTTPException
from psycopg.errors import UniqueViolation

from .supabase_repo import _connect, _resolve

CONFIRMED = "confirmed_unchanged"
EDITED = "edited"
REJECTED = "rejected"
REVERTED = "reverted_to_original"
OUTCOMES = (CONFIRMED, EDITED, REJECTED, REVERTED)

_COLUMNS = """
    version, parent, author, inputs_fingerprint, suggestions, summary,
    rules_removed, status_overrides, position_overrides, headline_rule_id,
    not_optimizable, outcome, tags, note, reviewer, created_at
"""


def _version(row) -> dict:
    (
        version, parent, author, fingerprint, suggestions, summary,
        rules_removed, status_overrides, position_overrides, headline_rule_id,
        not_optimizable, outcome, tags, note, reviewer, created_at,
    ) = row
    return {
        "version": version,
        "parent": parent,
        "author": author,
        "inputs_fingerprint": fingerprint,
        "suggestions": suggestions or [],
        "summary": summary,
        "rules_removed": rules_removed or [],
        "status_overrides": status_overrides or {},
        "position_overrides": position_overrides or {},
        "headline_rule_id": headline_rule_id,
        "not_optimizable": bool(not_optimizable),
        "created_at": created_at.isoformat(),
        # Kept nested, the shape the screen already reads: a version with no
        # review is the model's, and the screens branch on exactly that.
        "review": (
            {
                "outcome": outcome,
                "tags": tags or [],
                "note": note or "",
                "reviewer": reviewer,
                "reviewed_at": created_at.isoformat(),
            }
            if outcome
            else None
        ),
    }


def fingerprint(recipe: dict, payload: dict) -> str:
    """What produced this text: recipe, the rules that matched, and the model.

    Computed here rather than sent by the screen, so a version always records
    the inputs the server actually had. A stored fingerprint that no longer
    matches means the version was written against a different set of rules -
    which, now that rules change from the admin screen, is the difference
    between a current edit and one about an older recipe.
    """
    rule_ids = sorted(
        str(rule.get("rule_id")) for rule in (recipe.get("matched_rules") or []) if rule.get("rule_id")
    )
    model = payload.get("model") or payload.get("source") or "unknown"
    return f"{recipe.get('recipe_id')}|{','.join(rule_ids)}|{model}"


def _db_id(recipe_id: str) -> str:
    db_id = _resolve(recipe_id)
    if db_id is None:
        raise HTTPException(
            status_code=404, detail={"error": "no_such_recipe", "recipe_id": recipe_id}
        )
    return db_id


def _versions(conn, db_id: str) -> list[dict]:
    cur = conn.execute(
        f"SELECT {_COLUMNS} FROM recipe_content_versions WHERE recipe_id = %s ORDER BY version",
        (db_id,),
    )
    return [_version(row) for row in cur]


def _record(versions: list[dict], recipe_id: str, db_id: str) -> dict | None:
    if not versions:
        return None
    return {
        "recipe_id": recipe_id,
        "db_recipe_id": db_id,
        "current_version": versions[-1]["version"],
        "versions": versions,
    }


def get(recipe_id: str) -> dict | None:
    """Every version of one recipe, oldest first, or None if never reviewed."""
    db_id = _db_id(recipe_id)
    with _connect() as conn:
        return _record(_versions(conn, db_id), recipe_id, db_id)


def current(recipe_id: str) -> dict | None:
    """The version a cook should see, or None.

    Open to anyone, because the reviewed text is what a cook is meant to read.
    What is closed is writing it.

    Two cases return None, and both matter:

      Only version 1 exists. That is the model's own output, written the moment
      a reviewer opened the recipe. Serving it would label unreviewed text
      "reviewed" on the cook screen - the one claim this whole table exists to
      make truthfully - so an unreviewed recipe reads as unreviewed.

      The newest decision is "rejected". The review screen says in so many
      words that nothing is published for that recipe, so nothing is: the cook
      screen falls back to whatever the model writes now. An earlier approved
      version is not resurrected, because the reviewer's last word on this text
      was that it should not go out.
    """
    db_id = _resolve(recipe_id)
    if db_id is None:
        return None
    with _connect() as conn:
        rows = conn.execute(
            f"""SELECT {_COLUMNS} FROM recipe_content_versions
                 WHERE recipe_id = %s AND outcome IS NOT NULL
                 ORDER BY version DESC LIMIT 1""",
            (db_id,),
        ).fetchall()
    if not rows:
        return None
    version = _version(rows[0])
    return None if version["review"]["outcome"] == REJECTED else version


def seed(recipe: dict, payload: dict) -> dict:
    """Write version 1 from the model's output if this recipe has none yet.

    The payload is the one the server itself just produced, so "what the model
    said" is a server fact. Returns the whole record either way; an existing
    version 1 is never overwritten, because a later run of a different model
    would silently rewrite the baseline every diff is measured against.
    """
    recipe_id = recipe["recipe_id"]
    db_id = _db_id(recipe_id)
    # A payload with no model named came from the template provider, which
    # writes from the rule's own text. Falling back to `source` instead would
    # record authors like "model:cache", which names where the text was found
    # rather than what wrote it.
    model = payload.get("model") or "template"
    author = f"model:{str(model).split('/')[-1]}"

    with _connect() as conn:
        existing = _versions(conn, db_id)
        if existing:
            return _record(existing, recipe_id, db_id)
        try:
            conn.execute(
                """INSERT INTO recipe_content_versions
                       (recipe_id, version, parent, author, inputs_fingerprint,
                        suggestions, summary)
                   VALUES (%s, 1, NULL, %s, %s, %s, %s)""",
                (
                    db_id,
                    author,
                    fingerprint(recipe, payload),
                    json.dumps(payload.get("suggestions") or []),
                    json.dumps(payload.get("summary")) if payload.get("summary") else None,
                ),
            )
            conn.commit()
        except UniqueViolation:
            # Two reviewers opened the same recipe at once; one of them wrote
            # version 1 first. Theirs is as good as ours.
            conn.rollback()
        return _record(_versions(conn, db_id), recipe_id, db_id)


def add_version(recipe_id: str, body: dict, reviewer: str) -> dict:
    """Append one reviewer decision.

    Fields the body leaves out are inherited from the current version rather
    than reset, so a reviewer who changes one tip does not silently drop
    another reviewer's rule removal.
    """
    outcome = body.get("outcome")
    if outcome not in OUTCOMES:
        raise HTTPException(
            status_code=400, detail={"error": "bad_outcome", "allowed": list(OUTCOMES)}
        )
    if not reviewer:
        raise HTTPException(status_code=400, detail={"error": "no_reviewer_on_token"})

    db_id = _db_id(recipe_id)

    with _connect() as conn:
        existing = _versions(conn, db_id)
        if not existing:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "nothing_to_review",
                    "hint": "GET this recipe's review record first; that writes version 1 "
                            "from the model's output.",
                    "recipe_id": recipe_id,
                },
            )
        previous = existing[-1]

        def inherited(key, default):
            value = body.get(key)
            return previous.get(key, default) if value is None else value

        values = (
            db_id,
            previous["version"],
            f"human:{reviewer}",
            body.get("inputs_fingerprint") or previous.get("inputs_fingerprint"),
            json.dumps(inherited("suggestions", [])),
            json.dumps(inherited("summary", None)) if inherited("summary", None) is not None else None,
            json.dumps(inherited("rules_removed", [])),
            json.dumps(inherited("status_overrides", {})),
            json.dumps(inherited("position_overrides", {})),
            inherited("headline_rule_id", None),
            bool(inherited("not_optimizable", False)),
            outcome,
            json.dumps(body.get("tags") or []),
            (body.get("note") or "").strip() or None,
            reviewer,
        )

        # The version number is read and written in one statement, so the
        # unique constraint decides a tie instead of a lost update. A loser
        # retries against the row that won.
        insert = """
            INSERT INTO recipe_content_versions
                   (recipe_id, version, parent, author, inputs_fingerprint,
                    suggestions, summary, rules_removed, status_overrides,
                    position_overrides, headline_rule_id, not_optimizable,
                    outcome, tags, note, reviewer)
            SELECT %s,
                   coalesce(max(version), 0) + 1,
                   %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
              FROM recipe_content_versions WHERE recipe_id = %s
        """
        for attempt in (1, 2):
            try:
                conn.execute(insert, values + (db_id,))
                conn.commit()
                break
            except UniqueViolation:
                conn.rollback()
                if attempt == 2:
                    raise HTTPException(
                        status_code=409,
                        detail={"error": "concurrent_review", "recipe_id": recipe_id},
                    ) from None

        return _record(_versions(conn, db_id), recipe_id, db_id)


def stats() -> dict:
    """How often the model was left alone, across every recipe.

    A revert says something about an earlier edit, not about the model, so it
    is counted but kept out of the ratio.
    """
    with _connect() as conn:
        counts = dict(
            conn.execute(
                """SELECT outcome, count(*) FROM recipe_content_versions
                    WHERE outcome IS NOT NULL GROUP BY 1"""
            ).fetchall()
        )
        tag_counts = dict(
            conn.execute(
                """SELECT tag, count(*) FROM recipe_content_versions v,
                          jsonb_array_elements_text(v.tags) AS tag
                    WHERE v.outcome IS NOT NULL GROUP BY 1 ORDER BY 2 DESC"""
            ).fetchall()
        )
        recipes, reviewed_recipes = conn.execute(
            """SELECT count(DISTINCT recipe_id),
                      count(DISTINCT recipe_id) FILTER (WHERE outcome IS NOT NULL)
                 FROM recipe_content_versions"""
        ).fetchone()

    confirmed = counts.get(CONFIRMED, 0)
    edited = counts.get(EDITED, 0)
    rejected = counts.get(REJECTED, 0)
    reverted = counts.get(REVERTED, 0)
    judged = confirmed + edited + rejected
    return {
        "reviewed": confirmed + edited + rejected + reverted,
        "confirmed": confirmed,
        "edited": edited,
        "rejected": rejected,
        "reverted": reverted,
        "tagCounts": tag_counts,
        "unchangedRate": round(100 * confirmed / judged) if judged else None,
        "recipes_seen": recipes,
        "recipes_reviewed": reviewed_recipes,
        "source": "supabase",
    }
