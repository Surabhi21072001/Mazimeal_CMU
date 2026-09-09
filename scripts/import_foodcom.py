#!/usr/bin/env python3
"""
Import recipes from the Food.com dataset.

    python3 scripts/import_foodcom.py recipes.parquet --dry-run
    python3 scripts/import_foodcom.py recipes.parquet -o schema/seed/foodcom_400.sql
    psql -d mazimeal -v ON_ERROR_STOP=1 -f schema/seed/foodcom_400.sql

Takes the Kaggle "Food.com Recipes and Reviews" file (recipes.csv or
recipes.parquet) or the HuggingFace mirror AkashPS11/recipes_data_food.com.
Picks the best-rated recipes to fill each meal bucket, then writes SQL for
recipes, ingredients, recipe_ingredients, recipe_steps and recipe_nutrition.
The SQL is idempotent.

Targets default to the week-1 plan: Breakfast 80, Lunch 80, Dinner 100,
Snack 60, plus 80 special-diet recipes (vegan, gluten_free, ...) on top,
400 in all. The extra 80 keep their own meal slot.

Needs pandas (and pyarrow for parquet). Both ship with Anaconda.
"""
import argparse, html, re, sys
from collections import Counter, defaultdict
from fractions import Fraction

try:
    import pandas as pd
except ImportError:
    sys.exit("needs pandas: pip install pandas pyarrow")

# ---------------------------------------------------------------------------
# Dataset -> schema mappings
# ---------------------------------------------------------------------------

# Food.com Keywords / RecipeCategory -> our dietary_tags
DIETARY = {
    "vegan": "vegan", "vegetarian": "vegetarian", "lactose free": "dairy_free",
    "dairy free foods": "dairy_free", "egg free": "egg_free", "low carb": "low_carb",
    "gluten free": "gluten_free", "low cholesterol": "low_cholesterol",
    "kosher": "kosher", "halal": "halal", "diabetic friendly": "diabetic_friendly",
    "high protein": "high_protein", "low protein": "low_protein", "no shell fish": "shellfish_free",
}

# RecipeCategory is the reliable signal; Keywords are noisy (a brownie can be
# tagged "Lunch/Snacks"). So: exact category first, keywords as fallback.
DESSERT_CATEGORIES = {
    "Dessert", "Bar Cookie", "Drop Cookies", "Chocolate Chip Cookies", "Pie", "Tarts", "Candy",
    "Frozen Desserts", "Ice Cream", "Cheesecake", "Gelatin", "Bread Pudding", "Jellies",
}
DRINK_CATEGORIES = {"Beverages", "Smoothies", "Shakes", "Punch Beverage"}
NOT_A_MEAL_CATEGORIES = {   # components, preserves, and things that aren't food
    "Sauces", "Salad Dressings", "Stocks", "Chutneys", "Canning",
    "Breads", "Yeast Breads", "Sourdough Breads", "Bread Machine",
    "Household Cleaner", "Bath/Beauty", "Homeopathy/Remedies",
}
DESSERT_KEYWORDS = {"Dessert", "Cookie & Brownie"}

SLOT_BY_CATEGORY = {
    "Breakfast": "Breakfast", "Oatmeal": "Breakfast", "Brunch": "Breakfast",
    "Spreads": "Snack", "Summer Dip": "Snack",
}
LIGHT_KCAL = 250   # "Lunch/Snacks" category: under this per serving is a Snack

# A "Brunch" keyword on a chicken or steak recipe doesn't make it breakfast.
MAIN_COURSE_CATEGORIES = {
    "Chicken", "Chicken Breast", "Chicken Thigh & Leg", "Whole Chicken", "Poultry", "Turkey Breasts",
    "Whole Turkey", "Duck", "Duck Breasts", "Pork", "Ham", "Meat", "Steak", "Roast Beef", "Meatloaf",
    "Meatballs", "Lamb/Sheep", "Veal", "Deer", "Wild Game", "Tilapia", "Halibut", "Catfish", "Trout",
    "Bass", "Whitefish", "Mahi Mahi", "Orange Roughy", "Perch", "Tuna", "Crab", "Lobster", "Mussels",
    "Squid", "Crawfish", "Stew", "Curries", "Gumbo", "Roast",
}

NUTRIENTS = [  # dataset column -> (nutrient_id, unit)
    ("calories",             "Energy",             "kcal"),
    ("protein_content",      "Macro_Protein",      "g"),
    ("fat_content",          "Macro_Fat",          "g"),
    ("saturated_fat_content","Saturated_Fat",      "g"),
    ("carbohydrate_content", "Macro_Carbohydrate", "g"),
    ("fiber_content",        "Fiber",              "g"),
    ("sugar_content",        "Sugar",              "g"),
    ("sodium_content",       "Sodium",             "mg"),
    ("cholesterol_content",  "Cholesterol",        "mg"),
]

COLS = {  # dataset -> raw table column
    "RecipeId": "recipe_id", "Name": "name", "AuthorId": "author_id", "AuthorName": "author_name",
    "CookTime": "cook_time", "PrepTime": "prep_time", "TotalTime": "total_time",
    "DatePublished": "date_published", "Description": "description", "Images": "images",
    "RecipeCategory": "recipe_category", "Keywords": "keywords",
    "RecipeIngredientQuantities": "recipe_ingredient_quantities",
    "RecipeIngredientParts": "recipe_ingredient_parts",
    "AggregatedRating": "aggregated_rating", "ReviewCount": "review_count",
    "Calories": "calories", "FatContent": "fat_content", "SaturatedFatContent": "saturated_fat_content",
    "CholesterolContent": "cholesterol_content", "SodiumContent": "sodium_content",
    "CarbohydrateContent": "carbohydrate_content", "FiberContent": "fiber_content",
    "SugarContent": "sugar_content", "ProteinContent": "protein_content",
    "RecipeServings": "recipe_servings", "RecipeYield": "recipe_yield",
    "RecipeInstructions": "recipe_instructions",
}

# ---------------------------------------------------------------------------
# Parsing the dataset's odd encodings
# ---------------------------------------------------------------------------

def r_vector(v):
    """c("a", "b") -> ['a', 'b'].  Also handles real lists from parquet."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return []
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v if x is not None]
    if hasattr(v, "tolist"):                       # numpy array from parquet
        return [str(x) for x in v.tolist() if x is not None]
    s = str(v).strip()
    if s in ("", "NA", "character(0)"):
        return []
    if s.startswith("c(") and s.endswith(")"):
        s = s[2:-1]
    return [m.group(1).replace('\\"', '"') for m in re.finditer(r'"((?:[^"\\]|\\.)*)"', s)]


def iso_minutes(v):
    """PT1H30M -> 90"""
    if not isinstance(v, str):
        return None
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?", v)
    if not m or not any(m.groups()):
        return None
    d, h, mi = (int(x) if x else 0 for x in m.groups())
    return d * 1440 + h * 60 + mi


def quantity(v):
    """'1 1⁄2' -> 1.5, '2 -3' -> 2, NA -> None"""
    s = str(v).replace("⁄", "/").replace("½", "1/2").replace("¼", "1/4").replace("¾", "3/4")
    s = s.split("-")[0].strip()
    if not s or s == "NA":
        return None
    try:
        return float(sum(Fraction(p) for p in s.split()))
    except (ValueError, ZeroDivisionError):
        return None


def meal_slot(category, keywords, kcal):
    """Breakfast / Lunch / Dinner / Snack, or DESSERT / DRINK / SKIP."""
    category = category or ""
    kw = set(keywords)
    if category in DESSERT_CATEGORIES:   return "DESSERT"
    if category in DRINK_CATEGORIES:     return "DRINK"
    if category in NOT_A_MEAL_CATEGORIES: return "SKIP"
    if category in SLOT_BY_CATEGORY:     return SLOT_BY_CATEGORY[category]
    if kw & DESSERT_KEYWORDS:            return "DESSERT"
    if category == "Lunch/Snacks":
        return "Snack" if kcal is not None and kcal < LIGHT_KCAL else "Lunch"
    if category in ("Quick Breads", "Scones"):   # muffins, banana bread
        return "Breakfast" if kw & {"Breakfast", "Brunch"} else "Snack"
    if kw & {"Breakfast", "Brunch"} and category not in MAIN_COURSE_CATEGORIES:
        return "Breakfast"
    if "Lunch/Snacks" in kw:
        return "Snack" if kcal is not None and kcal < LIGHT_KCAL else "Lunch"
    return "Dinner"


def dietary_tags(category, keywords):
    hay = [k.lower() for k in keywords] + [(category or "").lower()]
    return sorted({DIETARY[k] for k in hay if k in DIETARY})


def clean(s, limit=None):
    s = re.sub(r"\s+", " ", html.unescape(str(s or ""))).strip()
    return s[:limit] if limit else s


def q(v):
    return "NULL" if v is None or v == "" else "'" + str(v).replace("'", "''") + "'"


# ---------------------------------------------------------------------------
# Load, filter, pick
# ---------------------------------------------------------------------------

def load(path):
    df = pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path, low_memory=False)
    missing = [c for c in COLS if c not in df.columns]
    if missing:
        sys.exit(f"dataset is missing columns: {missing}")
    df = df[list(COLS)].rename(columns=COLS)
    return df


def candidates(df, min_rating, min_reviews, exclude_desserts):
    rows, dropped = [], Counter()
    for r in df.itertuples(index=False):
        parts = r_vector(r.recipe_ingredient_parts)
        if not parts:                                  dropped["no ingredients"] += 1; continue
        if pd.isna(r.calories) or pd.isna(r.protein_content): dropped["no nutrition"] += 1; continue
        # no serving count means the nutrition is for the whole yield ("1 loaf")
        if pd.isna(r.recipe_servings) or r.recipe_servings <= 0: dropped["no serving count"] += 1; continue
        if pd.isna(r.aggregated_rating) or r.aggregated_rating < min_rating: dropped["rating"] += 1; continue
        if pd.isna(r.review_count) or r.review_count < min_reviews: dropped["reviews"] += 1; continue
        kw = r_vector(r.keywords)
        slot = meal_slot(r.recipe_category, kw, None if pd.isna(r.calories) else float(r.calories))
        if slot == "SKIP":                             dropped["not a meal"] += 1; continue
        if slot == "DRINK":                            dropped["drinks"] += 1; continue
        if slot == "DESSERT":
            if exclude_desserts:                       dropped["desserts"] += 1; continue
            slot = "Snack"
        rows.append(dict(
            ext_id=int(r.recipe_id), name=clean(r.name, 300), slot=slot,
            tags=dietary_tags(r.recipe_category, kw), rating=float(r.aggregated_rating),
            reviews=int(r.review_count), prep=iso_minutes(r.prep_time), cook=iso_minutes(r.cook_time),
            servings=int(r.recipe_servings),
            description=clean(r.description), category=clean(r.recipe_category, 100),
            parts=parts, quantities=r_vector(r.recipe_ingredient_quantities),
            steps=[clean(s) for s in r_vector(r.recipe_instructions) if clean(s)],
            nutrition={nid: (float(getattr(r, col)), unit) for col, nid, unit in NUTRIENTS
                       if not pd.isna(getattr(r, col))},
        ))
    return rows, dropped


def pick(rows, targets, special):
    """Fill each slot to its target, best-reviewed first, then add `special`
    more that carry a dietary tag. Dedup by normalised name."""
    rows.sort(key=lambda r: (-r["reviews"], -r["rating"]))
    seen, chosen, per_slot = set(), [], Counter()

    def take(r):
        key = re.sub(r"[^a-z0-9]", "", r["name"].lower())
        if key in seen:
            return False
        seen.add(key); chosen.append(r); per_slot[r["slot"]] += 1
        return True

    for r in rows:
        if per_slot[r["slot"]] < targets.get(r["slot"], 0):
            take(r)
    extra, per_slot_extra = 0, Counter()
    cap = -(-special // max(len(targets), 1))      # spread evenly over slots
    for r in rows:
        if extra >= special: break
        if r["tags"] and per_slot_extra[r["slot"]] < cap and take(r):
            extra += 1; per_slot_extra[r["slot"]] += 1
    tagged = sum(1 for r in chosen if r["tags"])
    return chosen, per_slot, tagged


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

def emit(chosen, out):
    w = out.write
    w("-- Generated by scripts/import_foodcom.py. Safe to run more than once.\nBEGIN;\n\n")

    # "light brown sugar" and "light-brown sugar" are one ingredient: first spelling wins
    canon = {}
    def name_of(p):
        k = clean(p, 200)
        key = re.sub(r"[^a-z0-9]", "", k.lower())
        return canon.setdefault(key, k) if key else ""

    for r in chosen:
        r["parts"] = [name_of(p) for p in r["parts"]]

    w("-- ingredients\n")
    for k in canon.values():
        w(f"INSERT INTO ingredients (ingredient_name, food_category, data_source) VALUES ({q(k)}, 'Uncategorized', 'Manual') "
          f"ON CONFLICT DO NOTHING;\n")

    w("\n-- recipes\n")
    for r in chosen:
        tags = "ARRAY[" + ",".join(q(t) for t in r["tags"]) + "]::text[]" if r["tags"] else "NULL"
        w(f"INSERT INTO recipes (external_source_id, recipe_name, recipe_description, meal_category, dietary_tags, "
          f"prep_time_min, cook_time_min, servings, calories_per_serving, regional_origin, data_source)\n"
          f"VALUES ({q(r['ext_id'])}, {q(r['name'])}, {q(r['description'])}, {q(r['slot'])}, {tags}, "
          f"{r['prep'] if r['prep'] is not None else 'NULL'}, {r['cook'] if r['cook'] is not None else 'NULL'}, "
          f"{r['servings']}, {r['nutrition'].get('Energy', (None,))[0] or 'NULL'}, NULL, 'Food.com')\n"
          f"ON CONFLICT DO NOTHING;\n")

    w("\n-- recipe_ingredients (units aren't in the dataset; quantity is the bare number)\n")
    for r in chosen:
        for i, p in enumerate(r["parts"]):
            k = clean(p, 200)
            if not k: continue
            qty = quantity(r["quantities"][i]) if i < len(r["quantities"]) else None
            w(f"INSERT INTO recipe_ingredients (recipe_id, ingredient_id, quantity, unit)\n"
              f"SELECT rc.recipe_id, i.ingredient_id, {qty if qty else 1}, {q('unit') if qty else q('portion')} "
              f"FROM recipes rc, ingredients i WHERE rc.external_source_id = {q(r['ext_id'])} "
              f"AND lower(btrim(i.ingredient_name)) = {q(k.lower())}\n"
              f"ON CONFLICT (recipe_id, ingredient_id) DO NOTHING;\n")

    w("\n-- recipe_steps\n")
    for r in chosen:
        for n, s in enumerate(r["steps"], 1):
            w(f"INSERT INTO recipe_steps (recipe_id, step_number, instruction) "
              f"SELECT recipe_id, {n}, {q(s)} FROM recipes WHERE external_source_id = {q(r['ext_id'])} "
              f"ON CONFLICT (recipe_id, step_number) DO NOTHING;\n")

    w("\n-- recipe_nutrition (per serving, as published)\n")
    for r in chosen:
        for nid, (val, unit) in r["nutrition"].items():
            w(f"INSERT INTO recipe_nutrition (recipe_id, nutrient_id, per_serving, unit) "
              f"SELECT recipe_id, {q(nid)}, {val}, {q(unit)} FROM recipes WHERE external_source_id = {q(r['ext_id'])} "
              f"ON CONFLICT (recipe_id, nutrient_id) DO NOTHING;\n")

    w("\nCOMMIT;\n")


# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser()
    p.add_argument("file", help="recipes.csv or recipes.parquet")
    p.add_argument("-o", "--out", default="schema/seed/foodcom_400.sql")
    p.add_argument("--targets", default="Breakfast=80,Lunch=80,Dinner=100,Snack=60")
    p.add_argument("--special", type=int, default=80, help="extra special-diet recipes on top of the slot targets")
    p.add_argument("--min-rating", type=float, default=4.0)
    p.add_argument("--min-reviews", type=int, default=5)
    p.add_argument("--include-desserts", action="store_true", help="count desserts as snacks")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--raw-csv", help="also write the full dataset (all rows, raw table column order) to this CSV for \\copy into foodcom_recipes_raw")
    a = p.parse_args()
    targets = {k: int(v) for k, v in (x.split("=") for x in a.targets.split(","))}

    df = load(a.file)
    print(f"{len(df):,} rows in dataset")
    if a.raw_csv:
        raw = df.copy()
        for c in ("keywords", "recipe_ingredient_quantities", "recipe_ingredient_parts", "recipe_instructions"):
            raw[c] = raw[c].map(lambda v: v if isinstance(v, str) else 'c(' + ', '.join('"' + str(x).replace('"', '\\"') + '"' for x in r_vector(v)) + ')')
        raw.to_csv(a.raw_csv, index=False)
        print(f"-> {a.raw_csv}  (load with: \\copy foodcom_recipes_raw({','.join(COLS.values())}) from '{a.raw_csv}' csv header)")
    rows, dropped = candidates(df, a.min_rating, a.min_reviews, not a.include_desserts)
    print(f"{len(rows):,} candidates after filtering  (dropped: {dict(dropped)})")
    chosen, per_slot, tagged = pick(rows, targets, a.special)
    print(f"picked {len(chosen)}: {dict(per_slot)}, {tagged} with a dietary tag")
    want = sum(targets.values()) + a.special
    if len(chosen) < want:
        print(f"warning: {want - len(chosen)} short of {want}. Lower --min-reviews or --min-rating.")
    if a.dry_run:
        for slot in targets:
            print(f"\n{slot}")
            for r in [c for c in chosen if c["slot"] == slot][:6]:
                print(f"  {r['rating']} ({r['reviews']:>4} reviews) {r['name'][:48]:48} {r['category'][:16]:16} {r['tags']}")
        return
    with open(a.out, "w", encoding="utf-8") as f:
        emit(chosen, f)
    print(f"-> {a.out}")


if __name__ == "__main__":
    main()
