#!/usr/bin/env python3
"""Recipe nutrition as rule-triggering facts: GLY-002, 003, 004, 009, 011 and INH-011.

What the data is
----------------
recipe_nutrition holds Food.com's PUBLISHED nutrition PER SERVING (schema/05_recipe_nutrition.sql),
nine nutrients for each of the 400 seed recipes, in g (macros, fibre, sugar, saturated fat),
kcal (energy) and mg (sodium, cholesterol). Nothing is per 100 g and nothing is per recipe.
Values are still normalised EXPLICITLY here, so a different basis can never be compared with a
per-serving threshold by accident.

Where thresholds come from
--------------------------
Only from the rule's own wording or an existing reviewed configuration. There is no numeric
definition anywhere in the repository of 'carbohydrate-dominant', 'carbohydrate-rich' or a
'high-carbohydrate serving', and the rule_codes for them are all flagged needs_review. So
NUTRITION_RULE_CONFIG holds exactly two kinds of entry:

  review_status 'wording'     the rule's words ARE the threshold:
                                'carbohydrate-containing meal'  -> carbohydrate > 0 g
                                'fat-free meal'                 -> fat <= 0 g
  review_status 'unreviewed'  the rule's words are NOT a number. threshold is None and the
                              rule returns NEEDS_CONTEXT, naming the missing definition.
                              A human fills `threshold` and sets review_status 'reviewed';
                              no code change is needed.

CANDIDATE detection and FINAL applicability are separate: the trigger criterion only decides
whether the rule is called (is there carbohydrate at all?); the applicability criterion decides
whether the recommendation is warranted (is the meal carbohydrate-DOMINANT?).
"""
from __future__ import annotations

import operator as _op
from dataclasses import dataclass

from derived_facts import DerivedFact

OPERATORS = {">": _op.gt, ">=": _op.ge, "<": _op.lt, "<=": _op.le, "==": _op.eq}

# Atwater general factors (kcal per g). Used ONLY to express macronutrient energy shares, which
# stay informational until a reviewer sets a threshold on them.
ATWATER_KCAL_PER_G = {"Macro_Carbohydrate": 4.0, "Macro_Protein": 4.0, "Macro_Fat": 9.0}

# Unit conversions the normaliser will perform. Anything else is refused, never guessed.
UNIT_FACTORS = {("g", "g"): 1.0, ("mg", "g"): 0.001, ("mcg", "g"): 0.000001, ("kg", "g"): 1000.0,
                ("kcal", "kcal"): 1.0, ("mg", "mg"): 1.0, ("g", "mg"): 1000.0}

# Verdicts of the nutrition plausibility review (migration 003) that mean "do not rely on it".
UNVERIFIED_VERDICTS = frozenset({"implausible", "needs_data"})
# If True a recipe nobody has reviewed is also unusable. False: only an adverse verdict blocks,
# and an unreviewed recipe is used with that fact recorded in the evidence. See the report for
# why this is an open decision (no recipe has a review yet).
REQUIRE_PLAUSIBILITY_REVIEW = False


@dataclass(frozen=True)
class NutritionCriterion:
    """One threshold on one (possibly computed) per-serving quantity."""
    key: str
    field: str              # native nutrient id, or a computed field (COMPUTED_FIELDS)
    operator: str
    threshold: float | None
    unit: str               # unit of `field` ('g', 'kcal', 'fraction')
    basis: str              # 'per_serving'
    review_status: str      # 'wording' | 'reviewed' | 'unreviewed'
    source: str             # rule id and the words this comes from
    reason: str = ""

    def usable(self) -> bool:
        return self.threshold is not None and self.review_status in ("wording", "reviewed")

    def as_dict(self) -> dict:
        return {"key": self.key, "field": self.field, "operator": self.operator,
                "threshold": self.threshold, "unit": self.unit, "basis": self.basis,
                "review_status": self.review_status, "source": self.source, "reason": self.reason}


# ---- candidate detection: which trigger code does the recipe's nutrition establish? -------
NUTRITION_RULE_CONFIG: dict[str, NutritionCriterion] = {
    "MACRO_CARB": NutritionCriterion(
        key="carbohydrate_present", field="Macro_Carbohydrate", operator=">", threshold=0.0, unit="g",
        basis="per_serving", review_status="wording",
        source="GLY-002 trigger_food_or_pattern: 'carbohydrate-containing meal'",
        reason="a meal that contains carbohydrate has more than 0 g"),
    "MACRO_FAT_LOW": NutritionCriterion(
        key="fat_free", field="Macro_Fat", operator="<=", threshold=0.0, unit="g",
        basis="per_serving", review_status="wording",
        source="INH-011 trigger_food_or_pattern: 'fat-free meal containing carotenoids or vitamins A/D/E/K'",
        reason="fat-free is read literally as 0 g; a labelling definition such as '< 0.5 g' is not in the "
               "rule and is not applied"),
}

# ---- final applicability: is the recommendation warranted? ---------------------------------
# Keyed by rule id. threshold None / 'unreviewed' means the rule's wording gives no number.
APPLICABILITY_CRITERIA: dict[str, NutritionCriterion] = {
    "GLY-003": NutritionCriterion(
        key="carbohydrate_dominant", field="carb_energy_share", operator=">=", threshold=None,
        unit="fraction", basis="per_serving", review_status="unreviewed",
        source="GLY-003 trigger_food_or_pattern: 'carbohydrate-dominant meal'",
        reason="'dominant' has no numeric definition in the rule or in rule_codes (MACRO_CARB needs_review)"),
    "GLY-004": NutritionCriterion(
        key="carbohydrate_dominant", field="carb_energy_share", operator=">=", threshold=None,
        unit="fraction", basis="per_serving", review_status="unreviewed",
        source="GLY-004 trigger_food_or_pattern: 'carbohydrate-dominant meal'",
        reason="'dominant' has no numeric definition in the rule or in rule_codes (MACRO_CARB needs_review)"),
    "GLY-009": NutritionCriterion(
        key="carbohydrate_rich", field="Macro_Carbohydrate", operator=">=", threshold=None,
        unit="g", basis="per_serving", review_status="unreviewed",
        source="GLY-009 trigger_food_or_pattern: 'carbohydrate-rich meal'",
        reason="'rich' has no numeric definition in the rule or in rule_codes (MACRO_CARB needs_review)"),
    "GLY-011": NutritionCriterion(
        key="high_carbohydrate_serving", field="available_carbohydrate", operator=">=", threshold=None,
        unit="g", basis="per_serving", review_status="unreviewed",
        source="GLY-011 trigger_food_or_pattern: 'high-carbohydrate serving'",
        reason="'high' has no numeric definition in the rule or in rule_codes (MACRO_AVAIL_CARB needs_review)"),
}

# GLY-011 reads 'available carbohydrate'. The conventional definition (total carbohydrate by
# difference minus dietary fibre) is used for the candidate test; it is recorded, not hidden.
AVAILABLE_CARB_FORMULA = "Macro_Carbohydrate - Fiber (floored at 0)"
AVAILABLE_CARB_CRITERION = NutritionCriterion(
    key="available_carbohydrate_present", field="available_carbohydrate", operator=">", threshold=0.0,
    unit="g", basis="per_serving", review_status="wording",
    source="GLY-011 trigger_food_or_pattern: 'high-carbohydrate serving' (a serving must contain "
           "available carbohydrate to be high in it)",
    reason="candidate test only: available carbohydrate = " + AVAILABLE_CARB_FORMULA)
NUTRITION_RULE_CONFIG["MACRO_AVAIL_CARB"] = AVAILABLE_CARB_CRITERION


# --------------------------------------------------------------------------
# Reading and normalising a nutrient
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Reading:
    """A per-serving quantity ready to compare, or the reason it is not."""
    field: str
    value: float | None
    unit: str | None
    basis: str = "per_serving"
    normalization: str = ""
    problem: str | None = None          # set when value is None
    missing_field: str | None = None    # machine-readable name of what is absent
    verification: str = "unreviewed"    # 'plausible' | 'unreviewed' (adverse verdicts are problems)

    @property
    def ok(self) -> bool:
        return self.value is not None

    def evidence(self) -> dict:
        return {"field": self.field, "value": self.value, "unit": self.unit, "basis": self.basis,
                "normalization": self.normalization, "verification": self.verification}


def _verification(facts) -> tuple[str, str | None]:
    """('plausible'|'unreviewed', None) when usable, else (verdict, reason it is not)."""
    review = facts.metadata.get("nutrition_review")
    if review is None:
        if REQUIRE_PLAUSIBILITY_REVIEW:
            return "unreviewed", "recipe nutrition has not been plausibility-reviewed"
        return "unreviewed", None
    verdict = review.get("verdict")
    if verdict in UNVERIFIED_VERDICTS:
        return verdict, "recipe nutrition was reviewed and judged %r" % verdict
    return verdict, None


def read_nutrient(facts, nutrient_id: str, want_unit: str) -> Reading:
    """One nutrient as a per-serving value in `want_unit`.

    Refuses (returns a Reading with a problem) when the value is absent, the basis cannot be
    brought to per serving, the unit cannot be converted, or the review says it is not usable.
    """
    label = "recipe_nutrition.%s" % nutrient_id
    verdict, bad = _verification(facts)
    if bad:
        return Reading(nutrient_id, None, None, problem=bad, missing_field=label + ".verification",
                       verification=verdict)
    if nutrient_id not in facts.nutrients:
        return Reading(nutrient_id, None, None, problem="%s is not available for this recipe" % nutrient_id,
                       missing_field=label)
    value = facts.nutrients[nutrient_id]
    have_unit = facts.metadata.get("nutrient_units", {}).get(nutrient_id)
    if have_unit is None:
        return Reading(nutrient_id, None, None, problem="%s has no unit recorded" % nutrient_id,
                       missing_field=label + ".unit")
    steps = []

    basis = facts.metadata.get("nutrition_basis")
    if basis == "per_serving":
        pass
    elif basis == "per_recipe":
        servings = facts.metadata.get("servings")
        if not servings or servings <= 0:
            return Reading(nutrient_id, None, None, basis="per_recipe",
                           problem="%s is per recipe and the number of servings is unknown" % nutrient_id,
                           missing_field="recipe.servings")
        value = value / servings
        steps.append("per recipe / %s servings" % servings)
    else:
        return Reading(nutrient_id, None, None, basis=str(basis),
                       problem="%s has nutrition basis %r, which cannot be brought to per serving"
                               % (nutrient_id, basis),
                       missing_field="recipe_nutrition.basis")

    factor = UNIT_FACTORS.get((have_unit, want_unit))
    if factor is None:
        return Reading(nutrient_id, None, have_unit,
                       problem="cannot convert %s from %r to %r" % (nutrient_id, have_unit, want_unit),
                       missing_field=label + ".unit")
    if factor != 1.0:
        value = value * factor
        steps.append("%s -> %s" % (have_unit, want_unit))
    return Reading(nutrient_id, value, want_unit, normalization="; ".join(steps) or "published per serving",
                   verification=verdict or "unreviewed")


def compute_field(facts, field: str, unit: str) -> Reading:
    """A native nutrient, or one of the computed fields, as a Reading."""
    if field == "available_carbohydrate":
        carb = read_nutrient(facts, "Macro_Carbohydrate", "g")
        fibre = read_nutrient(facts, "Fiber", "g")
        for part in (carb, fibre):
            if not part.ok:
                return Reading(field, None, None, problem=part.problem, missing_field=part.missing_field)
        return Reading(field, max(carb.value - fibre.value, 0.0), "g",
                       normalization=AVAILABLE_CARB_FORMULA, verification=carb.verification)
    if field == "carb_energy_share":
        parts = [read_nutrient(facts, n, "g") for n in ATWATER_KCAL_PER_G]
        for part in parts:
            if not part.ok:
                return Reading(field, None, None, problem=part.problem, missing_field=part.missing_field)
        kcal = {p.field: p.value * ATWATER_KCAL_PER_G[p.field] for p in parts}
        total = sum(kcal.values())
        if total <= 0:
            return Reading(field, None, None, problem="macronutrient energy is zero",
                           missing_field="recipe_nutrition.macronutrients")
        return Reading(field, kcal["Macro_Carbohydrate"] / total, "fraction",
                       normalization="Atwater 4/4/9 share of carbohydrate+protein+fat energy",
                       verification=parts[0].verification)
    return read_nutrient(facts, field, unit)


def compare(value: float, op: str, threshold: float) -> bool:
    return OPERATORS[op](value, threshold)


def check(facts, criterion: NutritionCriterion, scale: float = 1.0) -> dict:
    """Apply a criterion to a recipe. Returns a dict with:

    state       'met' | 'not_met' | 'undefined' (no usable threshold) | 'unavailable'
    reading     the Reading used (value, unit, basis, normalization, verification)
    criterion   the configuration applied, so a result can show the threshold it used
    scale       a multiplier applied to the value first (e.g. intended portions), recorded
    """
    reading = compute_field(facts, criterion.field, criterion.unit)
    out = {"reading": reading, "criterion": criterion, "scale": scale}
    if not reading.ok:
        out["state"] = "unavailable"
        return out
    if not criterion.usable():
        out["state"] = "undefined"
        return out
    value = reading.value * scale
    out["effective_value"] = value
    out["state"] = "met" if compare(value, criterion.operator, criterion.threshold) else "not_met"
    return out


def evidence_of(result: dict) -> dict:
    """The part of a check() a verdict should show: the value, unit, threshold and basis."""
    reading, crit = result["reading"], result["criterion"]
    return {"criterion": crit.as_dict(), "reading": reading.evidence(),
            "effective_value": result.get("effective_value"), "scale": result["scale"],
            "state": result["state"]}


def macro_summary(facts) -> dict:
    """Carbohydrate, protein and fat (g per serving) and energy shares, for evidence only."""
    out = {}
    for nid in ATWATER_KCAL_PER_G:
        r = read_nutrient(facts, nid, "g")
        out[nid] = r.value if r.ok else None
    if all(v is not None for v in out.values()):
        kcal = {n: out[n] * ATWATER_KCAL_PER_G[n] for n in out}
        total = sum(kcal.values())
        if total > 0:
            out["energy_share"] = {n: round(k / total, 3) for n, k in kcal.items()}
    return out


# --------------------------------------------------------------------------
# Candidate facts
# --------------------------------------------------------------------------
def _trigger_fact(code: str, criterion: NutritionCriterion, facts) -> DerivedFact | None:
    result = check(facts, criterion)
    reading = result["reading"]
    if result["state"] == "unavailable":
        # The trigger cannot be ruled in or out. The rule is called so it can say exactly
        # what is missing (NEEDS_CONTEXT), rather than silently not being called.
        return DerivedFact(code=code, source="recipe_nutrition", value=None, unit=criterion.unit,
                           evidence="%s: %s" % (criterion.field, reading.problem), confidence="unknown")
    if result["state"] != "met":
        return None
    return DerivedFact(
        code=code, source="recipe_nutrition", value=round(reading.value, 4), unit=reading.unit,
        evidence="%s = %g %s %s, %s %g %s (%s)" % (
            criterion.field, reading.value, reading.unit, criterion.basis.replace("_", " "),
            criterion.operator, criterion.threshold, criterion.unit, criterion.source),
        confidence="high" if reading.verification == "plausible" else "medium")


def nutrition_candidate_facts(facts, context=None) -> list[DerivedFact]:
    """Facts that call MACRO_CARB, MACRO_FAT_LOW (and MACRO_AVAIL_CARB, see below)."""
    out = []
    for code, criterion in NUTRITION_RULE_CONFIG.items():
        fact = _trigger_fact(code, criterion, facts)
        if fact is not None:
            out.append(fact)
    return out
