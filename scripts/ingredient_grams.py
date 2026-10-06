#!/usr/bin/env python3
"""
Household measures and gram estimates for ingredient lines.

    python3 scripts/ingredient_grams.py <sr_legacy_folder> [--parquet recipes.parquet] \
        --review schema/seed/ingredient_measures.csv -o schema/seed/ingredient_grams.sql

The Food.com dataset gives a bare number per ingredient and no unit, so
"2 olive oil" could be 2 tablespoons or 2 cups. This script:

  1. loads every household measure USDA SR Legacy publishes for the matched
     food (food_portion.csv: "cup" 125 g, "large" 50 g, "clove" 3 g) into
     ingredient_measures,
  2. picks a default measure per ingredient by rule (spices tsp, oils tbsp,
     flour and liquids cup, eggs and produce each, meat lb), falling back to a
     constant when USDA has no weight for it,
  3. sets recipe_ingredients.quantity_g = quantity x grams for that measure,
     tagged with how it was arrived at (grams_source),
  4. with --parquet, marks each recipe's lines as aligned or not: in most
     Food.com recipes the quantity list is longer than the ingredient list,
     so the number next to an ingredient may belong to a different one.

Review the CSV. The measure choice is a heuristic; fix the odd ones in
OVERRIDES below and rerun. Idempotent SQL.
"""
import argparse, csv, os, re, sys
from collections import defaultdict

# measure -> (USDA modifier keywords to look for, in order; fallback grams per 1)
MEASURES = {
    "tsp":   (["tsp", "teaspoon"], 5),
    "tbsp":  (["tbsp", "tablespoon"], 15),
    "cup":   (["cup"], 200),      # see CUP_FALLBACK
    "each":  (["medium", "large", "whole", "each", "item", "unit", "half breast", "breast", "piece", "fruit",
               "fillet", "steak", "chop", "link", "thigh", "stalk", "head", "tortilla", "bulb", "small"], 100),
    "clove": (["clove"], 3),
    "slice": (["slice"], 28),
    "lb":    (["lb"], 453.6),
    "oz":    (["oz"], 28.35),
    "can":   (["can"], 400),
}

# which USDA size to read first for 'each', when the usual order is wrong
EACH_PREFER = {"egg": ["large"]}

# a cup of what: fallback grams by USDA category when USDA has no cup weight
CUP_FALLBACK = {
    "Dairy and Egg Products": 120, "Cereal Grains and Pasta": 150, "Snacks": 90, "Beverages": 240,
    "Vegetables and Vegetable Products": 130, "Fruits and Fruit Juices": 150, "Legumes and Legume Products": 180,
    "Nut and Seed Products": 120, "Sweets": 170, "Soups, Sauces, and Gravies": 240, "Baked Products": 100,
}

# ingredient name -> measure, checked before any rule
OVERRIDES = {
    "garlic": "clove", "garlic clove": "clove", "garlic cloves": "clove",
    "cornstarch": "tbsp", "cream cheese": "oz", "tomato paste": "tbsp",
    "bacon": "slice", "bread": "slice", "celery": "each", "green onion": "each", "green onions": "each",
    "scallion": "each", "scallions": "each", "jalapeno": "each", "shallot": "each",
    "green beans": "cup", "fresh green beans": "cup", "lemon": "each", "lime": "each",
}

# (substring in name, measure). First hit wins. Longer, more specific words first.
NAME_RULES = [
    ("tuna", "can"), ("canned", "can"), ("diced tomatoes", "can"), ("crushed tomatoes", "can"),
    ("stewed tomatoes", "can"), ("tomato sauce", "can"), ("coconut milk", "can"), ("beans", "can"),
    ("pepper flakes", "tsp"), ("flakes", "tsp"),
    ("bell pepper", "each"), ("red pepper", "each"), ("green pepper", "each"),
    ("chicken breast", "each"), ("chicken thigh", "each"), ("pork chop", "each"), ("fillet", "each"),
    ("ground beef", "lb"), ("ground turkey", "lb"), ("ground pork", "lb"), ("ground chicken", "lb"),
    ("baking powder", "tsp"), ("baking soda", "tsp"), ("extract", "tsp"), ("yeast", "tsp"),
    ("cream of tartar", "tsp"), ("seasoning", "tsp"), ("spice", "tsp"), ("salt", "tsp"),
    ("black pepper", "tsp"), ("white pepper", "tsp"), ("cayenne", "tsp"), ("chili powder", "tsp"),
    ("cinnamon", "tsp"), ("nutmeg", "tsp"), ("cumin", "tsp"), ("paprika", "tsp"), ("oregano", "tsp"),
    ("thyme", "tsp"), ("curry", "tsp"), ("turmeric", "tsp"), ("ginger", "tsp"), ("dill", "tsp"),
    ("rosemary", "tsp"), ("sage", "tsp"), ("cloves", "tsp"), ("allspice", "tsp"), ("vanilla", "tsp"),
    ("tahini", "tbsp"),
    ("soy sauce", "tbsp"), ("sauce", "tbsp"), ("vinegar", "tbsp"), ("mustard", "tbsp"), ("ketchup", "tbsp"),
    ("mayonnaise", "tbsp"), ("honey", "tbsp"), ("syrup", "tbsp"), ("lemon juice", "tbsp"), ("lime juice", "tbsp"),
    ("peanut butter", "tbsp"), ("oil", "tbsp"), ("butter", "tbsp"), ("margarine", "tbsp"), ("shortening", "tbsp"),
    ("egg", "each"), ("onion", "each"), ("tomato", "each"), ("potato", "each"), ("carrot", "each"),
    ("apple", "each"), ("banana", "each"), ("lemon", "each"), ("lime", "each"), ("orange", "each"),
    ("avocado", "each"), ("zucchini", "each"), ("cucumber", "each"), ("tortilla", "each"), ("pita", "each"),
    ("sausage", "lb"), ("shrimp", "lb"), ("beef", "lb"), ("pork", "lb"), ("lamb", "lb"), ("steak", "lb"),
    ("salmon", "lb"), ("cod", "lb"),
]

# USDA food category -> measure, when no name rule matched
CATEGORY_RULES = {
    "Spices and Herbs": "tsp",
    "Fats and Oils": "tbsp",
    "Beef Products": "lb", "Pork Products": "lb", "Lamb, Veal, and Game Products": "lb",
    "Poultry Products": "lb", "Finfish and Shellfish Products": "lb", "Sausages and Luncheon Meats": "lb",
    "Baked Products": "slice",
}
DEFAULT_MEASURE = "cup"


def q(v):
    return "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"


def load_usda(folder):
    cat = {r["id"]: r["description"] for r in csv.DictReader(open(os.path.join(folder, "food_category.csv"), encoding="utf-8"))}
    food = {}
    for r in csv.DictReader(open(os.path.join(folder, "food.csv"), encoding="utf-8")):
        food[r["fdc_id"]] = (r["description"], cat.get(r["food_category_id"], ""))
    portions = defaultdict(list)
    for r in csv.DictReader(open(os.path.join(folder, "food_portion.csv"), encoding="utf-8")):
        try:
            amount = float(r["amount"] or 1) or 1
            grams = float(r["gram_weight"])
        except ValueError:
            continue
        portions[r["fdc_id"]].append((float(r["seq_num"] or 99), r["modifier"].strip(), grams / amount, r["id"]))
    for v in portions.values():
        v.sort()
    return food, portions


def pick_measure(name, category):
    n = name.lower().strip()
    if n in OVERRIDES:
        return OVERRIDES[n]
    for key, m in NAME_RULES:
        if key in n:
            return m
    return CATEGORY_RULES.get(category, DEFAULT_MEASURE)


SYNONYMS = {"tablespoon": "tbsp", "tablespoons": "tbsp", "teaspoon": "tsp", "teaspoons": "tsp",
            "cloves": "clove", "slices": "slice", "pieces": "each", "fruit": "each"}


def usda_measure_key(modifier):
    """'cup, chopped' -> 'cup'; 'tablespoon' -> 'tbsp'; 'medium (2-1/2" dia)' -> 'medium'."""
    m = modifier.lower()
    m = re.split(r"[,(]", m)[0].strip()
    return SYNONYMS.get(m, m)


def grams_for(measure, plist, category="", name=""):
    """(grams per 1 measure, usda portion id or None, usda modifier or '')"""
    keys, fallback = MEASURES[measure]
    if measure == "each":
        for word, first in EACH_PREFER.items():
            if word in name.lower() and "eggplant" not in name.lower():
                keys = first + keys
    if measure == "cup":
        fallback = CUP_FALLBACK.get(category, fallback)
    for key in keys:
        for _, modifier, g, pid in plist:
            head = usda_measure_key(modifier)
            if head == key or head.startswith(key + " ") or head.startswith(key + "s"):
                return g, pid, modifier
    return fallback, None, ""


def alignment(parquet, ext_ids):
    import pyarrow.parquet as pq
    t = pq.read_table(parquet, columns=["RecipeId", "RecipeIngredientQuantities", "RecipeIngredientParts"]).to_pandas()
    t = t[t.RecipeId.isin({int(x) for x in ext_ids})]
    out = {}
    for rid, qs, ps in zip(t.RecipeId, t.RecipeIngredientQuantities, t.RecipeIngredientParts):
        nq = len(qs) if qs is not None else 0
        np_ = len(ps) if ps is not None else 0
        out[str(int(rid))] = nq == np_
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("folder")
    p.add_argument("--matches", default="schema/seed/usda_matches.csv")
    p.add_argument("--parquet", help="Food.com recipes.parquet, to flag misaligned quantity lists")
    p.add_argument("--seed", default="schema/seed/foodcom_400.sql", help="where the imported recipe ids come from")
    p.add_argument("--review", default="schema/seed/ingredient_measures.csv")
    p.add_argument("-o", "--out", default="schema/seed/ingredient_grams.sql")
    a = p.parse_args()

    food, portions = load_usda(a.folder)
    matches = [r for r in csv.DictReader(open(a.matches, encoding="utf-8")) if r["ok"] == "True"]

    review, measures = [], []
    for r in matches:
        name, fdc = r["name"], r["fdc_id"]
        desc, category = food.get(fdc, ("", ""))
        plist = portions.get(fdc, [])
        measure = pick_measure(name, category)
        g, pid, modifier = grams_for(measure, plist, category, name)
        review.append(dict(name=name, category=category, usda=desc, measure=measure, grams=round(g, 2),
                           basis="usda" if pid else "fallback", usda_modifier=modifier))
        # the default measure under its own name first, then every other USDA measure
        measures.append((name, measure, round(g, 2), pid))
        seen = {measure}
        for _, mod, grams, portion_id in plist:
            key = usda_measure_key(mod)[:40]
            if not key or key in seen:
                continue
            seen.add(key)
            measures.append((name, key, round(grams, 2), portion_id))

    with open(a.review, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=["name", "category", "usda", "measure", "grams", "basis", "usda_modifier"])
        wr.writeheader()
        wr.writerows(sorted(review, key=lambda r: (r["basis"], r["measure"], r["name"])))
    fb = sum(1 for r in review if r["basis"] == "fallback")
    print(f"{len(review)} ingredients, {len(review) - fb} with a USDA weight for the default measure, {fb} on fallback constants")
    print(f"-> {a.review}")

    aligned = {}
    if a.parquet:
        ext_ids = sorted(set(re.findall(r"external_source_id = '(\d+)'", open(a.seed, encoding="utf-8").read())))
        aligned = alignment(a.parquet, ext_ids)
        ok = sum(aligned.values())
        print(f"{len(aligned)} recipes checked, {ok} with matching quantity and ingredient lists, {len(aligned) - ok} misaligned")

    with open(a.out, "w", encoding="utf-8") as f:
        w = f.write
        w("-- Generated by scripts/ingredient_grams.py. Safe to run more than once.\nBEGIN;\n\n")
        w("-- household measures USDA publishes for each matched food\n")
        for name, key, grams, portion_id in measures:
            src = "'usda_sr_legacy'" if portion_id else "'mazi_estimate'"
            w(f"INSERT INTO ingredient_measures (ingredient_id, measure, gram_weight, source_id, source_portion_id) "
              f"SELECT ingredient_id, {q(key)}, {grams}, {src}, {portion_id or 'NULL'} FROM ingredients "
              f"WHERE lower(btrim(ingredient_name)) = {q(name.lower().strip())} "
              f"ON CONFLICT (ingredient_id, measure) DO UPDATE SET gram_weight = EXCLUDED.gram_weight, "
              f"source_id = EXCLUDED.source_id, source_portion_id = EXCLUDED.source_portion_id;\n")
        w("\n-- default measure per ingredient\n")
        for r in review:
            w(f"UPDATE ingredients SET default_measure = {q(r['measure'])} "
              f"WHERE lower(btrim(ingredient_name)) = {q(r['name'].lower().strip())};\n")
        w("""
-- grams per line. Imported lines carry a bare number ('unit') or nothing
-- ('portion', assumed 1); both use the ingredient's default measure.
UPDATE recipe_ingredients ri
SET    measure      = i.default_measure,
       quantity_g   = round(ri.quantity * m.gram_weight, 2),
       grams_source = CASE ri.unit WHEN 'portion' THEN 'assumed' ELSE 'measure' END
FROM   ingredients i
JOIN   ingredient_measures m ON m.ingredient_id = i.ingredient_id AND m.measure = i.default_measure
WHERE  ri.ingredient_id = i.ingredient_id
AND    ri.unit IN ('unit', 'portion')
AND    ri.grams_source <> 'manual';

-- lines that already have a real unit (demo recipes): g, cup, tbsp, whole.
-- fn_line_grams is the recommender schema's; the week-1 schema has no such
-- lines. Units it can't convert stay NULL.
DO $$ BEGIN
    IF to_regproc('fn_line_grams') IS NOT NULL THEN
        UPDATE recipe_ingredients ri
        SET    measure      = lower(ri.unit),
               quantity_g   = round(fn_line_grams(ri.quantity, ri.unit, i.typical_serving_g), 2),
               grams_source = 'measure'
        FROM   ingredients i
        WHERE  ri.ingredient_id = i.ingredient_id
        AND    ri.unit NOT IN ('unit', 'portion')
        AND    ri.grams_source <> 'manual'
        AND    fn_line_grams(ri.quantity, ri.unit, i.typical_serving_g) > 0;
    END IF;
END $$;
""")
        if aligned:
            w("\n-- whether the source quantity list lined up with the ingredient list\n")
            for flag in (True, False):
                ids = [k for k, v in aligned.items() if v is flag]
                for i in range(0, len(ids), 200):
                    chunk = ", ".join(q(x) for x in ids[i:i + 200])
                    w(f"UPDATE recipe_ingredients ri SET quantity_aligned = {str(flag).upper()} "
                      f"FROM recipes r WHERE r.recipe_id = ri.recipe_id AND r.external_source_id IN ({chunk});\n")
        w("\nCOMMIT;\n\nDO $$ BEGIN IF to_regproc('fn_refresh_recipe_nutrients') IS NOT NULL THEN PERFORM fn_refresh_recipe_nutrients(); END IF; END $$;\n")
    print(f"-> {a.out}")


if __name__ == "__main__":
    main()
