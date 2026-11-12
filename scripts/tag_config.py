"""Per-code configuration for scripts/tag_ingredients.py.

Everything a reviewer may want to change about WHEN an ingredient is proposed
for a code lives here, so a threshold is a one-line edit with a citation next
to it rather than an expression buried in a SQL string.

Nothing here is applied by itself. tag_ingredients.py reads it to PROPOSE tags;
a person decides. Every code ships with approved=False until someone with the
authority named in `approver` signs it off.

Two things are deliberately not invented here:

  * No threshold other than the two FDA definitions below. A code that needs a
    different cut-off has to say where it comes from.
  * No reference amount that has not been read from 21 CFR 101.12(b). A food
    with no clear class there is reported as "unjudgeable" and left untagged,
    not measured on a convenient basis.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# --------------------------------------------------------------------------
# FDA Daily Values, 21 CFR 101.9(c)(8)(iv), adults and children 4+.
# --------------------------------------------------------------------------
DAILY_VALUE = {
    "Vitamin_C": 90.0,     # mg
    "Vitamin_K": 120.0,    # mcg
    "Vitamin_D": 20.0,     # mcg
    "Vitamin_A": 900.0,    # mcg RAE
    "Calcium": 1300.0,     # mg
    "Iron": 18.0,          # mg
    "Zinc": 11.0,          # mg
    "Folate": 400.0,       # mcg
}

# --------------------------------------------------------------------------
# Claim levels, 21 CFR 101.54 (checked against eCFR). Both are defined PER
# REFERENCE AMOUNT CUSTOMARILY CONSUMED (21 CFR 101.12(b)), not per 100 g and
# not per whatever a household measure happens to be.
#   high    101.54(b)(1)  "high", "rich in", "excellent source of"  >= 20% DV
#   source  101.54(c)(1)  "good source", "contains", "provides"     10-19% DV
#           (a food at 20% or more also qualifies as a source)
# --------------------------------------------------------------------------
LEVELS = {
    "high": 0.20,
    "source": 0.10,
}

# A proposal this close to its line is sent for review rather than trusted:
# the reference amount is a class average and USDA values are rounded, so a
# food at 105% of the line is not meaningfully "over" it. NOT a regulatory
# number; it only decides tier 1 vs tier 2.
REVIEW_MARGIN = 1.25

# A fuzzy USDA match scoring under this is sent for review. NOT a regulatory
# number. Alias and manual matches are not scored this way.
WEAK_MATCH_SCORE = 90


@dataclass(frozen=True)
class CodeConfig:
    """How one nutrient-based code is decided."""
    nutrients: tuple[str, ...]
    level: str                       # key of LEVELS
    categories: tuple[str, ...] | None  # USDA food_category filter, None = any
    combine: str = "all"             # "all" or "any" across `nutrients`
    basis: str = "reference_amount"  # or "typical_serving" (the old behaviour)
    wording: str = ""                # what the rule itself says
    rules: str = ""
    note: str = ""
    approver: str = "nutrition expert + rule owner"
    approved: bool = False


PLANT = (
    "Vegetables and Vegetable Products", "Fruits and Fruit Juices",
    "Legumes and Legume Products", "Cereal Grains and Pasta",
    "Nut and Seed Products", "Breakfast Cereals",
)
PRODUCE = ("Vegetables and Vegetable Products", "Fruits and Fruit Juices")
DAIRY = ("Dairy and Egg Products",)

NUTRIENT_CODES: dict[str, CodeConfig] = {
    "NUT_VITC": CodeConfig(
        nutrients=("Vitamin_C",), level="high", categories=PRODUCE,
        wording='"vitamin C-rich produce"', rules="INH-006, SYN-001 (partner)",
        note='"rich" is the 20% definition. SYN-001/SYN-008 list tomato as a '
             'valid PARTNER, and tomato is ~13% DV per reference amount, so '
             'the partner role would need its own "source" code. Not done here.'),
    "NUT_VITK": CodeConfig(
        nutrients=("Vitamin_K",), level="high", categories=PRODUCE + ("Fats and Oils",),
        wording='"leafy greens or other vitamin K foods"', rules="SYN-005",
        note='"foods" does not say source or rich; 20% kept as the existing '
             'default. Dropping to "source" is a one-word change if the rule owner prefers.'),
    "NUT_VITD": CodeConfig(
        nutrients=("Vitamin_D",), level="source", categories=None,
        wording='"vitamin D-containing food"', rules="SYN-004",
        note='101.54(c)(1) lists "contains" under good source (10%).'),
    "NUT_CALCIUM": CodeConfig(
        nutrients=("Calcium",), level="high", categories=DAIRY,
        wording='"calcium-rich dairy or fortified alternative"', rules="SYN-010, INH-003",
        note='INH-003 is a do_not_automate calcium-SUPPLEMENT rule that shares '
             'this code, so it becomes a candidate on every dairy recipe. '
             'Needs a supplement fact before it should be reachable.'),
    "NUT_NONHEME_IRON": CodeConfig(
        nutrients=("Iron",), level="source", categories=PLANT,
        wording='"plant iron source"', rules="SYN-001, SYN-008",
        note='The rules say "source", not "rich", so 10%. Plant categories only, '
             'so heme iron is excluded by construction.'),
    "NUT_CAROTENOIDS": CodeConfig(
        nutrients=("Vitamin_A",), level="high", categories=PRODUCE,
        wording='"carotenoid-rich vegetables"', rules="SYN-002",
        note='Vitamin A (RAE) is a proxy for carotenoids; produce only.'),
    "NUT_PROVITAMIN_A": CodeConfig(
        nutrients=("Vitamin_A",), level="high", categories=PRODUCE,
        wording='"orange or dark-green vegetables"', rules="SYN-006",
        note='The rule names a colour class, not a threshold. Same proxy as NUT_CAROTENOIDS.'),
    "ING_VITC_FOLATE_VEG": CodeConfig(
        nutrients=("Vitamin_C", "Folate"), level="high", categories=("Vegetables and Vegetable Products",), combine="any",
        wording='BIO-015: "vitamin C/folate-rich vegetables"; instruction: "when vitamin C OR folate is the target"',
        rules="BIO-015",
        note='The previous behaviour required BOTH (combine="all"), which kept '
             'only avocado, parsley and peas, and allowed fruit. The rule text says "or" and '
             '"vegetables", so this is OR over vegetables. Rule owner to confirm.'),
}

# --------------------------------------------------------------------------
# The three kinds of evidence a tag can rest on. They are reviewed by different
# people, fail in different ways, and so are kept apart in every output.
#
#   identity          WHAT THE FOOD IS. The name (and the USDA food it maps to)
#                     puts it in a class: a legume, a grain, an allium. No
#                     measurement is involved, so the risk is a wrong name match.
#   nutrient          HOW MUCH OF A MEASURED NUTRIENT. A value from
#                     ingredient_nutrition at the FDA reference amount against a
#                     threshold. The risk is a wrong USDA record or a wrong basis.
#   curated_compound  A COMPOUND THE DATABASE DOES NOT MEASURE: phytate, oxalate,
#                     tannin (and later piperine, curcumin). Membership is food-
#                     science knowledge, asserted from a list. It cannot be
#                     derived from nutrient rows and must not be, so a citation
#                     is required before one reaches tier 1.
# --------------------------------------------------------------------------
IDENTITY = "identity"
NUTRIENT = "nutrient"
COMPOUND = "curated_compound"
CATEGORIES = (IDENTITY, NUTRIENT, COMPOUND)

CODE_CATEGORY: dict[str, str] = {
    "ING_LEGUME": IDENTITY, "ING_GRAIN_LEGUME": IDENTITY, "ING_GRAIN": IDENTITY,
    "ING_ALLIUM": IDENTITY, "ING_SEED": IDENTITY, "BEV_SSB": IDENTITY,
    "NUT_VITC": NUTRIENT, "NUT_VITK": NUTRIENT, "NUT_VITD": NUTRIENT, "NUT_CALCIUM": NUTRIENT,
    "NUT_NONHEME_IRON": NUTRIENT, "NUT_CAROTENOIDS": NUTRIENT, "NUT_PROVITAMIN_A": NUTRIENT,
    "ING_VITC_FOLATE_VEG": NUTRIENT,
    "CMP_PHYTATE": COMPOUND, "CMP_OXALATE": COMPOUND, "BEV_TEA_COFFEE": COMPOUND,  # tannin carrier
}

# Who signs each kind off. Informational; printed by the tagger.
CATEGORY_REVIEWER = {
    IDENTITY: "data owner (ingredient names and USDA matches)",
    NUTRIENT: "nutrition expert + rule owner (thresholds, basis, USDA values)",
    COMPOUND: "food-science domain expert (needs a citation per code)",
}

# A curated-compound code needs a source before any of its proposals can be
# tier 1. Map the code to a citation string when one exists. Nothing is invented
# here: an empty dict means every compound proposal is held at tier 2.
COMPOUND_SOURCES: dict[str, str] = {}


def category_of(code: str) -> str:
    """The evidence category for a code; raises for a code nobody classified."""
    try:
        return CODE_CATEGORY[code]
    except KeyError:
        raise KeyError("no evidence category for %s; add it to CODE_CATEGORY" % code) from None


# --------------------------------------------------------------------------
# Evidence that must not drive a nutrient proposal, by ingredient name.
# A name here is still listed in the export, as tier 3 with the reason, so the
# exclusion is visible. Remove an entry once the data is fixed.
# --------------------------------------------------------------------------
EVIDENCE_EXCLUDED: dict[str, str] = {
    "cheese": "'cheese' names no single USDA record; mapped to Swiss, low sodium (961 mg calcium/100 g). Needs a decision on which cheese. See migration 010.",
    "milk": "mapped to 'Milk, buttermilk, fluid, whole', a different dairy product. Verified correct ids: 171265 whole, 171267 2%, 170872 1%. See migration 010.",
    "1% low-fat milk": "mapped to buttermilk (see 'milk'). Correct id 170872.",
    "2% low-fat milk": "mapped to buttermilk (see 'milk'). Correct id 171267.",
    "nonfat milk": "mapped to buttermilk (see 'milk'). Nonfat id not verified.",
    "skim milk": "mapped to 'Milk, lowfat, 1% milkfat, with added nonfat milk solids'. Nonfat id not verified.",
    "evaporated milk": "mapped to buttermilk; evaporated milk is ~2x as concentrated. Id not verified.",
    "fat-free evaporated milk": "mapped to buttermilk; evaporated milk is ~2x as concentrated. Id not verified.",
    "unsweetened applesauce": "USDA record has added ascorbic acid, so its vitamin C is fortification.",
    "ground coriander": "mapped to 'Coriander (cilantro) leaves, raw'; the ground spice is coriander SEED, a different food. Correct id not verified.",
}

# --------------------------------------------------------------------------
# A single (code, ingredient) pair that must not be tagged, when the ingredient is
# fine for other codes. Shown in the export as tier 3 with the reason, like
# EVIDENCE_EXCLUDED. Remove an entry only when the review has confirmed the evidence.
# --------------------------------------------------------------------------
PAIR_EXCLUSIONS: dict[tuple[str, str], str] = {
    ("NUT_VITD", "buttermilk"):
        "vitamin D 1.3 mcg/100 g on USDA 'Milk, buttermilk, fluid, whole' (172225), the record already blocked "
        "for plain milk; the figure looks like fortification and the review has not confirmed that "
        "fortified vitamin D is acceptable for SYN-004.",
    ("NUT_VITD", "low-fat buttermilk"):
        "same USDA record and the same unconfirmed fortification as 'buttermilk' (and it is not a low-fat record).",
}

# --------------------------------------------------------------------------
# Reference amounts, 21 CFR 101.12(b), read from eCFR. First match wins.
#   name_rx   against lower(ingredient_name)
#   desc_rx   against lower(USDA source_description), or None
#   category  USDA food_category the row applies to, or None for any
#   grams     the reference amount; mL are taken as g (water-like foods)
#   label     the 101.12(b) product category it came from
# A row with grams=None says "this is deliberately unjudgeable" and stops the
# search, so a later broad row cannot catch it.
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Ref:
    name_rx: str | None
    desc_rx: str | None
    category: str | None
    grams: float | None
    label: str


VEG = "Vegetables and Vegetable Products"
FRUIT = "Fruits and Fruit Juices"
GRAIN = "Cereal Grains and Pasta"

REFERENCE_AMOUNTS: tuple[Ref, ...] = (
    # --- deliberately unjudgeable -------------------------------------------------
    Ref(r"garlic", None, None, None, "garlic: not named in 101.12(b); not a measured vegetable serving"),
    Ref(r"pie filling", None, None, None, "pie filling: a dessert filling, not the vegetable"),
    Ref(r"^(?!.*brussels).*sprout", None, None, None, "sprouts: 101.12(b) gives 1/4 cup with no gram weight (Brussels sprouts are ordinary vegetables)"),
    Ref(r"zest|rind|peel", None, None, None, "zest, rind and peel: not a class in 101.12(b)"),
    Ref(r"tahini|nut butter|peanut butter", None, None, None, "nut and seed butters: 2 tbsp, no gram weight"),
    # --- vegetables ---------------------------------------------------------------
    Ref(r"parsley|cilantro|basil", None, None, 4.0, "Vegetables primarily used for garnish or flavor (pimento, parsley, fresh or dried)"),
    Ref(r"^fresh coriander|chives?\b|pimento", None, VEG, 4.0, "Vegetables primarily used for garnish or flavor (pimento, parsley, fresh or dried)"),
    Ref(None, None, "Spices and Herbs", 0.5, "Spices, herbs (1/4 tsp or 0.5 g)"),
    Ref(r"\bpowder\b|\bground\b|\bflakes\b|seasoning", None, None, 0.5, "Spices, herbs (1/4 tsp or 0.5 g)"),
    Ref(r"olive", None, None, 15.0, "Olives (15 g)"),
    Ref(r"chil(i|ie|e)s?\b|jalapeno|green onion|scallion|spring onion", None, None, 30.0, "Fresh or canned chili peppers, hot peppers, green onion"),
    Ref(r"sun-dried|sun dried", None, None, 5.0, "Dried vegetables, dried tomatoes"),
    Ref(r"tomato paste", None, None, 30.0, "Vegetable pastes, e.g., tomato paste"),
    Ref(r"tomato puree|tomato sauce", None, None, 60.0, "Vegetable sauces or purees"),
    Ref(r"wasabi|horseradish", None, None, 5.0, "Minor condiments (1 tsp)"),
    Ref(r"hash brown", None, None, 70.0, "French fries, hash browns (70 g prepared)"),
    Ref(r"sweet potato|^potato", None, None, 110.0, "Potatoes and sweet potatoes, plain, fresh or frozen"),
    Ref(r"pumpkin|winter squash|butternut|acorn squash|spaghetti squash", None, VEG, 130.0, "canned or stewed tomatoes, pumpkin, winter squash (130 g)"),
    Ref(None, r"canned|stewed", VEG, 130.0, "vegetables canned in liquid (130 g)"),
    Ref(None, None, VEG, 85.0, "All other vegetables without sauce (85 g fresh or frozen)"),
    # --- fruits -------------------------------------------------------------------
    Ref(r"lemon juice|lime juice", None, None, 5.0, "Juices used as ingredients (5 mL)"),
    Ref(r"^(lemon|lime)s?\b|avocado", None, None, 50.0, "Fruits used primarily as ingredients: avocado, lemon, lime (50 g)"),
    Ref(None, r"dried", FRUIT, 40.0, "Fruits, dried (40 g)"),
    Ref(None, None, FRUIT, 140.0, "All other fruits, fresh, canned or frozen (140 g)"),
    # --- dairy --------------------------------------------------------------------
    Ref(r"parmesan|parmigiano|romano", None, "Dairy and Egg Products", 5.0, "Cheese, grated hard (5 g)"),
    Ref(r"cottage", None, "Dairy and Egg Products", 110.0, "Cheese, cottage (110 g)"),
    Ref(r"ricotta", None, "Dairy and Egg Products", 55.0, "Cheese used primarily as ingredients (55 g)"),
    Ref(r"cheese|feta|velveeta", None, "Dairy and Egg Products", 30.0, "Cheese, all others (30 g)"),
    Ref(r"yogurt", None, "Dairy and Egg Products", 170.0, "Yogurt (170 g)"),
    Ref(r"evaporated", None, "Dairy and Egg Products", 30.0, "Milk, evaporated, undiluted (30 mL)"),
    Ref(r"milk", None, "Dairy and Egg Products", 240.0, "Milk (240 mL)"),
    # --- legumes ------------------------------------------------------------------
    Ref(r"tofu|tempeh", None, None, 85.0, "Tofu, tempeh (85 g)"),
    Ref(r"soy sauce|tamari", None, None, 15.0, "Major condiments (1 tbsp)"),
    Ref(r"baked beans|chili beans|refried", None, "Legumes and Legume Products", 130.0, "Beans in sauce / canned in liquid (130 g)"),
    Ref(None, r"canned", "Legumes and Legume Products", 130.0, "Beans canned in liquid (130 g)"),
    Ref(None, r"cooked|boiled", "Legumes and Legume Products", 90.0, "Beans, others prepared (90 g)"),
    Ref(None, r"raw|dry|mature seeds", "Legumes and Legume Products", 35.0, "Beans, dry (35 g)"),
    # --- grains -------------------------------------------------------------------
    Ref(r"\bwheat germ\b|\bbran\b", None, GRAIN, 15.0, "Bran or wheat germ (15 g)"),
    Ref(r"flour|cornmeal|meal\b", None, GRAIN, 30.0, "Flours or cornmeal (30 g)"),
    Ref(r"pasta|macaroni|spaghetti|noodle|orzo|fettuccine|linguine|rotini|penne", r"cooked", GRAIN, 140.0, "Pastas, plain (140 g prepared)"),
    Ref(r"pasta|macaroni|spaghetti|noodle|orzo|fettuccine|linguine|rotini|penne", None, GRAIN, 55.0, "Pastas, plain (55 g dry)"),
    Ref(r"rice|sorghum|barley|quinoa|bulgur", r"cooked", GRAIN, 140.0, "Grains, e.g., rice, barley, plain (140 g prepared)"),
    Ref(r"rice|sorghum|barley|quinoa|bulgur", None, GRAIN, 45.0, "Grains, e.g., rice, barley, plain (45 g dry)"),
    # --- seeds, fish, fats ---------------------------------------------------------
    Ref(None, None, "Nut and Seed Products", 30.0, "Nuts, seeds and mixtures (30 g)"),
    Ref(None, r"\braw\b", "Finfish and Shellfish Products", 110.0, "Fish, plain, uncooked (110 g)"),
    Ref(None, None, "Finfish and Shellfish Products", 85.0, "Fish, plain, cooked (85 g)"),
    Ref(None, None, "Fats and Oils", 15.0, "Butter, margarine, oil (1 tbsp)"),
)


def reference_amount(name: str, category: str | None, description: str | None):
    """(grams, label) for this ingredient, or None when 101.12(b) gives no clear class.

    `description` is the USDA record the nutrient values came from. The state of
    THAT food (raw, cooked, canned) decides the amount, because the numbers
    describe it, not the recipe's wording.
    """
    low = (name or "").lower()
    desc = (description or "").lower()
    for ref in REFERENCE_AMOUNTS:
        if ref.category and ref.category != category:
            continue
        if ref.name_rx and not re.search(ref.name_rx, low):
            continue
        if ref.desc_rx and not re.search(ref.desc_rx, desc):
            continue
        if ref.grams is None:
            return None
        return ref.grams, ref.label
    return None
