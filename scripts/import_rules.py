#!/usr/bin/env python3
"""Import the approved recipe-optimization rules workbook into SQL seeds.

Reads  "IN WORK - MaziMeal Recipe Optimization Rules (1).xlsx"  and writes
deterministic, idempotent PostgreSQL seed files:

    schema/seed/business_rules.sql          business_rules UPSERTs (54 rules)
    schema/seed/rule_codes.sql              rule_codes UPSERTs (the vocabulary)
    schema/seed/ingredient_rule_tags.sql    confident ingredient -> code tags
    schema/seed/rule_codes_review.csv       codes whose metadata needs a human
    schema/seed/ingredient_rule_tags_review.csv  ambiguous ingredient matches

Like scripts/csv_to_sql.py it does NOT touch a database. It emits SQL you load
with psql after review:

    python3 scripts/import_rules.py
    psql -d mazimeal -v ON_ERROR_STOP=1 -f schema/seed/rule_codes.sql
    psql -d mazimeal -v ON_ERROR_STOP=1 -f schema/seed/business_rules.sql
    psql -d mazimeal -v ON_ERROR_STOP=1 -f schema/seed/ingredient_rule_tags.sql

All generated SQL is idempotent (ON CONFLICT DO UPDATE / DO NOTHING), so it is
safe to run more than once without duplicating rows.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import sys
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------
# Paths / constants
# --------------------------------------------------------------------------
REPO = Path(__file__).resolve().parent.parent
WORKBOOK = REPO / "IN WORK - MaziMeal Recipe Optimization Rules (1).xlsx"
SEED_DIR = REPO / "schema" / "seed"

# Sheet name -> rule_category stored in business_rules.
RULE_SHEETS = {
    "Bioavailability": "bioavailability",
    "Food Synergies": "food_synergy",
    "Inhibitors": "inhibitor",
    "Glycemic Behaviors": "glycemic",
}
HEADER_ROW = 2  # 0-based: title row, blank row, then the real header.

# Columns expected in each rule sheet (order preserved for output).
RULE_COLUMNS = [
    "rule_id", "rule_name", "rule_type",
    "trigger_food_or_pattern", "trigger_code",
    "target_nutrient_or_outcome", "target_code",
    "action", "action_code",
    "mechanism", "recipe_engine_instruction",
    "conditions_and_limits", "population_scope",
    "evidence_tier", "evidence_summary", "automation_status",
    "source_title", "source_type", "source_url", "review_date",
]
# business_rules column order for INSERT (adds rule_category + is_active).
BR_INSERT_COLUMNS = (
    ["rule_id", "rule_name", "rule_category", "rule_type"]
    + RULE_COLUMNS[3:]
    + ["is_active"]
)

VALID_AUTOMATION = {"recipe_safe", "conditional", "instruction_only", "do_not_automate"}
VALID_TIER = {"A", "B", "C"}

# Human-readable labels for known code-type prefixes (display only; the code
# families are discovered from the data, this only prettifies code_type).
CODE_TYPE_LABELS = {
    "ING": "ingredient / ingredient group",
    "NUT": "nutrient",
    "CMP": "compound",
    "MACRO": "macronutrient / dietary pattern",
    "PROC": "cooking / processing method",
    "PAIR": "food pairing",
    "BEV": "beverage",
    "SEP": "separation guidance",
    "SUB": "ingredient substitution",
    "MITIGATE": "mitigation step",
    "BEH": "behaviour",
    "OUT": "outcome / objective",
    "CARB": "carbohydrate pattern",
    "ADD": "additive step",
    "AVOID": "avoidance step",
    "CALC": "calculation",
    "CHECK": "engine check",
    "FLAG": "clinical flag",
    "MEAL": "meal pattern",
    "MED": "medication interaction",
    "PORTION": "portion guidance",
    "RULE": "rule-engine concept",
    "SAFETY": "safety override",
    "SEQ": "eating sequence",
}

# --------------------------------------------------------------------------
# Confident ingredient-name -> rule_code mapping.
#
# Only exact-ish matches we are confident about. Each entry lists substrings
# that qualify an ingredient and substrings that disqualify it (false
# positives seen in the real seed data: "corn syrup", "garlic powder",
# "eggplant", "peanut butter", "spaghetti squash", ...). Anything a keyword
# touches but an exclusion rejects is routed to the review CSV instead of
# being tagged.
# --------------------------------------------------------------------------
INGREDIENT_CODE_MAP = {
    "ING_GARLIC":    {"include": ["garlic"],
                      "exclude": ["powder", "salt", "sauce", "ginger sauce"]},
    "ING_TOMATO":    {"include": ["tomato"],
                      "exclude": ["broth"]},
    "ING_MUSHROOM":  {"include": ["mushroom"], "exclude": []},
    "ING_TURMERIC":  {"include": ["turmeric"], "exclude": []},
    "ING_CARROT":    {"include": ["carrot"], "exclude": []},
    "ING_CORN":      {"include": ["corn", "cornmeal"],
                      "exclude": ["syrup", "starch", "corned", "tortilla", "chips", "popcorn"]},
    "ING_EGG":       {"include": ["egg", "eggs"],
                      "exclude": ["eggplant", "reggiano", "substitute", "nog"]},
    "ING_PASTA":     {"include": ["pasta", "spaghetti", "macaroni", "penne",
                                  "fettuccine", "linguine", "orzo", "rotini", "noodle"],
                      "exclude": ["squash"]},
    "ING_YOGURT":    {"include": ["yogurt", "yoghurt"], "exclude": []},
    "ING_CRUCIFER":  {"include": ["broccoli", "cauliflower", "cabbage",
                                  "brussels sprout", "kale", "collard",
                                  "bok choy", "watercress", "arugula"],
                      "exclude": []},
    "ING_LEAFY_GREEN": {"include": ["spinach", "kale", "collard", "swiss chard",
                                    "lettuce", "arugula", "watercress"],
                        "exclude": []},
}

# --------------------------------------------------------------------------
# SQL helpers
# --------------------------------------------------------------------------
def sql_str(value) -> str:
    """Quote a value for SQL, mapping blanks / NaN / NaT to NULL."""
    if value is None:
        return "NULL"
    if isinstance(value, float) and pd.isna(value):
        return "NULL"
    if value is pd.NaT:
        return "NULL"
    s = str(value).strip()
    if s == "" or s.lower() in ("nan", "nat", "none"):
        return "NULL"
    return "'" + s.replace("'", "''") + "'"


def norm_date(value) -> str:
    """Normalize a workbook date to a SQL DATE literal or NULL."""
    if value is None or value is pd.NaT:
        return "NULL"
    if isinstance(value, float) and pd.isna(value):
        return "NULL"
    if isinstance(value, (dt.datetime, dt.date, pd.Timestamp)):
        return "'" + pd.Timestamp(value).date().isoformat() + "'"
    s = str(value).strip()
    if s == "" or s.lower() in ("nan", "nat", "none"):
        return "NULL"
    try:
        return "'" + pd.to_datetime(s).date().isoformat() + "'"
    except Exception:
        return "NULL"


def blank_to_none(value):
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    s = str(value).strip()
    if s == "" or s.lower() in ("nan", "nat", "none"):
        return None
    return s


def humanize_code(code: str) -> str:
    """Derive a display name from a code, e.g. ING_GARLIC -> 'Garlic'."""
    parts = code.split("_")
    body = parts[1:] if len(parts) > 1 else parts
    return " ".join(w.capitalize() for w in body) if body else code


# --------------------------------------------------------------------------
# Reading / validation
# --------------------------------------------------------------------------
def read_rules(workbook: Path):
    """Return (rules_df, problems). rules_df has one row per usable rule."""
    problems = []
    frames = []
    with pd.ExcelFile(workbook, engine="openpyxl") as xl:
        sheet_names = xl.sheet_names
        parsed = {}
        for sheet in RULE_SHEETS:
            if sheet in sheet_names:
                parsed[sheet] = xl.parse(sheet_name=sheet, header=HEADER_ROW)
    for sheet, category in RULE_SHEETS.items():
        if sheet not in sheet_names:
            problems.append(f"missing expected sheet: {sheet!r}")
            continue
        df = parsed[sheet].dropna(how="all")
        got = list(df.columns)[: len(RULE_COLUMNS)]
        if got != RULE_COLUMNS:
            problems.append(
                f"{sheet}: unexpected columns.\n  expected {RULE_COLUMNS}\n  got      {got}"
            )
            continue
        df = df[RULE_COLUMNS].copy()
        df = df[df["rule_id"].notna() & (df["rule_id"].astype(str).str.strip() != "")]
        df["rule_category"] = category
        df["_sheet"] = sheet
        frames.append(df)

    if not frames:
        return pd.DataFrame(), problems

    rules = pd.concat(frames, ignore_index=True)

    # Duplicate rule_ids across every sheet.
    dupes = rules["rule_id"][rules["rule_id"].duplicated(keep=False)]
    for rid in sorted(set(dupes)):
        where = ", ".join(rules.loc[rules["rule_id"] == rid, "_sheet"])
        problems.append(f"duplicate rule_id {rid} in: {where}")

    # Required / enumerated field checks per row.
    for _, row in rules.iterrows():
        rid = str(row["rule_id"]).strip()
        if blank_to_none(row["rule_name"]) is None:
            problems.append(f"{rid}: missing rule_name")
        if blank_to_none(row["trigger_code"]) is None:
            problems.append(f"{rid}: missing trigger_code")
        if blank_to_none(row["action_code"]) is None and blank_to_none(row["action"]) is None:
            problems.append(f"{rid}: missing both action and action_code")
        auto = blank_to_none(row["automation_status"])
        if auto is not None and auto not in VALID_AUTOMATION:
            problems.append(f"{rid}: automation_status {auto!r} not in {sorted(VALID_AUTOMATION)}")
        tier = blank_to_none(row["evidence_tier"])
        if tier is not None and tier not in VALID_TIER:
            problems.append(f"{rid}: evidence_tier {tier!r} not in {sorted(VALID_TIER)}")

    return rules, problems


def collect_codes(rules: pd.DataFrame):
    """Return {code: code_type} for every code used across the rule sheets."""
    codes = {}
    for col in ("trigger_code", "target_code", "action_code"):
        for value in rules[col].dropna():
            code = str(value).strip()
            if not code or code.lower() == "nan":
                continue
            codes[code] = code.split("_")[0]
    return dict(sorted(codes.items()))


# --------------------------------------------------------------------------
# Ingredient name -> code matching
# --------------------------------------------------------------------------
def load_ingredient_names(seed_dir: Path):
    """Pull distinct ingredient names from the existing seed data."""
    names = set()
    foodcom = seed_dir / "foodcom_400.sql"
    if foodcom.exists():
        pat = re.compile(r"INSERT INTO ingredients \(ingredient_name.*?VALUES \('(.*?)'", re.I)
        for line in foodcom.read_text().splitlines():
            m = pat.match(line)
            if m:
                names.add(m.group(1).replace("''", "'").strip())
    ri = seed_dir / "recipe_ingredients.csv"
    if ri.exists():
        with ri.open() as f:
            for row in csv.DictReader(f):
                n = (row.get("ingredient_name") or "").strip()
                if n:
                    names.add(n)
    return sorted(names)


def match_ingredients(names, valid_codes):
    """Split ingredient names into confident tags and review candidates.

    Returns (confident, review) where
      confident = sorted list of (ingredient_name, code)
      review    = sorted list of (ingredient_name, code, reason)
    """
    confident, review = [], []
    for name in names:
        low = name.lower()
        for code, rule in INGREDIENT_CODE_MAP.items():
            if code not in valid_codes:
                continue
            inc = any(kw in low for kw in rule["include"])
            if not inc:
                continue
            exc = next((kw for kw in rule["exclude"] if kw in low), None)
            if exc:
                review.append((name, code, f"keyword matched but excluded by {exc!r}"))
            else:
                confident.append((name, code))
    return sorted(set(confident)), sorted(set(review))


# --------------------------------------------------------------------------
# SQL writers
# --------------------------------------------------------------------------
def write_business_rules(rules: pd.DataFrame, out: Path):
    lines = [
        "-- schema/seed/business_rules.sql",
        "-- GENERATED by scripts/import_rules.py. Do not edit by hand.",
        "-- Idempotent: ON CONFLICT (rule_id) DO UPDATE. Safe to run repeatedly.",
        "",
        "BEGIN;",
        "",
    ]
    cols = ", ".join(BR_INSERT_COLUMNS)
    update_cols = [c for c in BR_INSERT_COLUMNS if c != "rule_id"]
    for _, row in rules.sort_values("rule_id").iterrows():
        values = []
        for c in BR_INSERT_COLUMNS:
            if c == "is_active":
                values.append("TRUE")
            elif c == "review_date":
                values.append(norm_date(row[c]))
            else:
                values.append(sql_str(row[c]))
        set_clause = ",\n        ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
        lines.append(f"INSERT INTO business_rules ({cols})")
        lines.append("VALUES (" + ", ".join(values) + ")")
        lines.append("ON CONFLICT (rule_id) DO UPDATE SET")
        lines.append(f"        {set_clause},")
        lines.append("        updated_at = now();")
        lines.append("")
    lines.append("COMMIT;")
    out.write_text("\n".join(lines) + "\n")


def write_rule_codes(codes: dict, out: Path, review_out: Path):
    lines = [
        "-- schema/seed/rule_codes.sql",
        "-- GENERATED by scripts/import_rules.py. Do not edit by hand.",
        "-- Codebook sheet was empty, so display_name/description are derived and",
        "-- flagged needs_review = TRUE. Idempotent ON CONFLICT (code) DO UPDATE.",
        "",
        "BEGIN;",
        "",
    ]
    review_rows = []
    for code, ctype in codes.items():
        display = humanize_code(code)
        type_label = CODE_TYPE_LABELS.get(ctype, ctype)
        lines.append(
            "INSERT INTO rule_codes (code, code_type, display_name, description, needs_review)"
        )
        lines.append(
            f"VALUES ({sql_str(code)}, {sql_str(ctype)}, {sql_str(display)}, "
            f"{sql_str(type_label + ' (auto-derived; confirm meaning)')}, TRUE)"
        )
        lines.append("ON CONFLICT (code) DO UPDATE SET")
        lines.append("        code_type = EXCLUDED.code_type;")
        # Note: we keep an existing human-edited display_name/description on
        # re-run by only updating code_type.
        lines.append("")
        review_rows.append((code, ctype, display))
    lines.append("COMMIT;")
    out.write_text("\n".join(lines) + "\n")

    with review_out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["code", "code_type", "auto_display_name", "needs_human_description"])
        for code, ctype, display in review_rows:
            w.writerow([code, ctype, display, "yes"])


def write_ingredient_tags(confident, review, out: Path, review_out: Path):
    lines = [
        "-- schema/seed/ingredient_rule_tags.sql",
        "-- GENERATED by scripts/import_rules.py. Do not edit by hand.",
        "-- Ingredients are seeded by NAME (no fixed UUIDs), so each tag resolves",
        "-- the ingredient_id via a case-insensitive name lookup matching the",
        "-- uq_ingredients_name_lower index. Missing ingredient => 0 rows, no error.",
        "-- Idempotent ON CONFLICT (ingredient_id, rule_code) DO NOTHING.",
        "",
        "BEGIN;",
        "",
    ]
    for name, code in confident:
        lines.append("INSERT INTO ingredient_rule_tags (ingredient_id, rule_code)")
        lines.append("SELECT i.ingredient_id, " + sql_str(code))
        lines.append("FROM ingredients i")
        lines.append(f"WHERE lower(btrim(i.ingredient_name)) = lower(btrim({sql_str(name)}))")
        lines.append("ON CONFLICT (ingredient_id, rule_code) DO NOTHING;")
        lines.append("")
    lines.append("COMMIT;")
    out.write_text("\n".join(lines) + "\n")

    with review_out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ingredient_name", "candidate_code", "reason"])
        for name, code, reason in review:
            w.writerow([name, code, reason])


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workbook", type=Path, default=WORKBOOK)
    ap.add_argument("--seed-dir", type=Path, default=SEED_DIR)
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if any validation problem is found")
    args = ap.parse_args(argv)

    if not args.workbook.exists():
        print(f"workbook not found: {args.workbook}", file=sys.stderr)
        return 2
    args.seed_dir.mkdir(parents=True, exist_ok=True)

    rules, problems = read_rules(args.workbook)
    if rules.empty:
        print("no usable rules found", file=sys.stderr)
        for p in problems:
            print("  -", p, file=sys.stderr)
        return 2

    codes = collect_codes(rules)
    names = load_ingredient_names(args.seed_dir)
    confident, review = match_ingredients(names, set(codes))

    write_business_rules(rules, args.seed_dir / "business_rules.sql")
    write_rule_codes(codes, args.seed_dir / "rule_codes.sql",
                     args.seed_dir / "rule_codes_review.csv")
    write_ingredient_tags(confident, review,
                          args.seed_dir / "ingredient_rule_tags.sql",
                          args.seed_dir / "ingredient_rule_tags_review.csv")

    # Report
    by_cat = rules["rule_category"].value_counts().to_dict()
    print("Rules imported by category:")
    for cat in ("bioavailability", "food_synergy", "inhibitor", "glycemic"):
        print(f"  {cat:<16} {by_cat.get(cat, 0)}")
    print(f"  {'TOTAL':<16} {len(rules)}")
    print(f"\nUnique rule codes: {len(codes)} (all flagged needs_review)")
    print(f"Confident ingredient tags: {len(confident)}")
    print(f"Ingredient matches needing review: {len(review)}")
    print("\nSeed files written to", args.seed_dir)

    if problems:
        print(f"\n{len(problems)} validation note(s):", file=sys.stderr)
        for p in problems:
            print("  -", p, file=sys.stderr)
        if args.strict:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
