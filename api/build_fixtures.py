#!/usr/bin/env python3
"""
Build the fixture files the backend serves while the other workstreams are
still in progress.

    python3 api/build_fixtures.py

Real values (per-serving nutrition, ingredient names, step text, Maya's iron
target) come from the development database and are exported to TSV first; see
the header of each fixture for what is real and what is invented. Everything
invented is marked so nobody mistakes a placeholder for a measurement.
"""
import csv, json, pathlib, sys

SRC = pathlib.Path("/private/tmp/claude-501/-Users-caliber-platform/979a7ae1-05ce-435e-80aa-b2a8d4aca69c/scratchpad")
OUT = pathlib.Path(__file__).resolve().parent / "fixtures"
OUT.mkdir(exist_ok=True)

SLUG = {
    "Falafel": "falafel-001",
    "Souvlaki": "souvlaki-002",
    "Rachael Ray's Super Scrumptious Sloppy Joes": "sloppy-joes-003",
    "Kittencal's Tuna Salad Sandwiches": "tuna-salad-004",
    "Fresh Tomato Spaghetti Sauce": "tomato-spaghetti-005",
}
NICE = {
    "Falafel": "Falafel with Herbed Cucumber Yogurt",
    "Souvlaki": "Chicken Souvlaki",
    "Rachael Ray's Super Scrumptious Sloppy Joes": "Sloppy Joes",
    "Kittencal's Tuna Salad Sandwiches": "Tuna Salad Sandwiches",
    "Fresh Tomato Spaghetti Sauce": "Fresh Tomato Spaghetti Sauce",
}
LABEL = {
    "Energy": ("Calories", "kcal"), "Macro_Protein": ("Protein", "g"),
    "Macro_Fat": ("Fat", "g"), "Macro_Carbohydrate": ("Carbohydrates", "g"),
    "Fiber": ("Fiber", "g"), "Sodium": ("Sodium", "mg"), "Iron": ("Iron", "mg"),
    "Vitamin_C": ("Vitamin C", "mg"), "Calcium": ("Calcium", "mg"),
    "Zinc": ("Zinc", "mg"), "Folate": ("Folate", "mcg"),
}
ORDER = ["Energy", "Macro_Protein", "Macro_Carbohydrate", "Macro_Fat", "Fiber",
         "Sodium", "Iron", "Vitamin_C", "Calcium", "Zinc", "Folate"]

# Maya's daily targets, from profile_nutrient_targets in the database.
MAYA_TARGET = {"Iron": 27.0, "Energy": 2000.0, "Macro_Protein": 48.0,
               "Vitamin_C": 75.0, "Calcium": 1000.0, "Sodium": 2300.0}


def rows(name):
    path = SRC / name
    if not path.exists():
        sys.exit(f"missing {path}; run the psql export first")
    with path.open() as fh:
        return [r for r in csv.reader(fh, delimiter="\t") if r]


# ---------------------------------------------------------------- source data
ing, steps, nut, meta = {}, {}, {}, {}
for r in rows("ing.tsv"):
    ing.setdefault(r[0], []).append(
        {"line_id": int(r[1]), "name": r[2], "quantity": float(r[3]),
         "unit": r[4], "typical_g": float(r[5])})
for r in rows("steps.tsv"):
    steps.setdefault(r[0], []).append({"step_number": int(r[1]), "instruction": r[2]})
for r in rows("nut.tsv"):
    nut.setdefault(r[0], {})[r[1]] = {"value": float(r[2]), "unit": r[3], "source": r[4]}
for r in rows("meta.tsv"):
    meta[r[0]] = {"servings": int(r[1]), "time_min": int(r[2]),
                  "tags": [t for t in r[3].split(",") if t], "kcal": float(r[4])}

# ------------------------------------------------- invented, and marked as such
# Gram weights are placeholders until the data workstream delivers conversions.
GRAMS = {
    "garlic": 6.0, "scallions": 30.0, "fresh cilantro": 4.0, "of fresh mint": 2.0,
    "chickpeas": 246.0, "baking powder": 4.6, "ground cumin": 2.1, "sea salt": 6.0,
    "Tabasco sauce": 4.7, "Olive oil": 27.0, "lettuce": 36.0, "chopped tomato": 90.0,
    "onion": 55.0, "plain low-fat yogurt": 170.0, "fresh lemon juice": 15.0,
    "kirby cucumber": 52.0, "pepper": 2.3,
}
OPTIONAL = {"Tabasco sauce", "pepper", "sea salt"}
UNIT = {  # readable units for the cook screen; the dataset has none
    "garlic": "cloves", "scallions": "stalks", "fresh cilantro": "tbsp",
    "of fresh mint": "tbsp", "chickpeas": "cup", "baking powder": "tsp",
    "ground cumin": "tsp", "sea salt": "tsp", "Tabasco sauce": "tsp",
    "Olive oil": "tbsp", "lettuce": "cups", "chopped tomato": "medium",
    "onion": "small", "plain low-fat yogurt": "cup", "fresh lemon juice": "tbsp",
    "kirby cucumber": "whole", "pepper": "tsp",
}
STEP_TITLE = {  # the step-enrichment workstream will produce these for real
    1: ("Make the cucumber yogurt", 5, "mix"),
    2: ("Blend the herbs and garlic", 2, "blend"),
    3: ("Add the chickpeas and spices", 3, "blend"),
    4: ("Shape four patties", 5, "shape"),
    5: ("Spray the patties", 1, "prep"),
    6: ("Heat the olive oil", 3, "heat"),
    7: ("Fry until golden", 8, "fry"),
    8: ("Drain the patties", 1, "rest"),
    9: ("Fill the pita", 3, "assemble"),
    10: ("Serve with the yogurt", 1, "serve"),
}

# Rules below are real rows from "IN WORK - MaziMeal Recipe Optimization Rules.xlsx".
# The rule ids, evidence tiers, automation statuses and sources are the client's;
# what the rules workstream will add is which recipe they hit and where.
FALAFEL_RULES = [
    {"rule_id": "SYN-001", "target_nutrient": "iron absorption", "target_code": "NUT_IRON", "name": "Vitamin C with nonheme iron", "status": "satisfied",
     "automation_status": "recipe_safe", "evidence_tier": "A",
     "applies_to": {"type": "ingredients", "line_ids": [5, 12, 15]},
     "engine_action": "Keep the lemon juice and tomato in the same meal as the chickpeas.",
     "why": "Vitamin C reduces ferric iron to the form the gut absorbs, so the chickpeas give up more iron.",
     "source_url": "https://ods.od.nih.gov/factsheets/Iron-HealthProfessional/"},
    {"rule_id": "BIO-002", "target_nutrient": "allicin formation", "target_code": "CMP_ALLICIN", "name": "Crush garlic and rest before heating", "status": "not_satisfied",
     "automation_status": "recipe_safe", "evidence_tier": "B",
     "applies_to": {"type": "step", "step_number": 2},
     "engine_action": "Crush the garlic, then let it rest about 10 minutes before it meets heat.",
     "why": "Resting lets alliinase convert alliin to allicin; heating too early stops the reaction.",
     "source_url": "https://pubmed.ncbi.nlm.nih.gov/11160543/"},
    {"rule_id": "INH-002", "target_nutrient": "iron and zinc absorption", "target_code": "NUT_IRON_ZINC", "name": "High-phytate matrix with iron and zinc", "status": "not_satisfied",
     "automation_status": "recipe_safe", "evidence_tier": "A",
     "applies_to": {"type": "ingredients", "line_ids": [5]},
     "engine_action": "Soak dried chickpeas overnight, or rinse canned ones well, to cut phytate.",
     "why": "Phytate binds iron and zinc and keeps them from being absorbed.",
     "source_url": "https://ods.od.nih.gov/factsheets/Iron-HealthProfessional/"},
    {"rule_id": "INH-001", "target_nutrient": "nonheme iron absorption", "target_code": "NUT_IRON", "name": "Tea or coffee with a nonheme iron meal", "status": "advisory",
     "automation_status": "instruction_only", "evidence_tier": "A",
     "applies_to": {"type": "meal"},
     "engine_action": "Keep tea and coffee away from this meal; have them an hour either side.",
     "why": "Polyphenols bind nonheme iron and measurably reduce how much is absorbed.",
     "source_url": "https://pubmed.ncbi.nlm.nih.gov/6402915/"},
    {"rule_id": "INH-003", "target_nutrient": "iron absorption", "target_code": "NUT_IRON", "name": "Calcium next to iron", "status": "needs_review",
     "automation_status": "do_not_automate", "evidence_tier": "B",
     "applies_to": {"type": "ingredients", "line_ids": [14]},
     "engine_action": "Flagged for a reviewer. The yogurt sauce stays: the rule forbids stripping calcium from a balanced meal.",
     "why": "Calcium can reduce iron absorption in single meals, but the long-term evidence is mixed.",
     "source_url": "https://ods.od.nih.gov/factsheets/Calcium-HealthProfessional/"},
]

# Which ingredient lines carry a nutrient. The data workstream computes these
# from gram weights times USDA values; until then they are placeholders.
TOP_SOURCES = {
    "Iron": [(5, "chickpeas", 3.4, 57), (2, "scallions", 0.9, 15), (12, "chopped tomato", 0.6, 10)],
    "Vitamin_C": [(15, "fresh lemon juice", 52.0, 43), (12, "chopped tomato", 38.0, 32), (2, "scallions", 14.0, 12)],
    "Calcium": [(14, "plain low-fat yogurt", 310.0, 57), (5, "chickpeas", 95.0, 18)],
    "Macro_Protein": [(5, "chickpeas", 9.6, 57), (14, "plain low-fat yogurt", 4.2, 25)],
}

NOTE = ("Fixture data. Nutrition values, ingredient names and step text come from the "
        "development database; gram weights, units, step titles and durations are "
        "placeholders until the data and step workstreams deliver.")


def detail(name):
    m, slug = meta[name], SLUG[name]
    is_falafel = name == "Falafel"
    out = {
        "_fixture_note": NOTE,
        "recipe_id": slug, "name": NICE[name], "meal": "Lunch",
        "servings": m["servings"], "time_min": m["time_min"],
        "tags": m["tags"] or ["weeknight"], "image_url": None,
        "ingredients": [], "nutrition_per_serving": [], "steps": [],
        "matched_rules": FALAFEL_RULES if is_falafel else [],
        "source": "fixture",
    }
    for line in ing.get(name, []):
        grams = GRAMS.get(line["name"]) if is_falafel else None
        out["ingredients"].append({
            "line_id": line["line_id"],
            "name": line["name"],
            "quantity": line["quantity"],
            "unit": UNIT.get(line["name"], line["unit"]) if is_falafel else line["unit"],
            "grams": grams,
            "grams_source": "placeholder" if grams else None,
            "is_optional": line["name"] in OPTIONAL if is_falafel else False,
            "required_by_rule": "SYN-001" if (is_falafel and line["line_id"] in (5, 15)) else None,
            "notes": None,
        })
    for key in ORDER:
        v = nut.get(name, {}).get(key)
        if not v:
            continue
        target = MAYA_TARGET.get(key)
        pct = round(100 * v["value"] / target) if target else None
        sources = TOP_SOURCES.get(key, []) if is_falafel else []
        out["nutrition_per_serving"].append({
            "nutrient": key, "label": LABEL[key][0], "value": v["value"],
            "unit": v["unit"], "source": v["source"],
            "confidence": 1.0 if v["source"] == "published" else 0.6,
            "pct_of_target": pct,
            "top_sources": [
                {"line_id": lid, "name": name, "value": val, "unit": v["unit"],
                 "pct_of_recipe": share, "estimated": True}
                for lid, name, val, share in sources
            ],
        })
    for st in steps.get(name, []):
        title, dur, tech = STEP_TITLE.get(st["step_number"], (None, None, None)) if is_falafel else (None, None, None)
        out["steps"].append({
            "step_number": st["step_number"],
            "title": title,
            "instruction": st["instruction"],
            "duration_min": dur,
            "is_key_step": bool(is_falafel and st["step_number"] == 2),
            "ingredient_line_ids": [1, 2, 3, 4] if (is_falafel and st["step_number"] == 2) else [],
            "technique": tech,
        })
    return out


# ---------------------------------------------------------------- recipe files
for name in SLUG:
    d = detail(name)
    (OUT / f"recipe_{d['recipe_id']}.json").write_text(json.dumps(d, indent=2) + "\n")

# ---------------------------------------------------------------- household
household = {
    "_fixture_note": NOTE + " Today's consumed totals are invented.",
    "household_id": "demo-household", "name": "Demo Household", "date": "2026-10-19",
    "members": [
        {"member_id": "maya", "name": "Maya", "age": 31, "sex": "F",
         "conditions": ["iron_deficiency"],
         "preferences": {"allergies": ["peanut"], "dislikes": ["mushroom"],
                         "dietary_patterns": [], "cuisines": ["Mediterranean", "South Asian"]},
         "targets": [
             {"nutrient": "Iron", "label": "Iron", "unit": "mg", "target": 27.0,
              "baseline": 18.0, "consumed": 3.1, "remaining": 23.9, "upper_limit": 45.0,
              "adjusted_by": ["IRON_COND_ANY_C002_001"],
              "adjusted_reason": "iron deficiency"},
             {"nutrient": "Energy", "label": "Calories", "unit": "kcal", "target": 2000.0,
              "baseline": 2000.0, "consumed": 520.0, "remaining": 1480.0,
              "upper_limit": None, "adjusted_by": []},
             {"nutrient": "Macro_Protein", "label": "Protein", "unit": "g", "target": 48.0,
              "baseline": 48.0, "consumed": 18.0, "remaining": 30.0,
              "upper_limit": None, "adjusted_by": []},
             {"nutrient": "Vitamin_C", "label": "Vitamin C", "unit": "mg", "target": 75.0,
              "baseline": 75.0, "consumed": 22.0, "remaining": 53.0,
              "upper_limit": 2000.0, "adjusted_by": []},
         ]},
        {"member_id": "jeff", "name": "Jeff", "age": 28, "sex": "M",
         "conditions": [],
         "preferences": {"allergies": ["peanut"], "dislikes": [],
                         "dietary_patterns": [], "cuisines": ["American"]},
         "targets": [
             {"nutrient": "Iron", "label": "Iron", "unit": "mg", "target": 8.0,
              "baseline": 8.0, "consumed": 2.4, "remaining": 5.6, "upper_limit": 45.0,
              "adjusted_by": []},
             {"nutrient": "Energy", "label": "Calories", "unit": "kcal", "target": 2600.0,
              "baseline": 2600.0, "consumed": 780.0, "remaining": 1820.0,
              "upper_limit": None, "adjusted_by": []},
             {"nutrient": "Macro_Protein", "label": "Protein", "unit": "g", "target": 116.0,
              "baseline": None, "consumed": 32.0, "remaining": 84.0, "upper_limit": None,
              "adjusted_by": ["PROT_ACT_ANY_VERYACTIVE_001", "PROT_GOAL_ANY_MUSCLE_001"],
              "adjusted_reason": "very active, building muscle"},
         ]},
    ],
}
(OUT / "household.json").write_text(json.dumps(household, indent=2) + "\n")

# ---------------------------------------------------------------- recommendations
REMAINING_IRON = 23.9


def rec(name, score, rule_ids, why):
    iron = nut[name]["Iron"]["value"]
    m = meta[name]
    return {
        "recipe_id": SLUG[name], "name": NICE[name], "meal": "Lunch",
        "kcal_per_serving": m["kcal"], "time_min": m["time_min"],
        "tags": m["tags"] or ["weeknight"], "score": score,
        "nutrient_contribution": {
            "nutrient": "Iron", "per_serving": iron, "unit": "mg",
            "pct_of_remaining_need": round(100 * iron / REMAINING_IRON),
            "source": nut[name]["Iron"]["source"],
            "confidence": 1.0 if nut[name]["Iron"]["source"] == "published" else 0.6,
        },
        "matched_rule_ids": rule_ids,
        "why": why,
        "blocked_by": None,
    }


recommendations = {
    "_fixture_note": NOTE + " Scores are illustrative: they assume the iron weighting the recommender does not do yet.",
    "member_id": "maya", "meal": "Lunch", "target_nutrient": "Iron",
    "date": "2026-10-19", "generated_at": "2026-10-19T12:30:00Z", "source": "fixture",
    "results": [
        rec("Souvlaki", 91.2, ["SYN-002"],
            "Most iron of the lunches that fit her day, and it is already a Mediterranean dish she likes."),
        rec("Falafel", 89.6, [r["rule_id"] for r in FALAFEL_RULES],
            "Pairs plant iron with vitamin C already, and one preparation change would raise what she absorbs."),
        rec("Rachael Ray's Super Scrumptious Sloppy Joes", 88.0, ["SYN-001"],
            "Beef iron plus tomato; heavier on sodium than the rest."),
        rec("Kittencal's Tuna Salad Sandwiches", 86.4, ["INH-003"],
            "Ten minutes start to finish, with iron close to the others."),
        rec("Fresh Tomato Spaghetti Sauce", 79.5, ["SYN-001", "BIO-003"],
            "Good iron, but a two-hour sauce on a Tuesday lunch."),
    ],
    "blocked": [
        {"recipe_id": "peanut-bacon-006", "name": "Peanut Butter and Bacon Sandwich",
         "meal": "Lunch", "kcal_per_serving": 319.0, "time_min": 10, "tags": [],
         "score": None, "nutrient_contribution": None, "matched_rule_ids": [],
         "why": None,
         "blocked_by": {"reason": "household allergen", "detail": "peanut butter"}},
        {"recipe_id": "baked-trout-007", "name": "Baked Trout with Garlic & Mushrooms",
         "meal": "Lunch", "kcal_per_serving": 825.8, "time_min": 32, "tags": ["high_protein"],
         "score": None, "nutrient_contribution": None, "matched_rule_ids": [],
         "why": None,
         "blocked_by": {"reason": "disliked ingredient", "detail": "mushroom"}},
    ],
}
(OUT / "recommendations_maya_lunch.json").write_text(json.dumps(recommendations, indent=2) + "\n")

# ---------------------------------------------------------------- AI suggestions
# A deployed build has no model and no backend, so it serves whatever a
# reviewer last approved. Fall back to the hand-written stub only when nothing
# has been reviewed yet.
APPROVED = pathlib.Path(__file__).resolve().parent / "content" / "falafel-001.json"
reviewed = None
if APPROVED.exists():
    entry = json.loads(APPROVED.read_text())
    if entry.get("status") == "approved":
        reviewed = entry

suggestions = {
    "_fixture_note": "Stub text, written by hand. No model call. Replaced when the LLM endpoint is wired.",
    "recipe_id": "falafel-001", "member_id": "maya", "source": "stub",
    "disclaimer": "Generated from matched rules. Nutrition figures come from the database, not the model.",
    "suggestions": [
        {"rule_id": "BIO-002", "headline": "Let the garlic rest before it hits the oil",
         "body": "Crush the garlic first and leave it on the board for ten minutes while you shape the patties. "
                 "Nothing else about the recipe changes.",
         "evidence_tier": "B", "source_url": "https://pubmed.ncbi.nlm.nih.gov/11160543/"},
        {"rule_id": "SYN-001", "headline": "The lemon is doing more than seasoning",
         "body": "Lemon juice and tomato sit in the same meal as the chickpeas, which is what helps you absorb "
                 "the iron in them. Keep them in.",
         "evidence_tier": "A", "source_url": "https://ods.od.nih.gov/factsheets/Iron-HealthProfessional/"},
        {"rule_id": "INH-001", "headline": "Save the tea for later",
         "body": "Tea and coffee alongside this meal bind some of the iron. An hour either side is enough.",
         "evidence_tier": "A", "source_url": "https://pubmed.ncbi.nlm.nih.gov/6402915/"},
    ],
}
if reviewed:
    suggestions = {
        "_fixture_note": (
            "Approved text, copied from api/content at build time. Written by "
            f"{reviewed.get('model') or 'the rules themselves'} and approved by "
            f"{reviewed.get('reviewed_by')}."
        ),
        "recipe_id": "falafel-001",
        "member_id": "maya",
        "source": "reviewed",
        "model": reviewed.get("model"),
        "reviewed_by": reviewed.get("reviewed_by"),
        "summary": reviewed.get("summary"),
        "disclaimer": (
            "Written from the matched rules and approved by a reviewer. Nutrition "
            "figures come from the database, not from a model."
        ),
        "suggestions": reviewed["suggestions"],
    }

(OUT / "suggestions_falafel-001.json").write_text(json.dumps(suggestions, indent=2) + "\n")

# The frontend bundles the same fixtures so it runs with no backend at all.
WEB = pathlib.Path(__file__).resolve().parent.parent / "web" / "src" / "shared" / "fixtures"
WEB.mkdir(parents=True, exist_ok=True)
for p in sorted(OUT.glob("*.json")):
    (WEB / p.name).write_text(p.read_text())

for p in sorted(OUT.glob("*.json")):
    print(f"{p.name:40} {p.stat().st_size:>7,} bytes")
print(f"copied {len(list(OUT.glob('*.json')))} fixtures into {WEB.relative_to(WEB.parent.parent.parent.parent)}")
