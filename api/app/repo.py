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


def get_repo():
    if config.REPO == "supabase":  # not built yet; needs our own project first
        raise NotImplementedError(
            "The Supabase repository is not written yet. Run with MAZI_REPO=fixture."
        )
    return FixtureRepo()
