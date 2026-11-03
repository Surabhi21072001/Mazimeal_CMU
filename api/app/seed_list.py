"""The seed recipes, and the one place that reads the spreadsheet naming them.

`docs/MaziMeal_50_Recipes_Culture_Optimized.csv` is the team's list of the 50
recipes to build and test against, chosen for cultural spread. It is read here
rather than copied into a generated file, so there is no second copy to drift
out of date when someone edits a row.

Two of its columns matter to the API:

- `Food.com external_source_id` is how a row finds its database recipe. The
  spreadsheet's own notes ask for exactly this ("Map Food.com
  external_source_id to actual database recipe_id"), and `recipes` carries the
  column, so no name matching is involved.
- the cuisine, which exists only in the spreadsheet. The database has
  `regional_origin`, but it is not populated for these rows, and the
  spreadsheet is honest that the association is inferred from the dish name
  rather than verified - which the screen repeats rather than hides.

The ingredient and rule-clue columns are deliberately ignored. They are
keyword guesses made while the list was drawn up, and the rules engine
answers the same question properly from the tagged ingredients.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

CSV_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "docs"
    / "MaziMeal_50_Recipes_Culture_Optimized.csv"
)

EXTERNAL_ID = "Food.com external_source_id"
NAME = "Recipe Name"
CUISINE = "Cuisine / cultural association (inferred)"


@lru_cache(maxsize=1)
def seed_rows() -> tuple[dict, ...]:
    """The spreadsheet, as (external_source_id, name, cuisine) in its own order.

    An empty tuple when the file is missing, so a deployment that did not ship
    docs/ serves an empty list rather than failing every request.
    """
    if not CSV_PATH.exists():
        return ()
    with CSV_PATH.open(newline="") as handle:
        return tuple(
            {
                "external_source_id": external_id,
                "csv_name": (row.get(NAME) or "").strip(),
                "cuisine": (row.get(CUISINE) or "").strip() or None,
            }
            for row in csv.DictReader(handle)
            if (external_id := (row.get(EXTERNAL_ID) or "").strip())
        )


def external_ids() -> list[str]:
    return [row["external_source_id"] for row in seed_rows()]
