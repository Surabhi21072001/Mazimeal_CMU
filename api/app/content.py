"""
Reviewed suggestion text.

Two stores sit behind the suggestions endpoint and they are not the same thing:

    cache    speed only. Anything in it can be thrown away and regenerated.
    content  the reviewed text. A person approved these words, so they win
             over anything a model would write now.

The split exists because the words are a property of the recipe, not of the
person reading them: the rules matched the recipe, and the rules supply the
facts. What changes per member - how much iron they still need, which recipe
ranks first - is computed, never written by a model. That is what makes
pre-generating and reviewing possible at all.

A file per recipe, so a reviewer can read a diff and the whole store can go in
version control later.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

CONTENT_DIR = Path(
    os.environ.get("MAZI_CONTENT_DIR", Path(__file__).resolve().parent.parent / "content")
)

PENDING = "pending_review"
APPROVED = "approved"
REJECTED = "rejected"


def _path(recipe_id: str) -> Path:
    return CONTENT_DIR / f"{recipe_id}.json"


def get(recipe_id: str) -> dict | None:
    path = _path(recipe_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def approved(recipe_id: str) -> dict | None:
    entry = get(recipe_id)
    return entry if entry and entry.get("status") == APPROVED else None


def put(recipe_id: str, suggestions: list[dict], model: str | None, status: str = PENDING, summary: dict | None = None) -> dict:
    entry = {
        "recipe_id": recipe_id,
        "status": status,
        "model": model,
        "summary": summary,
        "generated_at": time.time(),
        "reviewed_by": None,
        "reviewed_at": None,
        "suggestions": suggestions,
    }
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    _path(recipe_id).write_text(json.dumps(entry, indent=2) + "\n")
    return entry


def review(recipe_id: str, status: str, reviewer: str) -> dict | None:
    entry = get(recipe_id)
    if not entry:
        return None
    entry["status"] = status
    entry["reviewed_by"] = reviewer
    entry["reviewed_at"] = time.time()
    _path(recipe_id).write_text(json.dumps(entry, indent=2) + "\n")
    return entry


def queue(status: str = PENDING) -> list[dict]:
    """What a reviewer still has to look at."""
    if not CONTENT_DIR.exists():
        return []
    out = []
    for path in sorted(CONTENT_DIR.glob("*.json")):
        try:
            entry = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if status in (None, "all") or entry.get("status") == status:
            out.append(entry)
    return out
