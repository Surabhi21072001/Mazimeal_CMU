"""Run the Chef on the facts a saved bio stage run selected, and show original vs enhanced recipes.

Run from the project root: python -m scripts.run_chef_stage <seed> [max_recipes]
Reads outputs/bio_stage_seed_<seed>.json, writes outputs/chef_stage_seed_<seed>.md and .json.
Recipes with no applicable facts are skipped (the Chef has nothing to apply).
Groq limit is 8K tokens/min, so the script pauses between recipes.
"""
import json
import sys
import time
from pathlib import Path

import dspy

from domain_models import ApplicableFact, Recipe
from language_model_config import configure_language_model
from nutrition_fact_repository import NutritionFactRepository
from recipe_enhancement_pipeline import RecipeEnhancementPipeline

OUTPUT_DIRECTORY = Path(__file__).resolve().parent.parent / "outputs"
SECONDS_BETWEEN_RECIPES = 30


def main() -> None:
    seed = int(sys.argv[1])
    bio_runs = [
        run for run in json.loads((OUTPUT_DIRECTORY / f"bio_stage_seed_{seed}.json").read_text())
        if run["applicable_facts"]
    ]
    if len(sys.argv) > 2:
        bio_runs = bio_runs[: int(sys.argv[2])]
    output_path = OUTPUT_DIRECTORY / f"chef_stage_seed_{seed}.md"
    json_path = output_path.with_suffix(".json")
    output_path.write_text(f"# Chef stage run, from bio stage seed {seed}\n")
    print(f"{len(bio_runs)} recipes with facts; results are saved to {output_path}")
    configure_language_model()
    pipeline = RecipeEnhancementPipeline(NutritionFactRepository())
    saved_runs = []
    for number, bio_run in enumerate(bio_runs, 1):
        if number > 1:
            time.sleep(SECONDS_BETWEEN_RECIPES)
        recipe = Recipe(**bio_run["recipe"])
        facts = [ApplicableFact(**fact) for fact in bio_run["applicable_facts"]]
        try:
            with dspy.track_usage() as usage_tracker:
                result = pipeline.apply_recommended_actions(recipe, facts)
        except Exception as error:  # e.g. rate limit; keep going so one failure does not lose the batch
            print(f"FAILED {recipe.title}: {error}")
            with open(output_path, "a") as output_file:
                output_file.write(f"\n## {recipe.title}\n\nFAILED: {error}\n")
            continue
        report = result.stage_reports[0]
        lines = [
            f"\n## {recipe.title}\n",
            f"Facts given: {[fact.rule_id for fact in facts]}  |  attempts: {report.attempts}  |  "
            f"shipped: {'ENHANCED' if result.change_log else 'ORIGINAL UNCHANGED'}\n",
            "### Original\n", "```", recipe.as_prompt_text(), "```\n",
            "### Enhanced\n", "```", result.recipe.as_prompt_text(), "```\n",
            "### Changes\n",
        ]
        lines += [
            f"- {change.rule_ids}: `{change.text_before}` -> `{change.text_after}`" for change in result.change_log
        ] or ["- none"]
        lines += ["\n### Declined\n"]
        lines += [f"- {rule_id}: {reason}" for rule_id, reason in report.skipped_reasons.items()] or ["- none"]
        lines += ["\n### Adaptation notes (suggestions, not applied)\n"]
        lines += [f"- {note}" for note in result.adaptation_notes] or ["- none"]
        lines += [f"\nerrors: {report.errors}", f"tokens: {usage_tracker.get_total_tokens()}"]
        with open(output_path, "a") as output_file:
            output_file.write("\n".join(lines) + "\n")
        saved_runs.append({
            "original": recipe.model_dump(), "result": result.model_dump(),
            "tokens": usage_tracker.get_total_tokens(),
        })
        json_path.write_text(json.dumps(saved_runs, indent=2, ensure_ascii=False))
        print(f"saved {number}/{len(bio_runs)}: {recipe.title} ({'enhanced' if result.change_log else 'unchanged'})", flush=True)


if __name__ == "__main__":
    main()
