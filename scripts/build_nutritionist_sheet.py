"""Build the blind answer sheet for the nutritionist from the held-out recipes.

For each recipe she enters the bioavailability and synergy rules that apply, the ones the recipe already does,
notes, and the specific changes she would make (what the Chef is supposed to do). No model output is shown, so her
answers are independent. Her sheet is later compared with the pipeline's output to compute precision, recall and F1.

Run from the project root: python -m scripts.build_nutritionist_sheet <seen_seed> [<seen_seed> ...]
The sheet holds only the held-out recipes: every CSV recipe that appears in no seen seed's output
(outputs/bio_stage_seed_<seed>.json), so the labels give a clean accuracy test.
Writes outputs/nutritionist_review_unseen.xlsx.
"""
import csv
import json
import random
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from nutrition_fact_repository import NutritionFactRepository
from scripts.run_bio_stage import RECIPES_CSV_PATH

RECIPES_ON_SHEET = 20
SAMPLE_SEED = 1
OUTPUT_DIRECTORY = Path(__file__).resolve().parent.parent / "outputs"
WRAP_TOP = Alignment(wrap_text=True, vertical="top")
ANSWER_FILL = PatternFill("solid", fgColor="FFF2CC")

INSTRUCTIONS = [
    "MaziMeal recipe review: instructions",
    "",
    "Goal: tell us, for each recipe, which rules from the Rules sheet apply, so we can measure how well our system picks them.",
    "",
    "For each recipe on the Recipes sheet, fill the yellow columns:",
    "1. Bioavailability rules that apply: rule ids (for example BIO-002, BIO-008) the recipe could use to improve absorption, because it has the ingredient or preparation but does not yet do what the rule says.",
    "2. Bioavailability rules already applied: rule ids the recipe already follows in its own ingredients or steps.",
    "3. Synergy rules that apply, and 4. Synergy rules already applied: the same two questions for the SYN rules.",
    "5. Notes: anything you want us to know (doubts, why a rule does not fit, missing ingredients in the recipe, and so on).",
    "6. Changes you would make: the specific edits you would make to the recipe, one per line, each starting with the rule id. Say what to change and where (ingredient line or step number), and quote the words you would replace when you can.",
    "   Simple example: BIO-002: crush the garlic and rest it 10 minutes before cooking (step 1).",
    "   Longer example, for a recipe with dry red lentils, carrots, garlic, spinach and olive oil, a step that boils everything together for 45 minutes, and no acid:",
    "   BIO-008: step 2, soak the dry lentils for 4 hours and discard the soak water before cooking.",
    "   BIO-002: step 1, crush the garlic and let it rest 10 minutes before it goes in the pan.",
    "   BIO-004: step 3, replace 'add whole baby carrots' with 'add the carrots chopped and cook until tender'.",
    "   BIO-015: step 5, swap 'boil the spinach for 20 minutes' for 'wilt the spinach for 2 minutes at the end'.",
    "   SYN-008: ingredients, add 'juice of 1 lemon' and stir it in off the heat in the last step.",
    "   SYN-002: no change, the olive oil already covers it.   (If a rule you marked as applying needs no edit, say so in a line like this.)",
    "   One rule can have several lines (one per edit). A rule you decide not to apply goes in Notes, with the reason.",
    "",
    "Please read ingredients and steps together, the way a cook who knows the rules would, not by looking for keywords.",
    "Enter several ids separated by commas. Leave a cell empty when no rule fits. A rule appears in only one of its two columns.",
    "Judge the recipe as written. Do not change amounts or timing beyond what the rule's action says.",
    "The Rules sheet lists every rule you can choose from, with its action. Use only those ids.",
]


def add_header(sheet, header: list[str]) -> None:
    sheet.append(header)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.alignment = WRAP_TOP
    sheet.freeze_panes = "A2"


def main() -> None:
    seen_titles = set()
    for seen_seed in sys.argv[1:]:
        saved = json.loads((OUTPUT_DIRECTORY / f"bio_stage_seed_{seen_seed}.json").read_text())
        seen_titles |= {run["recipe"]["title"] for run in saved}
    with open(RECIPES_CSV_PATH, newline="", encoding="utf-8-sig") as csv_file:
        csv_rows = {row["Recipe Name"]: row for row in csv.DictReader(csv_file)}
    held_out_titles = [title for title in csv_rows if title not in seen_titles]
    chosen = set(random.Random(SAMPLE_SEED).sample(held_out_titles, RECIPES_ON_SHEET))
    titles = [title for title in held_out_titles if title in chosen]  # keep the CSV order
    print(f"seen and left out: {len(seen_titles)}; held out: {len(held_out_titles)}; on the sheet: {len(titles)}")

    workbook = Workbook()
    instructions = workbook.active
    instructions.title = "Instructions"
    for line in INSTRUCTIONS:
        instructions.append([line])
    instructions["A1"].font = Font(bold=True, size=14)
    instructions.column_dimensions["A"].width = 140
    for row in instructions.iter_rows():
        row[0].alignment = WRAP_TOP

    rules = workbook.create_sheet("Rules")
    add_header(rules, ["Rule id", "Type", "Rule name", "Summary", "Action to take", "How to apply"])
    repository = NutritionFactRepository()
    for category, label in (("bioavailability", "Bioavailability"), ("synergy", "Synergy")):
        rule_ids = repository.fetch_rule_ids(category)
        names = repository.fetch_rule_names(category)
        summaries = repository.fetch_fact_summaries(category)
        actions = repository.fetch_recommended_actions(rule_ids)
        for rule_id, summary_line in zip(rule_ids, summaries):
            summary = summary_line.split("): ", 1)[1] if "): " in summary_line else summary_line
            rules.append([rule_id, label, names[rule_id], summary,
                          actions[rule_id].description, actions[rule_id].engine_instruction])
    for column, width in zip("ABCDEF", (10, 16, 34, 70, 50, 60)):
        rules.column_dimensions[column].width = width
    for row in rules.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = WRAP_TOP

    recipes = workbook.create_sheet("Recipes")
    add_header(recipes, [
        "No.", "Recipe", "Ingredients", "Steps",
        "Bioavailability rules that apply", "Bioavailability rules already applied",
        "Synergy rules that apply", "Synergy rules already applied",
        "Notes", "Changes you would make (one per line, start with the rule id)",
    ])
    for number, title in enumerate(titles, 1):
        row = csv_rows[title]
        ingredients = "\n".join(f"- {part.strip()}" for part in row["Ingredients (source ZIP)"].split(",") if part.strip())
        steps = "\n".join(part.strip() for part in row["Cooking instructions (source ZIP)"].split("|"))
        recipes.append([number, title, ingredients, steps])
    for column, width in zip("ABCDEFGHIJ", (5, 24, 36, 70, 22, 22, 22, 22, 36, 60)):
        recipes.column_dimensions[column].width = width
    for row in recipes.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = WRAP_TOP
            if cell.column >= 5:
                cell.fill = ANSWER_FILL
    recipes.freeze_panes = "C2"

    output_path = OUTPUT_DIRECTORY / f"nutritionist_review_unseen.xlsx"
    workbook.save(output_path)
    print(f"saved {output_path} with {len(titles)} recipes")


if __name__ == "__main__":
    main()
