"""Is this recipe's nutrition plausible?

A different question from the one the review screen already asks. That one is
about the suggestion text; this one is about the numbers, and it exists because
the numbers are the part nobody has checked. Food.com publishes six of the
eleven nutrients the cook screen shows; the other five - iron, calcium, zinc,
folate, vitamin C, the ones the rules are actually about - are computed from
ingredient weights that are a guessed pairing times a guessed measure, and
there is no published figure to catch an error in them.

Energy is the one nutrient with both, so its ratio is the only measurement of
that chain available. This module serves that ratio for every seed recipe with
the per-line counts behind it, and records what a person decided.

The snapshot is taken here, not sent by the client. A verdict is only readable
later if we know what the reviewer was looking at, and a client-supplied
"ratio I was shown" is a number the client chose.
"""
from __future__ import annotations

import json

from fastapi import HTTPException

from . import seed_list
from .supabase_repo import _connect, _resolve

VERDICTS = ("plausible", "implausible", "needs_data")

# Computed energy per serving against the published figure, per recipe, with
# the counts that explain a disagreement. One query for all fifty: the cook
# screen's per-recipe provenance would be fifty round trips.
_FACTS_SQL = """
WITH scope AS (
    SELECT r.recipe_id, r.external_source_id, r.recipe_name, r.meal_category, r.servings
      FROM recipes r
     WHERE r.external_source_id = ANY(%(ids)s) AND r.deleted_at IS NULL
),
published AS (
    SELECT recipe_id, per_serving FROM recipe_nutrition WHERE nutrient_id = 'Energy'
),
derived AS (
    SELECT ri.recipe_id, sum(v.value_per_100g * ri.quantity_g / 100.0) AS kcal
      FROM recipe_ingredients ri
      JOIN v_ingredient_nutrition v
        ON v.ingredient_id = ri.ingredient_id AND v.nutrient_id = 'Energy'
     WHERE ri.quantity_g IS NOT NULL
     GROUP BY 1
),
lines AS (
    SELECT ri.recipe_id,
           count(*) AS lines,
           count(*) FILTER (WHERE coalesce(ri.quantity_aligned, FALSE) IS FALSE) AS misaligned,
           count(*) FILTER (WHERE ri.grams_source <> 'measure') AS guessed_grams,
           count(*) FILTER (WHERE ri.quantity_g IS NULL) AS no_grams,
           count(*) FILTER (WHERE NOT EXISTS (
               SELECT 1 FROM v_ingredient_nutrition v
                WHERE v.ingredient_id = ri.ingredient_id)) AS no_nutrition
      FROM recipe_ingredients ri
     GROUP BY 1
),
latest AS (
    SELECT DISTINCT ON (recipe_id)
           recipe_id, verdict, reason, reviewer, reviewed_at, energy_ratio
      FROM recipe_nutrition_reviews
     ORDER BY recipe_id, reviewed_at DESC
)
SELECT s.recipe_id, s.external_source_id, s.recipe_name, s.meal_category, s.servings,
       round(p.per_serving::numeric, 1) AS energy_published,
       round((d.kcal / nullif(s.servings, 0))::numeric, 1) AS energy_derived,
       round((d.kcal / nullif(s.servings, 0) / nullif(p.per_serving, 0))::numeric, 3) AS energy_ratio,
       coalesce(l.lines, 0), coalesce(l.misaligned, 0), coalesce(l.guessed_grams, 0),
       coalesce(l.no_grams, 0), coalesce(l.no_nutrition, 0),
       v.verdict, v.reason, v.reviewer, v.reviewed_at, v.energy_ratio AS reviewed_ratio,
       (SELECT count(*) FROM recipe_nutrition_reviews rr WHERE rr.recipe_id = s.recipe_id)
  FROM scope s
  LEFT JOIN published p USING (recipe_id)
  LEFT JOIN derived   d USING (recipe_id)
  LEFT JOIN lines     l USING (recipe_id)
  LEFT JOIN latest    v USING (recipe_id)
"""


def _facts_row(row) -> dict:
    (
        recipe_id, external_id, name, meal, servings,
        published, derived, ratio,
        lines, misaligned, guessed, no_grams, no_nutrition,
        verdict, reason, reviewer, reviewed_at, reviewed_ratio, review_count,
    ) = row
    ratio = float(ratio) if ratio is not None else None
    reviewed_ratio = float(reviewed_ratio) if reviewed_ratio is not None else None
    return {
        "recipe_id": str(recipe_id),
        "external_source_id": external_id,
        "name": name,
        "meal": meal,
        "servings": servings,
        "energy_published": float(published) if published is not None else None,
        "energy_derived": float(derived) if derived is not None else None,
        "energy_ratio": ratio,
        "lines": lines,
        "lines_misaligned": misaligned,
        "grams_guessed": guessed,
        "grams_missing": no_grams,
        "lines_without_nutrition": no_nutrition,
        "review": (
            {
                "verdict": verdict,
                "reason": reason,
                "reviewer": reviewer,
                "reviewed_at": reviewed_at.isoformat() if reviewed_at else None,
                "energy_ratio": reviewed_ratio,
                # A verdict taken against a ratio the data no longer has is
                # about an older version of it, and saying so is the whole
                # reason the ratio is stored with the verdict.
                "stale": (
                    reviewed_ratio is not None
                    and ratio is not None
                    and abs(reviewed_ratio - ratio) > 0.005
                ),
            }
            if verdict
            else None
        ),
        "review_count": review_count,
    }


def _facts(conn, recipe_ids: list[str]) -> list[dict]:
    cur = conn.execute(_FACTS_SQL, {"ids": recipe_ids})
    return [_facts_row(row) for row in cur]


def queue() -> dict:
    """Every seed recipe, worst disagreement first.

    Sorted by how far the two energy figures are apart rather than by name: the
    recipe whose computed calories are a tenth of its published ones is the one
    worth opening, and a list in spreadsheet order buries it.
    """
    rows = seed_list.seed_rows()
    if not rows:
        return {"items": [], "count": 0, "source": "supabase", "note": "seed list not found"}

    by_external = {row["external_source_id"]: row for row in rows}
    with _connect() as conn:
        facts = _facts(conn, list(by_external))

    for item in facts:
        spreadsheet = by_external.get(item["external_source_id"]) or {}
        item["cuisine"] = spreadsheet.get("cuisine")

    def distance(item):
        ratio = item["energy_ratio"]
        if ratio is None:
            return -1.0  # nothing to compare: last, not worst
        return abs(ratio - 1)

    facts.sort(key=distance, reverse=True)
    reviewed = sum(1 for item in facts if item["review"])
    return {
        "items": facts,
        "count": len(facts),
        "reviewed": reviewed,
        "unreviewed": len(facts) - reviewed,
        "source": "supabase",
    }


def record(recipe_id: str, verdict: str, reason: str | None, reviewer: str) -> dict:
    """Store one verdict, with the numbers as they stand right now."""
    if verdict not in VERDICTS:
        raise HTTPException(
            status_code=400, detail={"error": "bad_verdict", "allowed": list(VERDICTS)}
        )
    reason = (reason or "").strip() or None
    if verdict != "plausible" and not reason:
        raise HTTPException(status_code=400, detail={"error": "reason_required", "verdict": verdict})

    db_id = _resolve(recipe_id)
    if db_id is None:
        raise HTTPException(status_code=404, detail={"error": "no_such_recipe", "recipe_id": recipe_id})

    with _connect() as conn:
        rows = conn.execute(
            "SELECT external_source_id FROM recipes WHERE recipe_id = %s AND deleted_at IS NULL",
            (db_id,),
        ).fetchall()
        if not rows:
            raise HTTPException(
                status_code=404, detail={"error": "no_such_recipe", "recipe_id": recipe_id}
            )
        facts = _facts(conn, [rows[0][0]])
        snapshot = facts[0] if facts else {}
        flags = {
            key: snapshot.get(key)
            for key in (
                "energy_published",
                "energy_derived",
                "lines",
                "lines_misaligned",
                "grams_guessed",
                "grams_missing",
                "lines_without_nutrition",
            )
        }
        written = conn.execute(
            """INSERT INTO recipe_nutrition_reviews
                   (recipe_id, verdict, reason, energy_ratio, flags, reviewer)
               VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING review_id, reviewed_at""",
            (
                db_id,
                verdict,
                reason,
                snapshot.get("energy_ratio"),
                json.dumps(flags),
                reviewer,
            ),
        ).fetchone()
        conn.commit()

    return {
        "review_id": str(written[0]),
        "recipe_id": str(db_id),
        "verdict": verdict,
        "reason": reason,
        "reviewer": reviewer,
        "reviewed_at": written[1].isoformat(),
        "energy_ratio": snapshot.get("energy_ratio"),
    }


def history(recipe_id: str) -> list[dict]:
    db_id = _resolve(recipe_id)
    if db_id is None:
        return []
    with _connect() as conn:
        return [
            {
                "review_id": str(review_id),
                "verdict": verdict,
                "reason": reason,
                "reviewer": reviewer,
                "reviewed_at": reviewed_at.isoformat(),
                "energy_ratio": float(ratio) if ratio is not None else None,
            }
            for review_id, verdict, reason, reviewer, reviewed_at, ratio in conn.execute(
                """SELECT review_id, verdict, reason, reviewer, reviewed_at, energy_ratio
                     FROM recipe_nutrition_reviews WHERE recipe_id = %s
                    ORDER BY reviewed_at DESC LIMIT 50""",
                (db_id,),
            )
        ]
