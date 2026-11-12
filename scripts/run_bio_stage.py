"""Run the bioavailability stage on a few sample recipes and print facts, governance report and tokens.

Run from the project root: python -m scripts.run_bio_stage [seed] [count]
Picks `count` (default 3) random recipes from the CSV in data/. Pass a seed to repeat the same pick.
Results are saved to outputs/bio_stage_seed_<seed>.md (to read) and .json (for the Chef).
Groq limit is 8K tokens/min, so the script pauses between recipes.
"""
import csv
import json
import random
import re
import sys
import time
from pathlib import Path

import dspy

from domain_models import Recipe
from language_model_config import configure_language_model
from nutrition_fact_repository import NutritionFactRepository
from recipe_enhancement_pipeline import RecipeEnhancementPipeline

SECONDS_BETWEEN_RECIPES = 30

RECIPES_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "MaziMeal_50_Recipes_Culture_Optimized.csv"
DEFAULT_RECIPE_COUNT = 3
OUTPUT_DIRECTORY = Path(__file__).resolve().parent.parent / "outputs"


def load_recipes() -> list[Recipe]:
    """Only name, ingredients and steps are loaded. The CSV's BIO/SYN clue columns would leak the answer."""
    with open(RECIPES_CSV_PATH, newline="", encoding="utf-8-sig") as csv_file:
        return [
            Recipe(
                title=row["Recipe Name"],
                ingredients=[part.strip() for part in row["Ingredients (source ZIP)"].split(",") if part.strip()],
                steps=[re.sub(r"^\d+\.\s*", "", part.strip()) for part in row["Cooking instructions (source ZIP)"].split("|")],
            )
            for row in csv.DictReader(csv_file)
        ]


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else random.randrange(10_000)
    count = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_RECIPE_COUNT
    recipes = random.Random(seed).sample(load_recipes(), count)
    output_path = OUTPUT_DIRECTORY / f"bio_stage_seed_{seed}.md"
    json_path = output_path.with_suffix(".json")
    saved_runs = []
    OUTPUT_DIRECTORY.mkdir(exist_ok=True)
    output_path.write_text(f"# Bio stage run, seed {seed}\n")
    print(f"seed={seed}; results are saved to {output_path}")
    configure_language_model()
    pipeline = RecipeEnhancementPipeline(NutritionFactRepository())
    for number, recipe in enumerate(recipes):
        if number:
            time.sleep(SECONDS_BETWEEN_RECIPES)
        try:
            with dspy.track_usage() as usage_tracker:
                facts, report = pipeline.select_bioavailability_facts(recipe)
        except Exception as error:  # e.g. rate limit; keep going so one failure does not lose the batch
            print(f"FAILED {recipe.title}: {error}")
            with open(output_path, "a") as output_file:
                output_file.write(f"\n## {recipe.title}\n\nFAILED: {error}\n")
            continue
        lines = [f"\n## {recipe.title}\n", "```", recipe.as_prompt_text(), "```\n", "**Applicable**\n"]
        lines += [f"- {fact.rule_id}: triggers {fact.trigger_ingredients}" for fact in facts] or ["- none"]
        lines += ["\n**Already applied**\n"]
        lines += [f'- {rule_id}: "{quote}"' for rule_id, quote in report.already_applied_quotes.items()] or ["- none"]
        lines += ["\n**Skipped**\n"]
        lines += [f"- {rule_id}: {reason}" for rule_id, reason in report.skipped_reasons.items()] or ["- none"]
        lines += [f"\nattempts: {report.attempts}", f"errors: {report.errors}", f"tokens: {usage_tracker.get_total_tokens()}"]
        with open(output_path, "a") as output_file:
            output_file.write("\n".join(lines) + "\n")
        saved_runs.append({"recipe": recipe.model_dump(), "applicable_facts": [f.model_dump() for f in facts],
                           "report": report.model_dump(), "tokens": usage_tracker.get_total_tokens()})
        json_path.write_text(json.dumps(saved_runs, indent=2, ensure_ascii=False))
        print(f"saved {number + 1}/{count}: {recipe.title}", flush=True)


if __name__ == "__main__":
    main()
