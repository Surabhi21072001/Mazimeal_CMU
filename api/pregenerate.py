#!/usr/bin/env python3
"""
Write the suggestion text for a sample of recipes, once, for a person to read.

    api/.venv/bin/python api/pregenerate.py                 # every fixture recipe
    api/.venv/bin/python api/pregenerate.py falafel-001     # just these

The model runs here, not while someone is looking at a page. What it writes
lands in api/content/<recipe_id>.json with status pending_review; the
suggestions endpoint only serves a file once a reviewer has approved it.

Set the provider the same way the server does:

    MAZI_PROVIDER=local MAZI_LLM_URL=http://127.0.0.1:8081/v1 \\
      MAZI_LLM_MODEL=mlx-community/gemma-3-4b-it-4bit \\
      api/.venv/bin/python api/pregenerate.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import config, content, providers  # noqa: E402
from app.repo import get_repo  # noqa: E402


def main(argv: list[str]) -> int:
    repo = get_repo()
    if argv:
        recipe_ids = argv
    else:
        recipe_ids = sorted(
            p.stem.removeprefix("recipe_") for p in config.FIXTURES_DIR.glob("recipe_*.json")
        )

    print(f"provider={config.PROVIDER} model={config.LLM_MODEL if config.PROVIDER == 'local' else '-'}")
    print(f"writing to {content.CONTENT_DIR}\n")

    for recipe_id in recipe_ids:
        recipe = repo.recipe(recipe_id)
        if not recipe:
            print(f"  {recipe_id:24} skipped, no such recipe")
            continue

        started = time.perf_counter()
        suggestions, source, model, summary = providers.suggestions_for(recipe)
        took = round((time.perf_counter() - started) * 1000)

        if not suggestions:
            print(f"  {recipe_id:24} no matched rules, nothing to write")
            continue

        content.put(recipe_id, suggestions, model, summary=summary)
        note = "model" if source == "local" else "template only"
        print(f"  {recipe_id:24} {len(suggestions)} suggestions, {note}, {took} ms")

    pending = content.queue()
    print(f"\n{len(pending)} recipes waiting for review.")
    print("Approve one:  curl -X POST localhost:8002/api/content/<recipe_id>/review "
          "-H 'Content-Type: application/json' -d '{\"status\":\"approved\",\"reviewer\":\"kevin\"}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
