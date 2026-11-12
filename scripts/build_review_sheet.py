"""Build an Excel review sheet from a saved bio stage run, for Guy to correct (the first gold set).
For each fact Guy picks the correct outcome: applicable, already applied, or not relevant.

Run from the project root: python -m scripts.build_review_sheet <seed>
Reads outputs/bio_stage_seed_<seed>.json (and _review_notes.md if present),
writes outputs/bio_stage_seed_<seed>_review.xlsx.
"""
import json
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from nutrition_fact_repository import NutritionFactRepository

OUTPUT_DIRECTORY = Path(__file__).resolve().parent.parent / "outputs"
FILLS = {
    "applicable": PatternFill("solid", fgColor="E2F0D9"),
    "already applied": PatternFill("solid", fgColor="DDEBF7"),
}
WRAP_TOP = Alignment(wrap_text=True, vertical="top")


def add_sheet(workbook: Workbook, title: str, header: list[str], rows: list[list], widths: list[int]):
    sheet = workbook.create_sheet(title)
    sheet.append(header)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append(row)
    for column, width in zip("ABCDEFGHIJ", widths):
        sheet.column_dimensions[column].width = width
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = WRAP_TOP
    sheet.freeze_panes = "A2"
    return sheet


def main() -> None:
    seed = int(sys.argv[1])
    runs = json.loads((OUTPUT_DIRECTORY / f"bio_stage_seed_{seed}.json").read_text())
    rule_names = NutritionFactRepository().fetch_rule_names("bioavailability")

    review_rows, recipe_rows = [], []
    for number, run in enumerate(runs, 1):
        title = run["recipe"]["title"]
        triggers = {fact["rule_id"]: fact["trigger_ingredients"] for fact in run["applicable_facts"]}
        reasons = run["report"]["skipped_reasons"]
        quotes = run["report"].get("already_applied_quotes", {})
        for rule_id in run["report"]["given_rule_ids"]:
            if rule_id in triggers:
                decision, detail = "applicable", "triggers: " + ", ".join(triggers[rule_id])
            elif rule_id in quotes:
                decision, detail = "already applied", f'quote: "{quotes[rule_id]}"'
            else:
                decision, detail = "skipped", reasons.get(rule_id, "")
            review_rows.append([number, title, rule_id, rule_names[rule_id], decision, detail, None, None])
        recipe_rows.append([
            number, title,
            "\n".join(run["recipe"]["ingredients"]),
            "\n".join(f"{n}. {step}" for n, step in enumerate(run["recipe"]["steps"], 1)),
        ])

    workbook = Workbook()
    workbook.remove(workbook.active)
    review = add_sheet(
        workbook, "Review",
        ["Recipe #", "Recipe", "Rule id", "Rule name", "Model decision", "Triggers or reason",
         "Correct outcome (Guy)", "Notes"],
        review_rows, [9, 30, 10, 38, 16, 60, 24, 40],
    )
    for row in review.iter_rows(min_row=2):
        fill = FILLS.get(row[4].value)
        if fill:
            for cell in row:
                cell.fill = fill
    answers = DataValidation(type="list", formula1='"applicable,already applied,not relevant"', allow_blank=True)
    review.add_data_validation(answers)
    answers.add(f"G2:G{len(review_rows) + 1}")
    add_sheet(workbook, "Recipes", ["Recipe #", "Recipe", "Ingredients", "Steps"], recipe_rows, [9, 30, 45, 90])

    notes_path = OUTPUT_DIRECTORY / f"bio_stage_seed_{seed}_review_notes.md"
    if notes_path.exists():
        add_sheet(workbook, "Reviewer notes", ["Notes"], [[line] for line in notes_path.read_text().splitlines() if line.strip()], [140])

    output_path = OUTPUT_DIRECTORY / f"bio_stage_seed_{seed}_review.xlsx"
    workbook.save(output_path)
    print(f"{output_path}: {len(runs)} recipes, {len(review_rows)} rows to review")


if __name__ == "__main__":
    main()
