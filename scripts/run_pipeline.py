"""Run the full pipeline (bio selector, synergy selector, Chef) on recipes we have already seen.

Run from the project root: python -m scripts.run_pipeline <count> [seed]
   or: python -m scripts.run_pipeline --recipes "Recipe title" "Another title"   (named, seen recipes only)
Recipes are drawn only from the ones in the earlier bio stage runs (SEEN_SEEDS). The recipes on the
nutritionist's sheet are held out for the final score and are never run here.
Writes outputs/pipeline_run_seed_<seed>.md (to read) and .json (for the scorer).
Groq limit is 8K tokens/min, so the script pauses between recipes.
"""
import json
import random
import sys
import time
from pathlib import Path

import dspy

from language_model_config import configure_language_model
from nutrition_fact_repository import NutritionFactRepository
from recipe_enhancement_pipeline import RecipeEnhancementPipeline
from scripts.run_bio_stage import OUTPUT_DIRECTORY, load_recipes

SEEN_SEEDS = (100, 2373)
SECONDS_BETWEEN_RECIPES = 60


def seen_recipe_titles() -> list[str]:
    titles = []
    for seed in SEEN_SEEDS:
        saved = json.loads((OUTPUT_DIRECTORY / f"bio_stage_seed_{seed}.json").read_text())
        titles += [run["recipe"]["title"] for run in saved if run["recipe"]["title"] not in titles]
    return titles


def main() -> None:
    seen_titles = set(seen_recipe_titles())
    candidates = [recipe for recipe in load_recipes() if recipe.title in seen_titles]
    if sys.argv[1] == "--recipes":
        wanted = sys.argv[2:]
        recipes = [recipe for recipe in candidates if recipe.title in wanted]
        if len(recipes) != len(wanted):
            sys.exit(f"Not all of {wanted} are seen recipes. Found: {[recipe.title for recipe in recipes]}")
        seed = "named"
    else:
        seed = int(sys.argv[2]) if len(sys.argv) > 2 else random.randrange(10_000)
        recipes = random.Random(seed).sample(candidates, int(sys.argv[1]))
    count = len(recipes)
    output_path = OUTPUT_DIRECTORY / f"pipeline_run_seed_{seed}.md"
    json_path = output_path.with_suffix(".json")
    output_path.write_text(f"# Full pipeline run, seed {seed}\n")
    print(f"seed={seed}; {len(candidates)} seen recipes to draw from; results are saved to {output_path}")
    configure_language_model()
    pipeline = RecipeEnhancementPipeline(NutritionFactRepository())
    saved_runs = []
    for number, recipe in enumerate(recipes, 1):
        if number > 1:
            time.sleep(SECONDS_BETWEEN_RECIPES)
        try:
            with dspy.track_usage() as usage_tracker:
                result = pipeline(recipe)
        except Exception as error:  # e.g. rate limit; keep going so one failure does not lose the batch
            print(f"FAILED {recipe.title}: {error}")
            with open(output_path, "a") as output_file:
                output_file.write(f"\n## {recipe.title}\n\nFAILED: {error}\n")
            continue
        bio_report, synergy_report, chef_report = result.stage_reports
        lines = [f"\n## {recipe.title}\n", "### Original\n", "```", recipe.as_prompt_text(), "```\n"]
        for report in (bio_report, synergy_report):
            lines += [f"### {report.stage_name.capitalize()} selector (attempts: {report.attempts})\n",
                      f"- applicable: {report.accepted_rule_ids or 'none'}"]
            lines += [f'- already applied {rule_id}: "{quote}"' for rule_id, quote in report.already_applied_quotes.items()]
            lines += [f"- errors: {report.errors}\n"] if report.errors else [""]
        lines += [f"### Chef (attempts: {chef_report.attempts}, "
                  f"shipped: {'ENHANCED' if result.change_log else 'ORIGINAL UNCHANGED'})\n",
                  "```", result.recipe.as_prompt_text(), "```\n", "Changes:"]
        lines += [f"- {change.rule_ids}: `{change.text_before}` -> `{change.text_after}`" for change in result.change_log] or ["- none"]
        lines += ["\nSources of the applied facts:"]
        lines += [f"- {rule_id}: {source['title']} ({source['type']}) {source['url']}"
                  for rule_id, sources in result.evidence_sources.items() for source in map(dict, sources)] or ["- none"]
        lines += ["\nDeclined:"]
        lines += [f"- {rule_id}: {reason}" for rule_id, reason in chef_report.skipped_reasons.items()] or ["- none"]
        lines += ["\nAdaptation notes (suggestions, not applied):"]
        lines += [f"- {note}" for note in result.adaptation_notes] or ["- none"]
        lines += [f"\nchef errors: {chef_report.errors}", f"tokens: {usage_tracker.get_total_tokens()}"]
        with open(output_path, "a") as output_file:
            output_file.write("\n".join(lines) + "\n")
        saved_runs.append({"original": recipe.model_dump(), "result": result.model_dump(),
                           "tokens": usage_tracker.get_total_tokens()})
        json_path.write_text(json.dumps(saved_runs, indent=2, ensure_ascii=False))
        print(f"saved {number}/{count}: {recipe.title} ({'enhanced' if result.change_log else 'unchanged'})", flush=True)


if __name__ == "__main__":
    main()
