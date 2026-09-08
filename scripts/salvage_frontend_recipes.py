#!/usr/bin/env python3
"""
Pull the hardcoded recipes out of the frontend into the seed CSVs.

    python3 scripts/salvage_frontend_recipes.py

Reads web/src/features/synergia-light/SynergiaLightApp.jsx, extracts the
recipeCollections array, writes schema/seed/recipes.csv and
schema/seed/recipe_ingredients.csv. Needs node on PATH to parse the JS.

Ingredient lines in the frontend are free text ("2 tbsp chopped parsley"), so
quantities are parsed best-effort. Anything that couldn't be parsed gets
quantity 1, unit "portion", and the original text in preparation_note.
Check those by hand.
"""
import csv, json, re, subprocess, sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSX  = ROOT / "web/src/features/synergia-light/SynergiaLightApp.jsx"
OUT  = ROOT / "schema/seed"

UNITS = {
    "g": "g", "gram": "g", "grams": "g", "kg": "kg",
    "ml": "ml", "l": "l", "litre": "l", "liter": "l",
    "tsp": "tsp", "teaspoon": "tsp", "teaspoons": "tsp",
    "tbsp": "tbsp", "tablespoon": "tbsp", "tablespoons": "tbsp",
    "cup": "cup", "cups": "cup", "oz": "oz", "lb": "lb",
    "clove": "cloves", "cloves": "cloves", "slice": "slices", "slices": "slices",
    "can": "can", "cans": "can", "handful": "handful", "pinch": "pinch",
    "bunch": "bunch", "piece": "whole", "pieces": "whole",
}
PREP_WORDS = {"chopped", "diced", "minced", "sliced", "grated", "crushed",
              "shredded", "cooked", "roasted", "steamed", "fresh", "large",
              "small", "medium", "ripe", "baby", "whole", "ground", "toasted"}

DIETARY = {"vegetarian": "vegetarian", "vegan": "vegan", "low carb": "low_carb",
           "gluten free": "gluten_free", "gluten-free": "gluten_free",
           "dairy free": "dairy_free", "dairy-free": "dairy_free", "keto": "keto"}


def extract_array(src: str) -> list:
    start = src.index("const recipeCollections = [")
    start = src.index("[", start)
    depth, i = 0, start
    while True:
        c = src[i]
        if c == "[": depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0: break
        i += 1
    js = src[start:i + 1]
    out = subprocess.run(
        ["node", "-e", "process.stdout.write(JSON.stringify(eval(require('fs').readFileSync(0,'utf8'))))"],
        input=js, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def parse_minutes(s):
    m = re.search(r"(\d+)", s or "")
    return int(m.group(1)) if m else ""


def parse_ingredient(line: str):
    """'2 tbsp chopped parsley' -> (2, 'tbsp', 'parsley', 'chopped')"""
    text = line.strip()
    m = re.match(r"^(\d+(?:\.\d+)?|\d+/\d+|\d+\s+\d+/\d+)\s+(.*)$", text)
    if not m:
        return 1, "portion", text, ""
    qty_s, rest = m.group(1), m.group(2)
    qty = float(sum(Fraction(p) for p in qty_s.split()))
    words = rest.split()
    unit = "whole"
    if words and words[0].lower().rstrip(".") in UNITS:
        unit = UNITS[words.pop(0).lower().rstrip(".")]
    prep = [w for w in words if w.lower() in PREP_WORDS]
    name = " ".join(w for w in words if w.lower() not in PREP_WORDS) or rest
    return qty, unit, name, " ".join(prep)


def main():
    src = JSX.read_text()
    recipes = extract_array(src)
    OUT.mkdir(parents=True, exist_ok=True)

    r_rows, i_rows, unparsed = [], [], 0
    for r in recipes:
        name = r["title"].strip()
        tags = []
        d = (r.get("dietary") or "").lower()
        if d in DIETARY: tags.append(DIETARY[d])
        r_rows.append({
            "recipe_name": name,
            "meal_category": r.get("mealType", "Dinner"),
            "dietary_tags": "|".join(tags),
            "prep_time_min": parse_minutes(r.get("prep")),
            "cook_time_min": "",
            "difficulty_level": {"Advanced": "Hard"}.get(r.get("difficulty", ""), r.get("difficulty", "")),
            "servings": 4,
            "calories_per_serving": r.get("calories", ""),
            "regional_origin": r.get("cuisine", ""),
            "description": r.get("subtitle", ""),
            "steps": "|".join(r.get("steps", [])),
        })
        for line in r.get("ingredients", []):
            qty, unit, iname, prep = parse_ingredient(line)
            if unit == "portion": unparsed += 1
            i_rows.append({
                "recipe_name": name,
                "ingredient_name": iname,
                "quantity": qty,
                "unit": unit,
                "preparation_note": prep,
                "is_optional": "false",
                "food_category": "Uncategorized",
            })

    with open(OUT / "recipes.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=r_rows[0].keys()); w.writeheader(); w.writerows(r_rows)
    with open(OUT / "recipe_ingredients.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=i_rows[0].keys()); w.writeheader(); w.writerows(i_rows)

    print(f"{len(r_rows)} recipes, {len(i_rows)} ingredient lines -> {OUT.relative_to(ROOT)}/")
    print(f"{unparsed} ingredient lines had no quantity; check rows with unit=portion")


if __name__ == "__main__":
    main()
