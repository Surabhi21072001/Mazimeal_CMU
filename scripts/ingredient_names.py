#!/usr/bin/env python3
"""
Print every ingredient name in the seed files, one per line, for match_usda.py.

    python3 scripts/ingredient_names.py > /tmp/names.txt
"""
import re, sys

FILES = ["schema/seed/foodcom_400.sql", "recommender/seed/00_reference.sql", "recommender/seed/01_demo_household.sql"]

names = set()
for f in FILES:
    try:
        text = open(f, encoding="utf-8").read()
    except FileNotFoundError:
        print(f"skipping {f}", file=sys.stderr)
        continue
    # foodcom: INSERT INTO ingredients (ingredient_name, ...) VALUES ('name', ...
    names.update(m.group(1) for m in re.finditer(r"INSERT INTO ingredients \(ingredient_name[^)]*\) VALUES \('((?:[^']|'')*)'", text))
    # demo seeds: ('0193...uuid', 171477, 'Chicken breast, cooked', ...
    names.update(m.group(1) for m in re.finditer(r"\('01930000-0000-7000-8000-0000000000\w\w', \d+, '((?:[^']|'')*)'", text))

for n in sorted(names, key=str.lower):
    print(n.replace("''", "'"))
