#!/usr/bin/env python3
"""
Writes the profile_nutrient_baselines rows for 00_reference.sql.

Values: Dietary Reference Intakes, National Academies (RDA where one exists,
otherwise AI), as summarised in the NIH DRI tables:
  https://www.ncbi.nlm.nih.gov/books/NBK545442/
Energy: Dietary Guidelines for Americans 2020-2025, Appendix 2, moderately
active, midpoint of the band.
Sodium upper limit: CDRR (National Academies 2019).
Saturated fat upper limit: under 10% of energy (DGA), converted to grams.

Our 19-50 band takes the larger of the 19-30 and 31-50 values.
Infants (C001-C004) are left out on purpose: infant feeding is not something
the recommender should touch.

    python3 seed/gen_dri.py > /tmp/dri.sql
"""

SRC = "https://www.ncbi.nlm.nih.gov/books/NBK545442/"
SRC_E = "https://www.dietaryguidelines.gov/sites/default/files/2020-12/Dietary_Guidelines_for_Americans_2020-2025.pdf"

# category -> (age band, sex)
CATS = {
    "C005": ("1-3", "F"), "C006": ("1-3", "M"),
    "C007": ("4-8", "F"), "C008": ("4-8", "M"),
    "C009": ("9-13", "F"), "C010": ("9-13", "M"),
    "C011": ("14-18", "F"), "C012": ("14-18", "M"),
    "C013": ("19-50", "F"), "C014": ("19-50", "M"),
    "C015": ("51-70", "F"), "C016": ("51-70", "M"),
    "C017": ("70+", "F"), "C018": ("70+", "M"),
}
BANDS = ["1-3", "4-8", "9-13", "14-18", "19-50", "51-70", "70+"]

# nutrient -> unit, {band: (F, M)}  (single number when same for both)
RDA = {
    "Energy": ("kcal", {"1-3": 1200, "4-8": (1500, 1600), "9-13": (1800, 2000), "14-18": (2000, 2600),
                        "19-50": (2000, 2600), "51-70": (1800, 2300), "70+": (1800, 2200)}),
    "Macro_Protein": ("g/kg/day", {"1-3": 1.05, "4-8": 0.95, "9-13": 0.95, "14-18": 0.85,
                                   "19-50": 0.80, "51-70": 0.80, "70+": 0.80}),
    "Macro_Carbohydrate": ("g", {b: 130 for b in BANDS}),
    "Fiber": ("g", {"1-3": 19, "4-8": 25, "9-13": (26, 31), "14-18": (26, 38),
                    "19-50": (25, 38), "51-70": (21, 30), "70+": (21, 30)}),
    "Calcium": ("mg", {"1-3": 700, "4-8": 1000, "9-13": 1300, "14-18": 1300,
                       "19-50": 1000, "51-70": (1200, 1000), "70+": 1200}),
    "Iron": ("mg", {"1-3": 7, "4-8": 10, "9-13": 8, "14-18": (15, 11),
                    "19-50": (18, 8), "51-70": 8, "70+": 8}),
    "Magnesium": ("mg", {"1-3": 80, "4-8": 130, "9-13": 240, "14-18": (360, 410),
                         "19-50": (320, 420), "51-70": (320, 420), "70+": (320, 420)}),
    "Phosphorus": ("mg", {"1-3": 460, "4-8": 500, "9-13": 1250, "14-18": 1250,
                          "19-50": 700, "51-70": 700, "70+": 700}),
    "Potassium": ("mg", {"1-3": 2000, "4-8": 2300, "9-13": (2300, 2500), "14-18": (2300, 3000),
                         "19-50": (2600, 3400), "51-70": (2600, 3400), "70+": (2600, 3400)}),
    "Zinc": ("mg", {"1-3": 3, "4-8": 5, "9-13": 8, "14-18": (9, 11),
                    "19-50": (8, 11), "51-70": (8, 11), "70+": (8, 11)}),
    "Copper": ("mg", {"1-3": 0.34, "4-8": 0.44, "9-13": 0.7, "14-18": 0.89,
                      "19-50": 0.9, "51-70": 0.9, "70+": 0.9}),
    "Selenium": ("mcg", {"1-3": 20, "4-8": 30, "9-13": 40, "14-18": 55,
                         "19-50": 55, "51-70": 55, "70+": 55}),
    "Vitamin_A": ("mcg", {"1-3": 300, "4-8": 400, "9-13": 600, "14-18": (700, 900),
                          "19-50": (700, 900), "51-70": (700, 900), "70+": (700, 900)}),
    "Vitamin_D": ("mcg", {"1-3": 15, "4-8": 15, "9-13": 15, "14-18": 15,
                          "19-50": 15, "51-70": 15, "70+": 20}),
    "Vitamin_E": ("mg", {"1-3": 6, "4-8": 7, "9-13": 11, "14-18": 15,
                         "19-50": 15, "51-70": 15, "70+": 15}),
    "Vitamin_K": ("mcg", {"1-3": 30, "4-8": 55, "9-13": 60, "14-18": 75,
                          "19-50": (90, 120), "51-70": (90, 120), "70+": (90, 120)}),
    "Vitamin_C": ("mg", {"1-3": 15, "4-8": 25, "9-13": 45, "14-18": (65, 75),
                         "19-50": (75, 90), "51-70": (75, 90), "70+": (75, 90)}),
    "Thiamin": ("mg", {"1-3": 0.5, "4-8": 0.6, "9-13": 0.9, "14-18": (1.0, 1.2),
                       "19-50": (1.1, 1.2), "51-70": (1.1, 1.2), "70+": (1.1, 1.2)}),
    "Riboflavin": ("mg", {"1-3": 0.5, "4-8": 0.6, "9-13": 0.9, "14-18": (1.0, 1.3),
                          "19-50": (1.1, 1.3), "51-70": (1.1, 1.3), "70+": (1.1, 1.3)}),
    "Niacin": ("mg", {"1-3": 6, "4-8": 8, "9-13": 12, "14-18": (14, 16),
                      "19-50": (14, 16), "51-70": (14, 16), "70+": (14, 16)}),
    "Vitamin_B6": ("mg", {"1-3": 0.5, "4-8": 0.6, "9-13": 1.0, "14-18": (1.2, 1.3),
                          "19-50": 1.3, "51-70": (1.5, 1.7), "70+": (1.5, 1.7)}),
    "Folate": ("mcg", {"1-3": 150, "4-8": 200, "9-13": 300, "14-18": 400,
                       "19-50": 400, "51-70": 400, "70+": 400}),
    "Vitamin_B12": ("mcg", {"1-3": 0.9, "4-8": 1.2, "9-13": 1.8, "14-18": 2.4,
                            "19-50": 2.4, "51-70": 2.4, "70+": 2.4}),
    # limit-only nutrients: target 0, upper limit below
    "Sodium": ("mg", {b: 0 for b in BANDS}),
    "Saturated_Fat": ("g", {b: 0 for b in BANDS}),
    "Sugar": ("g", {b: 0 for b in BANDS}),
    "Cholesterol": ("mg", {b: 0 for b in BANDS}),
}

# Tolerable Upper Intake Levels per day. None = not established.
UL = {
    "Calcium":    {"1-3": 2500, "4-8": 2500, "9-13": 3000, "14-18": 3000, "19-50": 2500, "51-70": 2000, "70+": 2000},
    "Iron":       {"1-3": 40, "4-8": 40, "9-13": 40, "14-18": 45, "19-50": 45, "51-70": 45, "70+": 45},
    "Phosphorus": {"1-3": 3000, "4-8": 3000, "9-13": 4000, "14-18": 4000, "19-50": 4000, "51-70": 4000, "70+": 3000},
    "Zinc":       {"1-3": 7, "4-8": 12, "9-13": 23, "14-18": 34, "19-50": 40, "51-70": 40, "70+": 40},
    "Copper":     {"1-3": 1, "4-8": 3, "9-13": 5, "14-18": 8, "19-50": 10, "51-70": 10, "70+": 10},
    "Selenium":   {"1-3": 90, "4-8": 150, "9-13": 280, "14-18": 400, "19-50": 400, "51-70": 400, "70+": 400},
    "Vitamin_A":  {"1-3": 600, "4-8": 900, "9-13": 1700, "14-18": 2800, "19-50": 3000, "51-70": 3000, "70+": 3000},
    "Vitamin_D":  {"1-3": 63, "4-8": 75, "9-13": 100, "14-18": 100, "19-50": 100, "51-70": 100, "70+": 100},
    "Vitamin_E":  {"1-3": 200, "4-8": 300, "9-13": 600, "14-18": 800, "19-50": 1000, "51-70": 1000, "70+": 1000},
    "Vitamin_C":  {"1-3": 400, "4-8": 650, "9-13": 1200, "14-18": 1800, "19-50": 2000, "51-70": 2000, "70+": 2000},
    "Niacin":     {"1-3": 10, "4-8": 15, "9-13": 20, "14-18": 30, "19-50": 35, "51-70": 35, "70+": 35},
    "Vitamin_B6": {"1-3": 30, "4-8": 40, "9-13": 60, "14-18": 80, "19-50": 100, "51-70": 100, "70+": 100},
    "Folate":     {"1-3": 300, "4-8": 400, "9-13": 600, "14-18": 800, "19-50": 1000, "51-70": 1000, "70+": 1000},
    # sodium: CDRR, "reduce intake if above"
    "Sodium":     {"1-3": 1200, "4-8": 1500, "9-13": 1800, "14-18": 2300, "19-50": 2300, "51-70": 2300, "70+": 2300},
}
# Magnesium UL applies to supplements only, so none here. Sugar and
# cholesterol have no DRI limit; the added-sugar guidance needs added sugar,
# which the recipe data doesn't separate from total.


def pick(v, sex):
    return v[0 if sex == "F" else 1] if isinstance(v, tuple) else v


def fmt(x):
    return "NULL" if x is None else (str(int(x)) if float(x).is_integer() else str(x))


rows = []
for cat, (band, sex) in CATS.items():
    energy = pick(RDA["Energy"][1][band], sex)
    for nid, (unit, byband) in RDA.items():
        val = pick(byband[band], sex)
        ul = UL.get(nid, {}).get(band)
        if nid == "Saturated_Fat":
            ul = round(energy * 0.10 / 9)
        src = SRC_E if nid == "Energy" else SRC
        rows.append(f"    ('{cat}', {nid!r}, {fmt(val)}, {unit!r}, 'Day', {fmt(ul)}, '{src}')")

print("INSERT INTO public.profile_nutrient_baselines")
print("    (category_id, nutrient_id, baseline_value, unit, per, upper_threshold_day, source_url) VALUES")
print(",\n".join(rows))
print("ON CONFLICT (category_id, nutrient_id) DO UPDATE SET")
print("    baseline_value = EXCLUDED.baseline_value, unit = EXCLUDED.unit,")
print("    upper_threshold_day = EXCLUDED.upper_threshold_day, source_url = EXCLUDED.source_url;")
