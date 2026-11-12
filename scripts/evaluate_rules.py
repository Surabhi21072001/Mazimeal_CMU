#!/usr/bin/env python3
"""Deterministic condition evaluation for candidate business rules.

Moves a candidate rule (its trigger_code is present in the recipe) to one of:

    APPLICABLE      trigger present AND required conditions satisfied
    NOT_APPLICABLE  trigger present BUT the recipe already satisfies the rule,
                    or a required condition fails
    NEEDS_CONTEXT   trigger present BUT the engine lacks the information to
                    decide (e.g. no instructions, or no evaluator implemented)

Flow:
    RecipeFacts -> detect candidate rules -> extract process facts
                -> evaluate each candidate -> EvaluatedRule

Scope limits (intentional): no nutrient thresholds, no user/clinical context,
no conflict resolution, no prioritization, no LLM, no recipe modification.
Process facts come from deterministic phrase matching over recipe instructions
only; each fact keeps the raw instruction text that produced it, so results are
auditable.

CLI:
    python3 scripts/evaluate_rules.py --dsn "dbname=mazimeal" <recipe_id> [...]
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field, replace
from enum import Enum

from recipe_facts import RecipeFacts, RecipeNotFound, build_recipe_facts
from detect_rules import DetectedRule, detect_rules_from_facts
import derived_facts as DF
import nutrition_facts as NF
from evaluation_context import EvaluationContext


# --------------------------------------------------------------------------
# Status model
# --------------------------------------------------------------------------
class ApplicabilityStatus(str, Enum):
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NEEDS_CONTEXT = "NEEDS_CONTEXT"

    def __str__(self) -> str:  # so f-strings print the bare value
        return self.value


@dataclass(frozen=True)
class ProcessFact:
    """One derived cooking/process fact plus the evidence that produced it."""
    value: bool
    evidence: str | None = None  # the instruction phrase/line that matched

    def as_dict(self) -> dict:
        return {"value": self.value, "evidence": self.evidence}


@dataclass(frozen=True)
class MatchedStep:
    """An instruction step that contributed evidence. step_number is recovered
    from the 'N. text' numbering RecipeFacts applies; None if not recoverable."""
    text: str
    step_number: int | None = None

    def as_dict(self) -> dict:
        return {"step_number": self.step_number, "text": self.text}


@dataclass(frozen=True)
class EvaluatedRule:
    rule_id: str
    rule_name: str
    trigger_code: str
    automation_status: str | None
    candidate: bool
    applicability_status: ApplicabilityStatus
    conditions_checked: tuple[str, ...]
    conditions_passed: tuple[str, ...]
    conditions_failed: tuple[str, ...]
    reason: str
    # Enrichment (filled after the evaluator runs; defaults keep the evaluator
    # helpers _make/_needs_context unchanged).
    rule_category: str | None = None
    rule_type: str | None = None
    evidence_tier: str | None = None
    target_code: str | None = None
    target_nutrient_or_outcome: str | None = None
    action: str | None = None
    recipe_engine_instruction: str | None = None
    mechanism: str | None = None
    conditions_and_limits: str | None = None
    source_title: str | None = None
    source_url: str | None = None
    matched_ingredients: tuple[tuple[str, str], ...] = ()  # (ingredient_id, name)
    matched_steps: tuple[MatchedStep, ...] = ()
    # Added with fact-driven triggering. All optional, so every earlier constructor call and
    # every consumer of as_dict() keeps working.
    trigger_source: str | None = None           # 'ingredient', 'recipe_process', 'recipe_nutrition', ...
    matched_facts: tuple = ()                   # tuple[DerivedFact, ...]: what called the rule
    missing_context: tuple = ()                 # tuple[dict, ...]: {'field', 'reason'} exactly what is absent
    evidence: dict | None = None                # values, units, thresholds and conditions the verdict used

    def as_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "rule_category": self.rule_category,
            "rule_type": self.rule_type,
            "automation_status": self.automation_status,
            "evidence_tier": self.evidence_tier,
            "applicability_status": str(self.applicability_status),
            "candidate": self.candidate,
            "trigger_code": self.trigger_code,
            "target_code": self.target_code,
            "target_nutrient_or_outcome": self.target_nutrient_or_outcome,
            "action": self.action,
            "recipe_engine_instruction": self.recipe_engine_instruction,
            "mechanism": self.mechanism,
            "conditions_and_limits": self.conditions_and_limits,
            "conditions_checked": list(self.conditions_checked),
            "conditions_passed": list(self.conditions_passed),
            "conditions_failed": list(self.conditions_failed),
            "matched_on": {
                "ingredients": [
                    {"ingredient_id": iid, "name": name}
                    for iid, name in self.matched_ingredients
                ],
                "steps": [s.as_dict() for s in self.matched_steps],
                # Every fact that called the rule, with its source. 'ingredients' and
                # 'steps' keep their original shape; this list is the structured view.
                "facts": [f.as_dict() for f in self.matched_facts],
            },
            "trigger_source": self.trigger_source,
            "missing_context": [dict(m) for m in self.missing_context],
            "evidence": self.evidence,
            "reason": self.reason,
            "source_title": self.source_title,
            "source_url": self.source_url,
        }


# --------------------------------------------------------------------------
# Process-fact extraction
#
# Deterministic phrase matching only. Each concept is a list of phrases; the
# first instruction line containing any phrase becomes the evidence. Kept as
# small, auditable tables rather than a parser.
# --------------------------------------------------------------------------
# Generic chopping verbs (used for crucifers and general produce prep, and for
# garlic when co-occurring with the word "garlic" on the same line).
CHOP_VERBS = ["chop", "chopped", "mince", "minced", "crush", "crushed",
              "dice", "diced", "slice", "sliced", "shred", "shredded",
              "grate", "grated", "press ", "pressed", "cut "]
HEAT_VERBS = ["saute", "sauté", "sautee", "fry", "fried", "cook", "cooked",
              "cooking", "heat", "heated", "simmer", "simmered", "boil",
              "boiled", "bake", "baked", "roast", "roasted", "steam",
              "steamed", "grill", "grilled", "stir-fry", "stir fry", "braise"]
REST_PHRASES = ["rest", "let sit", "let it sit", "let stand", "stand for",
                "leave for", "leave it", "wait ", "set aside", "allow it to rest",
                "allow to rest", "allow the", "10 minutes before",
                "minutes before", "sit for"]
AL_DENTE_PHRASES = ["al dente"]
FAT_PHRASES = ["oil", "olive oil", "butter", "ghee", "avocado", "tahini",
               "nuts", "seeds", "cream", "cheese", "coconut milk"]
COOL_PHRASES = ["cool", "refrigerate", "chill", "cold"]
REHEAT_PHRASES = ["reheat", "rewarm", "warm up", "warm through"]


def _instruction_lines(facts: RecipeFacts) -> list[str]:
    """Return instruction lines (lowercased) or [] when unavailable."""
    if not facts.instructions:
        return []
    return [ln.strip() for ln in facts.instructions.split("\n") if ln.strip()]


def _find(lines: list[str], phrases: list[str]) -> ProcessFact:
    """True + evidence if any phrase appears in any instruction line."""
    for ln in lines:
        low = ln.lower()
        for p in phrases:
            if p in low:
                return ProcessFact(True, evidence=ln)
    return ProcessFact(False, evidence=None)


def _find_cooccurrence(lines: list[str], noun: str, verbs: list[str]) -> ProcessFact:
    """True + evidence when a line mentions `noun` and any of `verbs`.

    Handles natural wording like 'Mince the garlic' where the verb and noun are
    not adjacent, without a full parser."""
    return _find_cooccurrence_any(lines, [noun], verbs)


def _find_cooccurrence_any(lines: list[str], nouns: list[str], verbs: list[str]) -> ProcessFact:
    """True + evidence when a line mentions ANY noun and ANY verb together."""
    for ln in lines:
        low = ln.lower()
        if any(n in low for n in nouns) and any(v in low for v in verbs):
            return ProcessFact(True, evidence=ln)
    return ProcessFact(False, evidence=None)


def _ingredient_present(facts: RecipeFacts, code: str) -> bool:
    return code in facts.ingredient_codes


CRUCIFER_NOUNS = ["broccoli", "cauliflower", "cabbage", "brussels sprout",
                  "brussels", "kale", "collard", "bok choy", "watercress",
                  "arugula", "crucifer"]


def _crucifer_names(facts: RecipeFacts) -> list[str]:
    """Crucifer nouns actually present as ingredients, for same-line matching."""
    found = []
    for ing in facts.ingredients:
        low = ing.ingredient_name.lower()
        for noun in CRUCIFER_NOUNS:
            if noun in low:
                found.append(noun)
    return found or CRUCIFER_NOUNS


# Word-aware patterns for FAT_PHRASES. Plain substring matching read 'boil' and 'broil' as
# 'oil' and 'buttermilk' as 'butter', so a tomato recipe that only boiled things counted as
# having a culinary fat. 'oil' and 'butter' now need a word start, and 'butter' must not
# be the start of another food. Other phrases keep their previous substring behaviour.
_FAT_PATTERNS = [
    re.compile(r"(?<![a-z])oils?(?![a-z])", re.I),
    re.compile(r"(?<![a-z])butter(?![a-z])(?!\s+(?:beans?|lettuce|squash|cookies?))", re.I),
] + [re.compile(re.escape(p), re.I) for p in FAT_PHRASES if p not in ("oil", "olive oil", "butter")]
# 'olive oil' is covered by the 'oil' pattern.


def _has_fat_word(text: str) -> bool:
    return any(p.search(text) for p in _FAT_PATTERNS)


def _fat_present(facts: RecipeFacts, lines: list[str]) -> ProcessFact:
    """Fat present either as an ingredient or named in the instructions."""
    for ing in facts.ingredients:
        if _has_fat_word(ing.ingredient_name):
            return ProcessFact(True, evidence=f"ingredient: {ing.ingredient_name}")
    for ln in lines:
        if _has_fat_word(ln):
            return ProcessFact(True, evidence=ln)
    return ProcessFact(False, evidence=None)


def extract_process_facts(facts: RecipeFacts) -> dict[str, ProcessFact]:
    """Derive structured cooking/process facts from a RecipeFacts.

    Returns {fact_name: ProcessFact}. `instructions_available` records whether
    any instruction text existed at all, which evaluators use to decide between
    a real answer and NEEDS_CONTEXT.
    """
    lines = _instruction_lines(facts)
    has_instructions = bool(lines)

    def ing(code):  # ingredient presence as a no-evidence ProcessFact
        return ProcessFact(_ingredient_present(facts, code), evidence=None)

    pf: dict[str, ProcessFact] = {
        "instructions_available": ProcessFact(has_instructions),

        "garlic_present": ing("ING_GARLIC"),
        "garlic_chopped": _find_cooccurrence(lines, "garlic", CHOP_VERBS),
        # Garlic heated: either the same line names garlic + a heat verb, or the
        # recipe clearly cooks (heat verb anywhere) — garlic is usually added to
        # a hot pan. Prefer same-line evidence when available.
        "garlic_heated": _find_cooccurrence(lines, "garlic", HEAT_VERBS)
                         if _find_cooccurrence(lines, "garlic", HEAT_VERBS).value
                         else _find(lines, HEAT_VERBS),
        "garlic_rest_period_detected": _find(lines, REST_PHRASES),

        "tomato_present": ing("ING_TOMATO"),
        "tomato_cooked": _find_cooccurrence_any(lines, ["tomato"], HEAT_VERBS),
        "fat_present": _fat_present(facts, lines),

        "pasta_present": ing("ING_PASTA"),
        "pasta_cooked": _find_cooccurrence_any(
            lines, ["pasta", "spaghetti", "fettuccine", "noodle", "macaroni",
                    "penne", "linguine", "orzo", "rotini"], HEAT_VERBS),
        "pasta_al_dente_instruction": _find(lines, AL_DENTE_PHRASES),

        "crucifer_present": ing("ING_CRUCIFER"),
        # Require a chop verb on the same line as an actual crucifer noun, so
        # "chopped parsley" does not count as chopping the broccoli/kale.
        "crucifer_chopped": _find_cooccurrence_any(lines, _crucifer_names(facts), CHOP_VERBS),
        "crucifer_cooked": _find_cooccurrence_any(lines, _crucifer_names(facts), HEAT_VERBS),

        "egg_present": ing("ING_EGG"),
        "egg_cooked": _find_cooccurrence_any(lines, ["egg"], HEAT_VERBS),

        # Cooling and reheating are read by the structured scanner in derived_facts
        # (whole words, negation-aware) rather than by substring: 'cold water' and
        # 'cool whip' are not cooling a dish. Same keys and evidence format as before.
        "cooling_detected": _scan_flag(facts, "cooling"),
        "reheating_detected": _scan_flag(facts, "reheating"),
    }
    return pf


def _scan_flag(facts: RecipeFacts, kind: str) -> ProcessFact:
    """ProcessFact for any affirmed cooling/reheating mention in any step (starch named or
    not), with the first step as evidence in the original 'N. text' format."""
    steps = DF.parse_steps(facts.instructions)
    pattern = DF._COOL if kind == "cooling" else DF._REHEAT
    for st in steps:
        affirmed, _ = DF.positive_hits(st.text, pattern)
        if affirmed:
            return ProcessFact(True, evidence="%d. %s" % (st.number, st.text) if st.number else st.text)
    return ProcessFact(False, evidence=None)


# --------------------------------------------------------------------------
# Evaluators (one per implemented rule). Each returns EvaluatedRule.
#
# Shared contract: if the trigger ingredient is present but there are no
# instructions, return NEEDS_CONTEXT (we cannot inspect the process).
# --------------------------------------------------------------------------
def _needs_context(c: DetectedRule, checked, reason, missing=(), evidence=None,
                   passed=(), failed=()) -> EvaluatedRule:
    """NEEDS_CONTEXT. `missing` lists exactly what is absent as {'field', 'reason'} dicts."""
    return _make(c, ApplicabilityStatus.NEEDS_CONTEXT, checked, passed, failed, reason,
                 missing=missing, evidence=evidence)


def _make(c: DetectedRule, status, checked, passed, failed, reason,
          missing=(), evidence=None) -> EvaluatedRule:
    return EvaluatedRule(
        rule_id=c.rule_id, rule_name=c.rule_name, trigger_code=c.trigger_code,
        automation_status=c.automation_status, candidate=True,
        applicability_status=status,
        conditions_checked=tuple(checked), conditions_passed=tuple(passed),
        conditions_failed=tuple(failed), reason=reason,
        missing_context=tuple(missing), evidence=evidence,
    )


def evaluate_bio_002(c, facts, pf) -> EvaluatedRule:
    """Garlic: crush/mince and rest before heating.

    APPLICABLE     garlic chopped + heated, no rest step -> rule adds value
    NOT_APPLICABLE a rest step is already present (rule satisfied)
    NEEDS_CONTEXT  no instructions to inspect
    """
    checked = ("garlic present", "garlic chopped/minced", "garlic heated",
               "rest period present")
    if not pf["instructions_available"].value:
        return _needs_context(c, checked,
            "Garlic is present, but cooking instructions are unavailable.")

    chopped = pf["garlic_chopped"].value
    heated = pf["garlic_heated"].value
    rested = pf["garlic_rest_period_detected"].value

    if rested:
        passed = ("garlic present", "rest period present")
        return _make(c, ApplicabilityStatus.NOT_APPLICABLE, checked, passed, (),
            f"A resting step is already present: {pf['garlic_rest_period_detected'].evidence!r}.")
    if chopped and heated:
        passed = ("garlic present", "garlic chopped/minced", "garlic heated",
                  "no rest period detected")
        return _make(c, ApplicabilityStatus.APPLICABLE, checked, passed, (),
            "Garlic is chopped/minced and heated with no resting step detected; "
            "adding a ~10 minute rest before heating would help allicin form.")
    # Chopped/heated not both detected -> not enough signal to assert applicability.
    failed = tuple(x for x, ok in (("garlic chopped/minced", chopped),
                                   ("garlic heated", heated)) if not ok)
    return _needs_context(c, checked,
        "Garlic present, but chopping and/or heating were not clearly detected "
        f"in the instructions (missing: {', '.join(failed)}).")


def evaluate_bio_003(c, facts, pf) -> EvaluatedRule:
    """Tomato: cook with a culinary fat for lycopene."""
    checked = ("tomato present", "tomato cooked", "fat present")
    if not pf["instructions_available"].value:
        return _needs_context(c, checked,
            "Tomato is present, but cooking instructions are unavailable.")
    cooked = pf["tomato_cooked"].value
    fat = pf["fat_present"].value
    if cooked and fat:
        passed = ("tomato present", "tomato cooked", "fat present")
        return _make(c, ApplicabilityStatus.NOT_APPLICABLE, checked, passed, (),
            f"Tomato is cooked and a fat is already present ({pf['fat_present'].evidence}).")
    if cooked and not fat:
        return _make(c, ApplicabilityStatus.APPLICABLE, checked,
            ("tomato present", "tomato cooked"), ("fat present",),
            "Tomato is cooked but no culinary fat was detected; adding a modest "
            "amount of unsaturated oil would aid lycopene absorption.")
    return _needs_context(c, checked,
        "Tomato present, but cooking was not clearly detected in the instructions.")


def evaluate_gly_007(c, facts, pf) -> EvaluatedRule:
    """Pasta: prefer al dente."""
    checked = ("pasta present", "al dente instruction present")
    if not pf["instructions_available"].value:
        return _needs_context(c, checked,
            "Pasta is present, but cooking instructions are unavailable.")
    if pf["pasta_al_dente_instruction"].value:
        return _make(c, ApplicabilityStatus.NOT_APPLICABLE, checked,
            ("pasta present", "al dente instruction present"), (),
            f"Recipe already specifies al dente: {pf['pasta_al_dente_instruction'].evidence!r}.")
    return _make(c, ApplicabilityStatus.APPLICABLE, checked,
        ("pasta present",), ("al dente instruction present",),
        "Pasta is present with no al dente instruction; cooking al dente would "
        "lower the glycemic response.")


def evaluate_bio_007(c, facts, pf) -> EvaluatedRule:
    """Crucifers: chop before cooking."""
    checked = ("crucifer present", "crucifer chopped", "crucifer cooked")
    if not pf["instructions_available"].value:
        return _needs_context(c, checked,
            "A crucifer is present, but cooking instructions are unavailable.")
    chopped = pf["crucifer_chopped"].value
    cooked = pf["crucifer_cooked"].value
    if chopped:
        return _make(c, ApplicabilityStatus.NOT_APPLICABLE, checked,
            ("crucifer present", "crucifer chopped"), (),
            f"A chopping step is already present: {pf['crucifer_chopped'].evidence!r}.")
    if cooked and not chopped:
        return _make(c, ApplicabilityStatus.APPLICABLE, checked,
            ("crucifer present", "crucifer cooked"), ("crucifer chopped",),
            "Crucifer is cooked with no chopping step detected; chopping before "
            "cooking helps form beneficial compounds.")
    return _needs_context(c, checked,
        "Crucifer present, but neither chopping nor cooking was clearly detected.")


def evaluate_bio_011(c, facts, pf) -> EvaluatedRule:
    """Eggs: cook rather than consume raw (protein + food safety)."""
    checked = ("egg present", "egg cooked")
    if not pf["instructions_available"].value:
        return _needs_context(c, checked,
            "Egg is present, but cooking instructions are unavailable.")
    if pf["egg_cooked"].value:
        return _make(c, ApplicabilityStatus.NOT_APPLICABLE, checked,
            ("egg present", "egg cooked"), (),
            f"Egg is already cooked: {pf['egg_cooked'].evidence!r}.")
    return _make(c, ApplicabilityStatus.APPLICABLE, checked,
        ("egg present",), ("egg cooked",),
        "Egg is present but no cooking step was detected; eggs should be cooked "
        "(protein absorption and food safety).")


def takes_context(fn):
    """Mark an evaluator that also receives the EvaluationContext as a fourth argument.
    The five original evaluators take (candidate, facts, process_facts) and are untouched."""
    fn.takes_context = True
    return fn


def _hit_summary(hits) -> list[dict]:
    """Scanner hits without the internal sort key, for evidence."""
    return [{"instruction_step": h["instruction_step"], "text": h["text"],
             "matched": h["matched"], "starch": h["starch"]} for h in hits]


@takes_context
def evaluate_gly_015(c, facts, pf, ctx=None) -> EvaluatedRule:
    """Cooked rice/pasta/potato: cool promptly, refrigerate, and reheat safely.

    The rule's action has three parts, so the recipe satisfies it only when it states all
    of them, cooling and refrigeration first and reheating after. Cooling alone leaves
    the reheating unsaid, and reheating alone leaves the cooling and storage unsaid, so
    each of those is APPLICABLE (the guidance adds something).

    APPLICABLE     cooling without reheating, reheating without cooling, or cooling and
                   reheating with no refrigeration stated
    NOT_APPLICABLE the starch is cooled, refrigerated and then reheated in the recipe;
                   or no step cools or reheats it
    NEEDS_CONTEXT  no instructions; reheating comes before any cooling; or a cooling or
                   reheating step does not say which food it concerns

    Exact times and temperatures are not checked: the rule says they must be localised to
    the applicable food code and no such table is configured. The result says so.
    """
    checked = ("cooked starch (rice/pasta/potato) present", "cooling step names the starch",
               "refrigeration stated", "reheating step names the starch", "cooling precedes reheating")
    limits_note = ("exact cooling/storage time and temperature limits are not checked: the rule "
                   "requires them to be localised to the applicable food code and none is configured")

    if not pf["instructions_available"].value:
        return _needs_context(c, checked,
            "GLY-015 is read from the recipe steps and no instructions are available.",
            missing=[{"field": "recipe.instructions",
                      "reason": "GLY-015 needs the cooking steps to see whether cooked starch is cooled or reheated"}])

    starch = DF.recipe_starch_ingredients(facts)
    if not starch:
        return _make(c, ApplicabilityStatus.NOT_APPLICABLE, checked, (), ("cooked starch (rice/pasta/potato) present",),
            "The recipe has no rice, pasta or potato ingredient, so there is no cooked starch to cool.",
            evidence={"starch_ingredients": []})

    scan = DF.cooling_scan(DF.parse_steps(facts.instructions))
    cooling, refrigeration, reheating = scan["cooling"], scan["refrigeration"], scan["reheating"]
    evidence = {
        "starch_ingredients": starch,
        "cooling": _hit_summary(cooling), "refrigeration": _hit_summary(refrigeration),
        "reheating": _hit_summary(reheating), "negated": _hit_summary(scan["negated"]),
        "unattributed": _hit_summary(scan["unattributed"]),
        "validated_limits": limits_note,
    }

    if not cooling and not reheating:
        if scan["unattributed"]:
            return _needs_context(c, checked,
                "A step mentions cooling or reheating but does not name the starch, so it cannot be tied to it.",
                missing=[{"field": "recipe.instructions.food_cooled_or_reheated",
                          "reason": "step %s mentions %r without saying which food"
                                    % (scan["unattributed"][0]["instruction_step"], scan["unattributed"][0]["matched"])}],
                evidence=evidence, passed=("cooked starch (rice/pasta/potato) present",))
        why = ("Cooling or reheating is explicitly ruled out in the steps."
               if scan["negated"] else "No step cools or reheats the starch.")
        return _make(c, ApplicabilityStatus.NOT_APPLICABLE, checked, ("cooked starch (rice/pasta/potato) present",),
                     ("cooling step names the starch",), why, evidence=evidence)

    if cooling and reheating and min(r["position"] for r in reheating) < min(k["position"] for k in cooling):
        return _needs_context(c, checked,
            "Reheating is mentioned before any cooling, so the order of cooling and reheating is unclear.",
            missing=[{"field": "recipe.instructions.order",
                      "reason": "step %s reheats before step %s cools"
                                % (min(reheating, key=lambda r: r["position"])["instruction_step"],
                                   min(cooling, key=lambda k: k["position"])["instruction_step"])}],
            evidence=evidence,
            passed=("cooked starch (rice/pasta/potato) present", "cooling step names the starch",
                    "reheating step names the starch"),
            failed=("cooling precedes reheating",))

    base = ("cooked starch (rice/pasta/potato) present",)
    if cooling and reheating:
        if refrigeration:
            return _make(c, ApplicabilityStatus.NOT_APPLICABLE, checked,
                base + ("cooling step names the starch", "refrigeration stated",
                        "reheating step names the starch", "cooling precedes reheating"), (),
                "The recipe already cools, refrigerates and then reheats the starch; "
                "%s." % limits_note, evidence=evidence)
        return _make(c, ApplicabilityStatus.APPLICABLE, checked,
            base + ("cooling step names the starch", "reheating step names the starch", "cooling precedes reheating"),
            ("refrigeration stated",),
            "The starch is cooled and reheated but refrigeration is not stated; add prompt "
            "refrigeration and safe reheating guidance.", evidence=evidence)
    if cooling:
        return _make(c, ApplicabilityStatus.APPLICABLE, checked,
            base + ("cooling step names the starch",), ("reheating step names the starch",),
            "The starch is cooled but no safe reheating is stated; add reheating guidance "
            "and storage limits.", evidence=evidence)
    return _make(c, ApplicabilityStatus.APPLICABLE, checked,
        base + ("reheating step names the starch",), ("cooling step names the starch",),
        "The starch is reheated but no prompt cooling or refrigeration is stated; add "
        "cooling and storage guidance.", evidence=evidence)


# --------------------------------------------------------------------------
# Shared helpers for rules decided from recipe nutrition and the member
# --------------------------------------------------------------------------
def _nutrition_unavailable(c, checked, readings, passed=()) -> EvaluatedRule | None:
    """NEEDS_CONTEXT naming every nutrient that is missing or unverified, else None."""
    bad = [r for r in readings if not r.ok]
    if not bad:
        return None
    return _needs_context(
        c, checked, "Recipe nutrition needed for %s is not usable: %s." % (c.rule_id, "; ".join(r.problem for r in bad)),
        missing=[{"field": r.missing_field, "reason": r.problem} for r in bad],
        evidence={"nutrition": [r.evidence() for r in readings if r.ok]}, passed=passed)


def _ingredient_hits(facts, pattern=None, codes=(), exclude=None) -> list[dict]:
    """Ingredients that match a whole-word pattern or carry one of `codes`, with why.
    `exclude` removes a NAME match that is a flavouring rather than the food the rule names
    (a tag match is never excluded: tags are curated)."""
    hits = []
    for ing in facts.ingredients:
        by_code = sorted(set(codes) & set(ing.rule_codes))
        word = pattern.search(ing.ingredient_name) if pattern else None
        if word and exclude is not None and exclude.search(ing.ingredient_name):
            word = None
        if by_code or word:
            hits.append({"ingredient_id": ing.ingredient_id, "name": ing.ingredient_name,
                         "matched_on": ("tag " + by_code[0]) if by_code else ("name: " + word.group(0).lower())})
    return hits


# Recommended foods, taken from each rule's own action / recipe_engine_instruction text.
VISCOUS_FIBER_RE = DF.compile_phrases(["legume", "oat", "oatmeal", "barley", "okra", "chia", "flax", "flaxseed",
                                       "psyllium"])                                      # GLY-002 action
PROTEIN_RE = DF.compile_phrases(["tofu", "fish", "poultry", "chicken", "turkey"])      # GLY-003 instruction
PROTEIN_CODES = ("ING_LEGUME", "ING_EGG", "ING_YOGURT")                                # beans, eggs, yogurt
UNSATURATED_FAT_RE = DF.compile_phrases([                                              # GLY-004 instruction
    "olive oil", "avocado", "nut", "almond", "walnut", "pecan", "cashew", "pistachio", "hazelnut", "peanut",
    "seed", "sesame", "chia", "flax", "tahini", "fish", "salmon", "tuna", "sardine", "mackerel", "trout", "anchovy"])
VINEGAR_RE = DF.compile_phrases(["vinegar"])                                            # GLY-009 action
# A name that mentions a protein or a seed is not that food when it is a flavouring: chicken
# broth, bouillon and stuffing mix, poultry seasoning and fish sauce are not a protein source,
# and celery, cumin, mustard... seeds are spices, not the nut-and-seed fat the rule means.
FLAVORING_RE = DF.compile_phrases(["broth", "stock", "bouillon", "seasoning", "sauce", "stuffing", "soup",
                                   "flavor", "flavored", "flavour", "flavoured", "gravy"])
SPICE_SEED_RE = DF.compile_phrases(["celery", "mustard", "caraway", "cumin", "fennel", "anise", "coriander",
                                    "dill", "fenugreek", "nigella", "poppy"])
SEASONING_OR_SPICE_RE = re.compile(FLAVORING_RE.pattern + "|" + SPICE_SEED_RE.pattern, re.I)
# Ingredient tags that mean 'a carotenoid or vitamin A/D/K source' (INH-011). The tag
# vocabulary has no vitamin E code.
FAT_SOLUBLE_CODES = ("NUT_CAROTENOIDS", "NUT_PROVITAMIN_A", "NUT_BETACAROTENE", "NUT_VITA", "NUT_VITD", "NUT_VITK")


def _personalization(ctx, concepts):
    """How the member changes the answer.

    ('general', ...)     no member supplied: the general recommendation stands, and the
                         result says personal limits were not evaluated
    ('missing', ...)     a member is supplied but their conditions were not: unknown, not none
    ('caution', ...)     the member's declared conditions match a limit in the rule's text
    ('clear', ...)       conditions were supplied and none of the rule's limits matches
    """
    from evaluation_context import matched_cautions
    if ctx is None or not ctx.is_personal():
        return "general", [], []
    if not concepts:                      # the rule's text names no member-level limit
        return "clear", [], []
    if ctx.conditions is None:
        return "missing", [], [{"field": "user_context.conditions",
                                "reason": "a member is being evaluated but their conditions were not provided; "
                                          "their absence cannot be assumed"}]
    return ("caution" if matched_cautions(ctx.conditions, concepts) else "clear",
            matched_cautions(ctx.conditions, concepts), [])


def _caution_result(c, checked, passed, kind, matched, missing, evidence):
    """The result for a member-dependent stop: a caution or missing member information.
    Never echoes the member's own condition text; only the rule's limit that matched."""
    evidence = dict(evidence or {})
    if kind == "missing":
        return _needs_context(c, checked, "The member's conditions were not provided, and %s has limits that "
                              "depend on them." % c.rule_id, missing=missing, evidence=evidence, passed=passed)
    first = matched[0]
    evidence["matched_limits"] = [{"concept": m.concept, "rule_text": m.rule_text,
                                   "effect": m.effect, "vocabulary_review": m.review_status} for m in matched]
    limit_label = checked[-1]             # by convention the last condition is the member-limit check
    if any(m.effect == "not_applicable" for m in matched):
        return _make(c, ApplicabilityStatus.NOT_APPLICABLE, checked, passed, (limit_label,),
                     "The rule's own limits exclude this member (%s)." % first.rule_text, evidence=evidence)
    return _needs_context(
        c, checked, "A limit in the rule applies to this member and calls for individual review: %s." % first.rule_text,
        missing=[{"field": "clinical_review.%s" % m.concept, "reason": m.rule_text} for m in matched],
        evidence=evidence, passed=passed, failed=(limit_label,))


def _general_note(kind):
    return "not evaluated: no member context supplied" if kind == "general" else "evaluated against the member's declared conditions"


def _undefined_threshold(c, checked, passed, result, extra_missing=(), facts=None):
    """NEEDS_CONTEXT because the rule's own wording gives no number to compare against."""
    crit = result["criterion"]
    ev_ = {"nutrition": NF.evidence_of(result)}
    if facts is not None:
        ev_["macros_per_serving"] = NF.macro_summary(facts)
    return _needs_context(
        c, checked,
        "The meal is not classified because the rule gives no numeric definition: %s (%s)." % (crit.source, crit.reason),
        missing=[{"field": "reviewed_definition.%s" % crit.key,
                  "reason": "%s; a reviewed %s threshold on %s (%s, %s) is required"
                            % (crit.reason, crit.operator, crit.field, crit.unit, crit.basis)}, *extra_missing],
        evidence=ev_, passed=passed, failed=("meal classified by a reviewed definition",))


def _carb_recommendation(c, facts, ctx, *, rule_id, satisfied_by, satisfied_label, checked_extra, action_reason,
                         pattern=None, codes=(), limits=(), classify=True, exclude=None):
    """Shared flow for the carbohydrate rules.

    1 carbohydrate present?  2 recommendation already in the recipe?  3 is the meal of the
    kind the rule is for (dominant / rich)?  4 does a limit for this member apply?  5 APPLICABLE.
    """
    carb_ok = NF.check(facts, NF.NUTRITION_RULE_CONFIG["MACRO_CARB"])
    checked = ("meal contains carbohydrate", satisfied_label)
    if classify:
        checked += ("meal classified by a reviewed definition",)
    checked += tuple(checked_extra)
    stop = _nutrition_unavailable(c, checked, [carb_ok["reading"]])
    if stop:
        return stop
    ev_ = {"carbohydrate": NF.evidence_of(carb_ok)}
    if carb_ok["state"] != "met":
        return _make(c, ApplicabilityStatus.NOT_APPLICABLE, checked, (), ("meal contains carbohydrate",),
                     "The recipe has no carbohydrate per serving, so there is nothing to pair.", evidence=ev_)
    passed = ("meal contains carbohydrate",)

    have = _ingredient_hits(facts, pattern, codes, exclude)
    if have:
        ev_["already_present"] = have
        return _make(c, ApplicabilityStatus.NOT_APPLICABLE, checked, passed, (satisfied_label,),
                     "The recipe already includes %s (%s)." % (satisfied_by, have[0]["name"]), evidence=ev_)
    passed += (satisfied_label,)

    if classify:
        crit = NF.APPLICABILITY_CRITERIA[rule_id]
        res = NF.check(facts, crit)
        ev_["classification"] = NF.evidence_of(res)
        if res["state"] == "unavailable":
            return _nutrition_unavailable(c, checked, [res["reading"]], passed=passed)
        if res["state"] == "undefined":
            return _undefined_threshold(c, checked, passed, res, facts=facts)
        if res["state"] == "not_met":
            return _make(c, ApplicabilityStatus.NOT_APPLICABLE, checked, passed, ("meal classified by a reviewed definition",),
                         "The meal does not meet the rule's definition (%s %s %s %s)."
                         % (crit.field, crit.operator, crit.threshold, crit.unit), evidence=ev_)
        passed += ("meal classified by a reviewed definition",)

    kind, matched, missing = _personalization(ctx, limits)
    ev_["personalization"] = _general_note(kind)
    if kind in ("missing", "caution"):
        return _caution_result(c, checked, passed, kind, matched, missing, ev_)
    return _make(c, ApplicabilityStatus.APPLICABLE, checked, passed + tuple(checked_extra), (), action_reason, evidence=ev_)


@takes_context
def evaluate_gly_002(c, facts, pf, ctx=None) -> EvaluatedRule:
    """Carbohydrate-containing meal: add soluble/viscous fibre.
    The trigger wording IS the threshold (carbohydrate > 0 g per serving). Satisfied when the
    recipe already has one of the foods the action lists. GI-condition limit from the rule text."""
    return _carb_recommendation(
        c, facts, ctx, rule_id="GLY-002", classify=False, pattern=VISCOUS_FIBER_RE, codes=("ING_LEGUME",),
        satisfied_by="a viscous-fibre food", satisfied_label="viscous fibre source not already present",
        checked_extra=("no GI-condition limit applies",), limits=("gi_condition",),
        action_reason="The meal contains carbohydrate and no viscous-fibre food; add legumes, oats, barley, "
                      "okra, chia, flax or psyllium-compatible ingredients, gradually.")


@takes_context
def evaluate_gly_003(c, facts, pf, ctx=None) -> EvaluatedRule:
    """Carbohydrate-dominant meal: pair with protein. 'Dominant' has no numeric definition
    (see nutrition_facts.APPLICABILITY_CRITERIA), so this is NEEDS_CONTEXT until one is reviewed."""
    return _carb_recommendation(
        c, facts, ctx, rule_id="GLY-003", pattern=PROTEIN_RE, codes=PROTEIN_CODES, exclude=FLAVORING_RE,
        satisfied_by="a protein source", satisfied_label="protein source not already present",
        checked_extra=("no kidney or protein-prescription limit applies",), limits=("kidney_disease",),
        action_reason="The meal is carbohydrate-dominant with no protein source; add an appropriate protein.")


@takes_context
def evaluate_gly_004(c, facts, pf, ctx=None) -> EvaluatedRule:
    """Carbohydrate-dominant meal: pair with a modest unsaturated fat. Same definition gap as GLY-003."""
    return _carb_recommendation(
        c, facts, ctx, rule_id="GLY-004", pattern=UNSATURATED_FAT_RE, codes=(), exclude=SEASONING_OR_SPICE_RE,
        satisfied_by="an unsaturated-fat food", satisfied_label="unsaturated fat source not already present",
        checked_extra=(), limits=(),
        action_reason="The meal is carbohydrate-dominant with no unsaturated-fat food; add a modest amount "
                      "within energy targets.")


@takes_context
def evaluate_gly_009(c, facts, pf, ctx=None) -> EvaluatedRule:
    """Carbohydrate-rich meal: include culinary vinegar when tolerated. 'Rich' has no numeric definition."""
    return _carb_recommendation(
        c, facts, ctx, rule_id="GLY-009", pattern=VINEGAR_RE, codes=(),
        satisfied_by="culinary vinegar", satisfied_label="vinegar not already present",
        checked_extra=("no reflux limit applies",), limits=("reflux",),
        action_reason="The meal is carbohydrate-rich with no vinegar; use normal culinary amounts "
                      "in a dressing or the dish, never concentrated vinegar.")


@takes_context
def evaluate_inh_011(c, facts, pf, ctx=None) -> EvaluatedRule:
    """Fat-free meal with fat-soluble nutrients: add a modest fat source.

    'Fat-free' is read literally as 0 g fat per serving (the trigger). The fat-soluble nutrient
    must be present as an approved ingredient tag; limits for gallbladder, pancreatic and
    fat-malabsorption conditions come from the rule's text."""
    checked = ("meal is fat-free", "a carotenoid or vitamin A/D/K source is present",
               "no fat-handling limit applies")
    fat = NF.check(facts, NF.NUTRITION_RULE_CONFIG["MACRO_FAT_LOW"])
    stop = _nutrition_unavailable(c, checked, [fat["reading"]])
    if stop:
        return stop
    ev_ = {"fat": NF.evidence_of(fat)}
    if fat["state"] != "met":
        return _make(c, ApplicabilityStatus.NOT_APPLICABLE, checked, (), ("meal is fat-free",),
                     "The recipe has %g g fat per serving, so it is not fat-free." % fat["reading"].value, evidence=ev_)
    sources = _ingredient_hits(facts, None, FAT_SOLUBLE_CODES)
    if not sources:
        return _make(c, ApplicabilityStatus.NOT_APPLICABLE, checked, ("meal is fat-free",),
                     ("a carotenoid or vitamin A/D/K source is present",),
                     "No ingredient is tagged as a carotenoid or vitamin A/D/K source, so low fat costs "
                     "no absorption here.", evidence=ev_)
    ev_["fat_soluble_sources"] = sources
    passed = ("meal is fat-free", "a carotenoid or vitamin A/D/K source is present")
    kind, matched, missing = _personalization(ctx, ("fat_handling_condition",))
    ev_["personalization"] = _general_note(kind)
    if kind in ("missing", "caution"):
        return _caution_result(c, checked, passed, kind, matched, missing, ev_)
    return _make(c, ApplicabilityStatus.APPLICABLE, checked, passed + ("no fat-handling limit applies",), (),
                 "The meal has no fat and contains fat-soluble nutrients; add a modest fat source "
                 "(%s)." % sources[0]["name"], evidence=ev_)


@takes_context
def evaluate_gly_005(c, facts, pf, ctx=None) -> EvaluatedRule:
    """Mixed meal with starch: eat non-starchy vegetables and protein before the starch.

    This is about the ORDER the member eats in, which the recipe cannot tell us and which is
    never inferred. It is decided from meal_context.eating_sequence:

    NOT_APPLICABLE every vegetable/protein in the sequence comes before the first starch
                   (already satisfied), or the sequence has no vegetable/protein (nothing to
                   put before the starch, so not a mixed meal)
    APPLICABLE     some vegetable or protein is eaten after the starch has begun
    NEEDS_CONTEXT  no eating sequence; or the sequence never mentions the starch
    """
    import meal_facts as MF
    checked = ("an eating sequence was supplied", "the sequence includes the starch",
               "vegetables and protein come before the starch")
    meal = getattr(ctx, "meal_context", None)
    starch = MF.recipe_or_meal_starch(facts, ctx)
    ev_ = {"starch": starch}
    if meal is None or not meal.eating_sequence:
        return _needs_context(c, checked,
            "GLY-005 depends on the order the member eats in, which was not provided.",
            missing=[{"field": "meal_context.eating_sequence",
                      "reason": "GLY-005 is about eating non-starchy vegetables and protein before the starch; "
                                "the order is behaviour and is not inferred from the recipe"}],
            evidence=ev_)
    seq = MF.classify_sequence(meal.eating_sequence)
    ev_["eating_sequence"] = list(meal.eating_sequence)
    ev_["unrecognised_sequence_terms"] = seq["ignored"]
    if not seq["starch"]:
        return _needs_context(c, checked,
            "The eating sequence never mentions the starch, so its position cannot be judged.",
            missing=[{"field": "meal_context.eating_sequence",
                      "reason": "the sequence must include where the starch (carbohydrate) is eaten"}],
            evidence=ev_, passed=("an eating sequence was supplied",))
    others = sorted(seq["vegetables"] + seq["protein"])
    if not others:
        return _make(c, ApplicabilityStatus.NOT_APPLICABLE, checked,
            ("an eating sequence was supplied", "the sequence includes the starch"),
            ("vegetables and protein come before the starch",),
            "The sequence has no vegetables or protein to put before the starch, so this is not a mixed meal.",
            evidence=ev_)
    first_starch = min(seq["starch"])
    late = [i for i in others if i > first_starch]
    if late:
        ev_["after_starch"] = [meal.eating_sequence[i] for i in late]
        return _make(c, ApplicabilityStatus.APPLICABLE, checked,
            ("an eating sequence was supplied", "the sequence includes the starch"),
            ("vegetables and protein come before the starch",),
            "The starch is eaten before %s; eating the non-starchy vegetables and protein first "
            "lowers the glucose rise." % ", ".join(ev_["after_starch"]), evidence=ev_)
    return _make(c, ApplicabilityStatus.NOT_APPLICABLE, checked, checked, (),
        "The member already eats the vegetables and protein before the starch.", evidence=ev_)


@takes_context
def evaluate_gly_010(c, facts, pf, ctx=None) -> EvaluatedRule:
    """Post-meal period: take a brief light-to-moderate walk after eating.

    instruction_only, 'subject to mobility and medical constraints'. So the member's
    conditions are required: their absence is never assumed.

    NOT_APPLICABLE the member already plans to walk after the meal
    NEEDS_CONTEXT  conditions not provided; or a mobility/medical limit applies
    APPLICABLE     conditions provided, no limit matches, no walk planned
    """
    checked = ("a meal context was supplied", "no mobility or medical limit applies", "no post-meal walk already planned")
    meal = getattr(ctx, "meal_context", None)
    if meal is None:
        return _needs_context(c, checked, "GLY-010 applies to a meal and no meal context was supplied.",
            missing=[{"field": "meal_context", "reason": "the rule concerns the period after a meal"}])
    ev_ = {"meal_context": meal.as_dict()}
    activity = (meal.post_meal_activity or "").lower().replace("_", " ")
    walks, _negated = DF.positive_hits(activity, re.compile(r"(?<![\w])walk\w*", re.I))
    if walks:
        return _make(c, ApplicabilityStatus.NOT_APPLICABLE, checked, checked[:1], (checked[2],),
            "The member already plans to walk after the meal.", evidence=ev_)
    if ctx.conditions is None:
        return _needs_context(c, checked,
            "Walking after a meal is subject to mobility and medical constraints, and the member's conditions "
            "were not provided.",
            missing=[{"field": "user_context.conditions",
                      "reason": "GLY-010 limits: injury, fall risk, cardiac limits or exercise restrictions "
                                "need individualized guidance; their absence cannot be assumed"}],
            evidence=ev_, passed=checked[:1])
    from evaluation_context import matched_cautions
    matched = matched_cautions(ctx.conditions, ("mobility_or_medical_limit",))
    if matched:
        return _caution_result(c, checked[:2], checked[:1], "caution", matched, [], ev_)
    return _make(c, ApplicabilityStatus.APPLICABLE, checked, checked[:2], (),
        "No mobility or medical limit was declared and no post-meal walk is planned; offer an optional "
        "light-to-moderate walk after eating.", evidence=ev_)


@takes_context
def evaluate_gly_011(c, facts, pf, ctx=None) -> EvaluatedRule:
    """High-carbohydrate serving: reduce the portion of available carbohydrate.

    Three things must be known and none is invented: what 'high' means (no numeric definition
    exists, so a reviewed threshold is required), how much the member will actually eat
    (meal_context.intended_portions), and the member's goals and energy needs, because the
    rule forbids underfeeding children, pregnancy, lactation, older adults, athletes and
    high energy needs. Every one that is missing is listed in the same result."""
    checked = ("available carbohydrate present", "serving is high in carbohydrate",
               "intended portions known", "member goals known", "no underfeeding limit applies")
    avail = NF.check(facts, NF.NUTRITION_RULE_CONFIG["MACRO_AVAIL_CARB"])
    stop = _nutrition_unavailable(c, checked, [avail["reading"]])
    if stop:
        return stop
    ev_ = {"available_carbohydrate": NF.evidence_of(avail)}
    if avail["state"] != "met":
        return _make(c, ApplicabilityStatus.NOT_APPLICABLE, checked, (), (checked[0],),
                     "There is no available carbohydrate per serving to reduce.", evidence=ev_)
    meal = getattr(ctx, "meal_context", None)
    portions = meal.intended_portions if meal else None
    crit = NF.APPLICABILITY_CRITERIA["GLY-011"]
    high = NF.check(facts, crit, scale=portions if portions else 1.0)
    ev_["classification"] = NF.evidence_of(high)
    passed = (checked[0],)

    if high["state"] == "not_met" and portions:
        return _make(c, ApplicabilityStatus.NOT_APPLICABLE, checked, passed, (checked[1],),
            "At %g intended portion(s) the serving is not high in carbohydrate (%.1f g against %g g)."
            % (portions, high["effective_value"], crit.threshold), evidence=ev_)
    if high["state"] == "met" and portions:
        passed += (checked[1], checked[2])

    missing = []
    if high["state"] == "undefined":
        missing.append({"field": "reviewed_definition.%s" % crit.key,
                        "reason": "%s; a reviewed %s threshold on %s (%s, %s) is required"
                                  % (crit.reason, crit.operator, crit.field, crit.unit, crit.basis)})
    if portions is None:
        missing.append({"field": "meal_context.intended_portions",
                        "reason": "the carbohydrate eaten is per serving times the servings the member will eat"})
    if ctx is None or ctx.goals is None:
        missing.append({"field": "user_context.goals",
                        "reason": "the rule scales the starch portion 'according to user goals'"})
    if ctx is None or ctx.conditions is None:
        missing.append({"field": "user_context.conditions",
                        "reason": "the rule must not underfeed children, pregnancy, lactation, older adults, "
                                  "athletes or high energy needs; their absence cannot be assumed"})
    if missing:
        ev_["macros_per_serving"] = NF.macro_summary(facts)
        return _needs_context(c, checked, "GLY-011 cannot be decided: %s." % "; ".join(m["field"] for m in missing),
                              missing=missing, evidence=ev_, passed=passed)

    from evaluation_context import matched_cautions
    tokens = list(ctx.conditions) + [t for t in (ctx.activity_level, ctx.life_stage) if t]
    matched = matched_cautions(tokens, ("high_energy_need_or_vulnerable_stage",))
    if matched:
        return _caution_result(c, checked[:5], passed + (checked[3],), "caution", matched, [], ev_)
    return _make(c, ApplicabilityStatus.APPLICABLE, checked, passed + (checked[3], checked[4]), (),
        "The intended serving is high in available carbohydrate (%.1f g) and no underfeeding limit applies; "
        "reduce the starch portion and replace the volume with non-starchy vegetables or protein."
        % high["effective_value"], evidence=ev_)


@takes_context
def evaluate_syn_012(c, facts, pf, ctx=None) -> EvaluatedRule:
    """Acidic moist dish: offer cast-iron cookware as an optional instruction.

    Definition used (population_scope 'general; avoid in iron overload'; action 'cook compatible
    foods in cast iron'; instruction 'offer cast-iron cookware as an optional instruction'):

    NOT_APPLICABLE the member has iron overload (the rule says avoid), or the recipe already
                   uses bare cast iron (the recommendation is followed)
    NEEDS_CONTEXT  no cookware is stated (absence is not evidence); the cookware's material is
                   unsettled (Dutch oven, enameled iron); the dish cannot be classed acidic
                   and moist because the rule gives no definition; or the member's
                   conditions are unknown
    APPLICABLE     not reachable today: it needs a reviewed definition of 'acidic moist dish',
                   which neither the rule nor rule_codes provides
    """
    import equipment_facts as EQ
    from evaluation_context import matched_cautions
    checked = ("cookware is stated", "bare cast iron is not already used", "dish is acidic and moist",
               "no iron-overload limit applies")
    eq = EQ.equipment_candidate_facts(facts, ctx)
    ev_ = {"equipment": [f.as_dict() for f in eq]}
    conditions = ctx.conditions if ctx is not None else None

    matched = matched_cautions(conditions, ("iron_overload",))
    if matched:
        return _caution_result(c, checked, (), "caution", matched, [], ev_)

    iron = [f for f in eq if f.value["equipment_code"] == "EQUIP_CAST_IRON"
            and f.value["review_status"] in ("auto", "confirmed")]
    if iron:
        step = iron[0].value["instruction_step"]
        return _make(c, ApplicabilityStatus.NOT_APPLICABLE, checked, (checked[0],), (checked[1],),
                     "The recipe already uses cast iron%s." % (" (step %s)" % step if step else ""), evidence=ev_)

    if not eq:
        return _needs_context(c, checked,
            "No cookware is stated for this recipe, and not mentioning it does not show what was used.",
            missing=[{"field": "recipe_equipment",
                      "reason": "SYN-012 is about the cookware; none is stated in recipe_equipment, the steps or the request"}],
            evidence=ev_)

    missing = []
    for f in eq:
        if f.value["review_status"] == "pending_review":
            where = "step %s" % f.value["instruction_step"] if f.value["instruction_step"] else "the request"
            missing.append({"field": "recipe_equipment.material",
                            "reason": "%s names %s (%s); whether it is bare iron is not settled and is awaiting review"
                                      % (where, f.value["equipment_code"], f.value["matched"])})
    missing.append({"field": "recipe.dish_acidity_and_moisture",
                    "reason": "SYN-012 applies to an 'acidic moist dish'; there is no reviewed definition of acidic or "
                              "moist, so the dish cannot be classified"})
    if conditions is None:
        missing.append({"field": "user_context.conditions",
                        "reason": "SYN-012 says to avoid cast iron in iron overload; its absence cannot be assumed"})
    return _needs_context(c, checked,
        "Cookware is stated but SYN-012 cannot be decided: %s." % "; ".join(m["field"] for m in missing),
        missing=missing, evidence=ev_, passed=(checked[0], checked[1]))


RULE_EVALUATORS = {
    "BIO-002": evaluate_bio_002,
    "BIO-003": evaluate_bio_003,
    "BIO-007": evaluate_bio_007,
    "BIO-011": evaluate_bio_011,
    "GLY-007": evaluate_gly_007,
    "GLY-015": evaluate_gly_015,
    "GLY-002": evaluate_gly_002,
    "GLY-003": evaluate_gly_003,
    "GLY-004": evaluate_gly_004,
    "GLY-009": evaluate_gly_009,
    "INH-011": evaluate_inh_011,
    "GLY-005": evaluate_gly_005,
    "GLY-010": evaluate_gly_010,
    "GLY-011": evaluate_gly_011,
    "SYN-012": evaluate_syn_012,
}


# --------------------------------------------------------------------------
# Dispatcher + high-level API
# --------------------------------------------------------------------------
_STEP_PREFIX = re.compile(r"^\s*(\d+)[.)]\s*(.*)$")

# Trigger codes established by derived process facts that carry their own instruction steps.
_DERIVED_STEP_CODES = frozenset({"PROC_COOL_REHEAT", "PROC_COOKWARE"})


def _matched_ingredients(rule: DetectedRule, facts: RecipeFacts) -> tuple[tuple[str, str], ...]:
    """Ingredients whose rule_codes contain the rule's trigger_code. Exact match
    only, no fuzzy logic. matched_on is evidence, independent of applicability."""
    out = []
    for ing in facts.ingredients:
        if rule.trigger_code in ing.rule_codes:
            out.append((ing.ingredient_id, ing.ingredient_name))
    return tuple(out)


def _matched_steps(result: EvaluatedRule, process_facts, facts) -> tuple[MatchedStep, ...]:
    """Instruction evidence that supported this evaluation.

    Collects distinct ProcessFact.evidence lines for the facts relevant to this
    rule's trigger, recovering the real step number from the 'N. text'
    numbering RecipeFacts applies. Empty when no instruction evidence exists."""
    relevant_prefix = {
        "ING_GARLIC": "garlic", "ING_TOMATO": "tomato", "ING_PASTA": "pasta",
        "ING_CRUCIFER": "crucifer", "ING_EGG": "egg",
    }.get(result.trigger_code)
    seen: dict[str, MatchedStep] = {}
    if result.trigger_code in _DERIVED_STEP_CODES:
        # A derived trigger carries its own steps (number and text) in the facts that called
        # it; there is no process-fact name to filter by.
        for fact in result.matched_facts:
            value = fact.value if isinstance(fact.value, dict) else {}
            if value.get("instruction_step") is not None and fact.evidence:
                key = "%s|%s" % (value["instruction_step"], fact.evidence)
                seen.setdefault(key, MatchedStep(text=fact.evidence,
                                                 step_number=value["instruction_step"] or None))
        return tuple(seen.values())
    for name, pf in process_facts.items():
        if not getattr(pf, "evidence", None):
            continue
        if relevant_prefix and not name.startswith(relevant_prefix):
            continue
        evidence = pf.evidence
        if evidence in seen:
            continue
        m = _STEP_PREFIX.match(evidence)
        if m:
            seen[evidence] = MatchedStep(text=m.group(2).strip(),
                                         step_number=int(m.group(1)))
        else:
            seen[evidence] = MatchedStep(text=evidence, step_number=None)
    return tuple(seen.values())


def _enrich(result: EvaluatedRule, rule: DetectedRule, facts: RecipeFacts,
            process_facts: dict[str, ProcessFact]) -> EvaluatedRule:
    """Attach rule metadata + matched_on to a raw evaluator result.

    Does not touch applicability_status, conditions, or reason — purely additive
    response enrichment."""
    result = replace(result, trigger_source=rule.trigger_source, matched_facts=tuple(rule.matched_facts))
    if result.applicability_status == ApplicabilityStatus.NEEDS_CONTEXT and not result.missing_context:
        # The original evaluators stop for exactly two reasons: no instructions, or the
        # process was not clearly stated in them. Name which, using their own reason text.
        have_steps = process_facts.get("instructions_available")
        field = ("recipe.instructions.process_detail" if have_steps is not None and have_steps.value
                 else "recipe.instructions")
        result = replace(result, missing_context=({"field": field, "reason": result.reason},))
    return replace(
        result,
        rule_category=rule.rule_category,
        rule_type=rule.rule_type,
        evidence_tier=rule.evidence_tier,
        target_code=rule.target_code,
        target_nutrient_or_outcome=rule.target_nutrient_or_outcome,
        action=rule.action,
        recipe_engine_instruction=rule.recipe_engine_instruction,
        mechanism=rule.mechanism,
        conditions_and_limits=rule.conditions_and_limits,
        source_title=rule.source_title,
        source_url=rule.source_url,
        matched_ingredients=_matched_ingredients(rule, facts),
        matched_steps=_matched_steps(result, process_facts, facts),
    )


def _evaluate_rule_raw(rule: DetectedRule, facts: RecipeFacts,
                       process_facts: dict[str, ProcessFact],
                       context: EvaluationContext | None = None) -> EvaluatedRule:
    """Dispatch to the rule's evaluator (unchanged applicability logic).

    Rules with no registered evaluator return NEEDS_CONTEXT with a clear reason
    rather than being silently marked applicable.
    """
    fn = RULE_EVALUATORS.get(rule.rule_id)
    if fn is None:
        return EvaluatedRule(
            rule_id=rule.rule_id, rule_name=rule.rule_name,
            trigger_code=rule.trigger_code, automation_status=rule.automation_status,
            candidate=True, applicability_status=ApplicabilityStatus.NEEDS_CONTEXT,
            conditions_checked=(), conditions_passed=(), conditions_failed=(),
            reason="condition evaluator not implemented",
            missing_context=({"field": "rule_evaluator",
                              "reason": "no evaluator is implemented for %s" % rule.rule_id},),
        )
    if getattr(fn, "takes_context", False):
        return fn(rule, facts, process_facts, context)
    return fn(rule, facts, process_facts)


def evaluate_rule(rule: DetectedRule, facts: RecipeFacts,
                  process_facts: dict[str, ProcessFact],
                  context: EvaluationContext | None = None) -> EvaluatedRule:
    """Evaluate a candidate rule, then enrich the result with metadata +
    matched_on. Applicability logic is unchanged (see _evaluate_rule_raw). `context` is
    optional; without it every evaluation behaves as before."""
    result = _evaluate_rule_raw(rule, facts, process_facts, context)
    return _enrich(result, rule, facts, process_facts)


def evaluate_primary_rules(conn, facts: RecipeFacts,
                           context: EvaluationContext | None = None) -> list[EvaluatedRule]:
    """Ordinary candidate rules: ingredient, composite and derived triggers."""
    candidates = detect_rules_from_facts(conn, facts, context)
    process_facts = extract_process_facts(facts)
    return [evaluate_rule(c, facts, process_facts, context) for c in candidates]


def evaluate_all_rules(conn, facts: RecipeFacts,
                       context: EvaluationContext | None = None) -> list[EvaluatedRule]:
    """Primary rules, then the engine-level rules that look at the primary results.

    The engine stage reads `primary` and returns separate results; it never alters them."""
    import engine_rules
    primary = evaluate_primary_rules(conn, facts, context)
    return primary + engine_rules.evaluate_engine_rules(conn, facts, context, primary)


def evaluate_recipe_rules(conn, recipe_id,
                          context: EvaluationContext | None = None) -> list[EvaluatedRule]:
    """Full flow: facts -> candidates -> process facts -> evaluated rules.

    Does not route by automation_status; it is carried through on each result.
    `context` (member + intended meal) is optional; without it the recipe is evaluated on
    its own and nothing about any member is read or assumed.
    """
    facts = build_recipe_facts(conn, recipe_id)
    return evaluate_all_rules(conn, facts, context)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
_STATUS_MARK = {
    ApplicabilityStatus.APPLICABLE: "APPLICABLE",
    ApplicabilityStatus.NOT_APPLICABLE: "NOT_APPLICABLE",
    ApplicabilityStatus.NEEDS_CONTEXT: "NEEDS_CONTEXT",
}


def format_evaluations(recipe_name, recipe_id, evaluated: list[EvaluatedRule]) -> str:
    out = [f"Recipe: {recipe_name}  [{recipe_id}]"]
    if not evaluated:
        out.append("  (no candidate rules)")
        return "\n".join(out)
    for e in evaluated:
        out.append("")
        out.append(f"Candidate: {e.rule_id}  {e.rule_name}")
        out.append(f"  Applicability: {e.applicability_status}")
        if e.conditions_checked:
            out.append("  Conditions:")
            passed = set(e.conditions_passed)
            failed = set(e.conditions_failed)
            for cond in e.conditions_checked:
                mark = "+" if cond in passed else ("x" if cond in failed else "-")
                out.append(f"    [{mark}] {cond}")
        out.append(f"  Automation status: {e.automation_status}")
        if e.trigger_source:
            out.append(f"  Trigger source: {e.trigger_source}")
        out.append(f"  Reason: {e.reason}")
        if e.missing_context:
            out.append("  Missing context:")
            for m in e.missing_context:
                out.append(f"    - {m['field']}: {m['reason']}")
    return "\n".join(out)


def _connect(dsn: str):
    try:
        import psycopg
        return psycopg.connect(dsn)
    except ImportError:
        pass
    import psycopg2
    return psycopg2.connect(dsn)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("recipe_ids", nargs="+")
    ap.add_argument("--dsn", default="dbname=mazimeal")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    conn = _connect(args.dsn)
    try:
        for rid in args.recipe_ids:
            try:
                facts = build_recipe_facts(conn, rid)
            except RecipeNotFound:
                print(f"\nRecipe: (unknown)  [{rid}]\n  (no such recipe)")
                continue
            evaluated = evaluate_all_rules(conn, facts)
            if args.json:
                import json
                print(json.dumps(
                    {"recipe_id": facts.recipe_id, "recipe_name": facts.recipe_name,
                     "evaluated": [e.as_dict() for e in evaluated]},
                    indent=2, default=str))
            else:
                print("\n" + format_evaluations(facts.recipe_name, facts.recipe_id, evaluated))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
