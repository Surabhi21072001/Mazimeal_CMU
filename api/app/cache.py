"""
Suggestion cache.

A rewrite costs a couple of seconds per rule on the local model, and the text
for a given recipe does not change between visits. So the first view of a
recipe pays for the model and every later view is instant.

Two layers: a dict for this process, and a json file per key so a restart does
not throw the work away - which matters when the model takes seconds, not
milliseconds.

The key covers everything that would change the text: the recipe, the member,
the rules asked for, the provider, the model, and the prompt itself. Change the
prompt and old entries are simply never read again, so there is no stale text
to clear by hand.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

CACHE_DIR = Path(os.environ.get("MAZI_CACHE_DIR", Path(__file__).resolve().parent.parent / ".cache"))
ENABLED = os.environ.get("MAZI_CACHE", "1") != "0"

_memory: dict[str, dict] = {}


def key_for(recipe_id: str, rule_ids: list[str] | None, provider: str, model: str, prompt: str) -> str:
    # No member in the key: the words come from the rules, which belong to the
    # recipe. What differs per member is computed elsewhere and never cached.
    material = json.dumps(
        {
            "recipe": recipe_id,
            "rules": sorted(rule_ids or []),
            "provider": provider,
            "model": model,
            "prompt": hashlib.sha256(prompt.encode()).hexdigest()[:16],
        },
        sort_keys=True,
    )
    return hashlib.sha256(material.encode()).hexdigest()[:32]


def get(key: str) -> dict | None:
    if not ENABLED:
        return None
    if key in _memory:
        return _memory[key]
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        entry = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None  # a half-written file is not worth a 500
    _memory[key] = entry
    return entry


def put(key: str, payload: dict) -> None:
    if not ENABLED:
        return
    entry = {"created_at": time.time(), "payload": payload}
    _memory[key] = entry
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_DIR / f"{key}.json.tmp"
        tmp.write_text(json.dumps(entry))
        tmp.replace(CACHE_DIR / f"{key}.json")  # atomic, so no half-written reads
    except OSError:
        pass  # the memory layer still works; a read-only disk is not fatal


def clear() -> int:
    _memory.clear()
    if not CACHE_DIR.exists():
        return 0
    removed = 0
    for path in CACHE_DIR.glob("*.json"):
        path.unlink()
        removed += 1
    return removed
