"""Build seed fact JSON files from Guy's rule workbook.

Reads the 'Bioavailability' and 'Food Synergies' tabs (read-only) and writes
data/seed_facts/bioavailability.json and data/seed_facts/synergy.json using the
fact record schema in docs/implementation-spec.md.

Run: python scripts/build_seed_facts.py   (needs openpyxl)
"""
import json
from pathlib import Path

import openpyxl

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKBOOK_PATH = PROJECT_ROOT / "IN WORK - MaziMeal Recipe Optimization Rules.xlsx"
OUTPUT_DIRECTORY = PROJECT_ROOT / "data" / "seed_facts"

TAB_TO_CATEGORY = {
    "Bioavailability": ("bioavailability", "bioavailability.json"),
    "Food Synergies": ("synergy", "synergy.json"),
}


def build_fact_record(row: dict, category: str) -> dict:
    return {
        "rule_id": row["rule_id"],
        "rule_name": row["rule_name"],
        "category": category,
        "action": {
            "description": row["action"],
            "code": row["action_code"],
            "engine_instruction": row["recipe_engine_instruction"],
        },
        "evidence": {
            "tier": row["evidence_tier"],
            "summary": row["evidence_summary"],
            "sources": [
                {
                    "title": row["source_title"],
                    "type": row["source_type"],
                    "url": row["source_url"],
                    "review_date": str(row["review_date"]),
                }
            ],
        },
    }


def read_rows(worksheet) -> list[dict]:
    rows = worksheet.iter_rows(values_only=True)
    column_names = next(row for row in rows if "rule_id" in row)
    return [dict(zip(column_names, row)) for row in rows if row[0]]


def main() -> None:
    workbook = openpyxl.load_workbook(WORKBOOK_PATH, data_only=True, read_only=True)
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for tab_name, (category, file_name) in TAB_TO_CATEGORY.items():
        rows = read_rows(workbook[tab_name])
        # Only recipe_safe rules go in v1: conditional and instruction_only rules
        # carry safety limits (medication, allergy, food safety) the schema cannot hold.
        left_out = [row["rule_id"] for row in rows if row["automation_status"] != "recipe_safe"]
        print(f"{tab_name}: left out {left_out}")
        facts = [
            build_fact_record(row, category)
            for row in rows
            if row["automation_status"] == "recipe_safe"
        ]
        rule_ids = [fact["rule_id"] for fact in facts]
        assert len(rule_ids) == len(set(rule_ids)), f"duplicate rule_id in {tab_name}"
        for fact in facts:
            missing = [k for k in ("rule_name",) if not fact[k]]
            missing += [k for k, v in fact["action"].items() if not v]
            missing += [k for k, v in fact["evidence"].items() if not v]
            assert not missing, f"{fact['rule_id']} missing {missing}"
        output_path = OUTPUT_DIRECTORY / file_name
        output_path.write_text(json.dumps(facts, indent=2, ensure_ascii=False) + "\n")
        print(f"{output_path.relative_to(PROJECT_ROOT)}: {len(facts)} facts")


if __name__ == "__main__":
    main()
