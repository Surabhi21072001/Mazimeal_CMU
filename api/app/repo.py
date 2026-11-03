"""
Where the data comes from.

One interface, two implementations for now. The fixture one reads the json in
api/fixtures; the Supabase one will call the functions the other team already
wrote (fn_recipe_nutrition, fn_home) once we have a project of our own.
Nothing above this file knows which is in use.
"""
from __future__ import annotations

import json
from functools import lru_cache

from . import config


class FixtureRepo:
    """Serves the bundled fixtures. Everything it returns is marked as such."""

    name = "fixture"

    @staticmethod
    @lru_cache(maxsize=32)
    def _read(filename: str) -> dict | None:
        path = config.FIXTURES_DIR / filename
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def household(self) -> dict | None:
        return self._read("household.json")

    def recommendations(self, member_id: str, meal: str, target_nutrient: str | None) -> dict | None:
        # Only one combination exists as a fixture. Returning it for every
        # request would be a lie, so the payload keeps its own member and meal
        # and the frontend says when they do not match what was asked for.
        return self._read("recommendations_maya_lunch.json")

    def recipe(self, recipe_id: str) -> dict | None:
        return self._read(f"recipe_{recipe_id}.json")

    def seed_recipes(self) -> dict:
        """The bundled recipes, shaped like the real seed list.

        Five, not the spreadsheet's fifty: a build with no backend can only
        offer what was baked into it, and saying so is better than an empty
        screen. `source` is what the UI reads to say which it is looking at.
        """
        results = []
        for filename in sorted(config.FIXTURES_DIR.glob("recipe_*.json")):
            data = self._read(filename.name)
            if not data:
                continue
            results.append(
                {
                    "recipe_id": data["recipe_id"],
                    "external_source_id": None,
                    "cuisine": None,
                    "csv_name": data["name"],
                    "name": data["name"],
                    "meal": data.get("meal"),
                    "servings": data.get("servings"),
                    "time_min": data.get("time_min"),
                    "tags": data.get("tags", []),
                    "ingredient_count": len(data.get("ingredients", [])),
                    "step_count": len(data.get("steps", [])),
                    "nutrient_count": len(data.get("nutrition_per_serving", [])),
                    "rule_count": len(data.get("matched_rules", [])),
                    "in_database": True,
                }
            )
        return {
            "results": results,
            "total": len(results),
            "in_database": len(results),
            "source": "fixture",
        }


def get_repo():
    fixtures = FixtureRepo()
    if config.REPO == "supabase":
        from .supabase_repo import get_supabase_repo

        # Recipes and rules come from the database; household and
        # recommendations fall back to fixtures until they exist there too.
        return get_supabase_repo(fixtures)
    return fixtures
