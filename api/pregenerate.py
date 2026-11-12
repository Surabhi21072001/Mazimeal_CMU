#!/usr/bin/env python3
"""
Write the suggestion text for a sample of recipes, once, ahead of review.

    api/.venv/bin/python api/pregenerate.py                 # every fixture recipe
    api/.venv/bin/python api/pregenerate.py falafel-001     # just these

The model runs here, not while someone is looking at a page. What it writes
becomes **version 1** of each recipe's review record in Postgres
(recipe_content_versions), which is the baseline a reviewer reads a diff
against. Version 1 is never served to a cook: the suggestions endpoint and the
cook screen both ask for the current *decision*, and a recipe with only a
baseline reads as unreviewed. So this is safe to run over everything.

It is also idempotent. A recipe that already has a version 1 keeps it, because
a later run of a different model must not silently rewrite the baseline every
diff is measured against. To compare models, use ?refresh=true on the
suggestions endpoint instead - that writes nothing.

Needs the database, and the same provider settings the server uses:

    set -a; . ./.env; set +a
    MAZI_REPO=supabase MAZIMEAL_DSN="$SUPABASE_DB_URL" \\
      MAZI_PROVIDER=local MAZI_LLM_URL=http://127.0.0.1:8081/v1 \\
      MAZI_LLM_MODEL=mlx-community/gemma-3-4b-it-4bit \\
      api/.venv/bin/python api/pregenerate.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import config, content_review, providers  # noqa: E402
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
    print(f"repo={repo.name}, writing version 1 into recipe_content_versions\n")

    written = kept = 0
    for recipe_id in recipe_ids:
        recipe = repo.recipe(recipe_id)
        if not recipe:
            print(f"  {recipe_id:24} skipped, no such recipe")
            continue

        # Asked before the model runs: a recipe that already has a baseline
        # needs no generation at all, which is the difference between a cheap
        # re-run and paying for every recipe again.
        if content_review.get(recipe_id):
            print(f"  {recipe_id:24} already has a version 1, left alone")
            kept += 1
            continue

        started = time.perf_counter()
        suggestions, source, model, summary = providers.suggestions_for(recipe)
        took = round((time.perf_counter() - started) * 1000)

        if not suggestions:
            print(f"  {recipe_id:24} no matched rules, nothing to write")
            continue

        payload = {"suggestions": suggestions, "summary": summary, "model": model, "source": source}
        record = content_review.seed(recipe, payload)
        note = "model" if source == "local" else "template only"
        print(f"  {recipe_id:24} {len(suggestions)} suggestions, {note}, {took} ms"
              f"  -> v{record['versions'][0]['version']} by {record['versions'][0]['author']}")
        written += 1

    print(f"\n{written} baselines written, {kept} already present.")
    print("Review them on #/review - signed in, and on the reviewer list.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
