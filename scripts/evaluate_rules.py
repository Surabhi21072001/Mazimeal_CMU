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
            },
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


def _fat_present(facts: RecipeFacts, lines: list[str]) -> ProcessFact:
    """Fat present either as an ingredient or named in the instructions."""
    for ing in facts.ingredients:
        name = ing.ingredient_name.lower()
        if any(fp in name for fp in FAT_PHRASES):
            return ProcessFact(True, evidence=f"ingredient: {ing.ingredient_name}")
    return _find(lines, FAT_PHRASES)


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

        "cooling_detected": _find(lines, COOL_PHRASES),
        "reheating_detected": _find(lines, REHEAT_PHRASES),
    }
    return pf


# --------------------------------------------------------------------------
# Evaluators (one per implemented rule). Each returns EvaluatedRule.
#
# Shared contract: if the trigger ingredient is present but there are no
# instructions, return NEEDS_CONTEXT (we cannot inspect the process).
# --------------------------------------------------------------------------
def _needs_context(c: DetectedRule, checked, reason) -> EvaluatedRule:
    return _make(c, ApplicabilityStatus.NEEDS_CONTEXT, checked, (), (), reason)


def _make(c: DetectedRule, status, checked, passed, failed, reason) -> EvaluatedRule:
    return EvaluatedRule(
        rule_id=c.rule_id, rule_name=c.rule_name, trigger_code=c.trigger_code,
        automation_status=c.automation_status, candidate=True,
        applicability_status=status,
        conditions_checked=tuple(checked), conditions_passed=tuple(passed),
        conditions_failed=tuple(failed), reason=reason,
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


RULE_EVALUATORS = {
    "BIO-002": evaluate_bio_002,
    "BIO-003": evaluate_bio_003,
    "BIO-007": evaluate_bio_007,
    "BIO-011": evaluate_bio_011,
    "GLY-007": evaluate_gly_007,
}


# --------------------------------------------------------------------------
# Dispatcher + high-level API
# --------------------------------------------------------------------------
_STEP_PREFIX = re.compile(r"^\s*(\d+)[.)]\s*(.*)$")


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
                       process_facts: dict[str, ProcessFact]) -> EvaluatedRule:
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
        )
    return fn(rule, facts, process_facts)


def evaluate_rule(rule: DetectedRule, facts: RecipeFacts,
                  process_facts: dict[str, ProcessFact]) -> EvaluatedRule:
    """Evaluate a candidate rule, then enrich the result with metadata +
    matched_on. Applicability logic is unchanged (see _evaluate_rule_raw)."""
    result = _evaluate_rule_raw(rule, facts, process_facts)
    return _enrich(result, rule, facts, process_facts)


def evaluate_recipe_rules(conn, recipe_id) -> list[EvaluatedRule]:
    """Full flow: facts -> candidates -> process facts -> evaluated rules.

    Does not route by automation_status; it is carried through on each result.
    """
    facts = build_recipe_facts(conn, recipe_id)
    candidates = detect_rules_from_facts(conn, facts)
    process_facts = extract_process_facts(facts)
    return [evaluate_rule(c, facts, process_facts) for c in candidates]


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
        out.append(f"  Reason: {e.reason}")
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
            candidates = detect_rules_from_facts(conn, facts)
            pfacts = extract_process_facts(facts)
            evaluated = [evaluate_rule(c, facts, pfacts) for c in candidates]
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
