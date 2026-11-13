#!/usr/bin/env python3
"""Facts that do not come from ingredient tags.

A trigger code can be established by an ingredient tag (the original mechanism), or by a
FACT DERIVED from somewhere else: recipe nutrition, a cooking process in the instructions,
the meal the member intends to eat, the member, the equipment, or a result the engine has
already produced. Every such fact is a DerivedFact and keeps where it came from, so a
candidate rule can always say which fact called it and why.

    ingredient_facts + nutrition_facts + process_facts + meal_context_facts
        + user_context_facts + equipment_facts  ->  candidate facts  ->  detect_rules

Nothing here is written to ingredient_rule_tags. A fact is derived fresh for each
evaluation from the recipe and the context.

Text matching is deterministic: whole words and phrases only, so 'boil' never matches
'oil', and a negation within a few words ('do not refrigerate') cancels a mention.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

SOURCES = (
    "ingredient",
    "recipe_nutrition",
    "recipe_process",
    "meal_context",
    "user_context",
    "equipment",
    "engine_result",
)


@dataclass(frozen=True)
class DerivedFact:
    """One thing the engine knows, where it came from, and the evidence.

    code        the trigger code this fact establishes (e.g. 'PROC_COOL_REHEAT'), or a
                finer fact code
    source      one of SOURCES
    value       the measured or detected value; may be a small dict for structured facts
    unit        unit of `value` when it is a quantity
    evidence    the sentence, step or computation that produced it
    confidence  'high' | 'medium' | 'low' | 'unknown'
    """
    code: str
    source: str
    value: object | None = None
    unit: str | None = None
    evidence: str | None = None
    confidence: str | None = None

    def __post_init__(self):
        if self.source not in SOURCES:
            raise ValueError("unknown fact source %r (expected one of %s)" % (self.source, ", ".join(SOURCES)))

    def as_dict(self) -> dict:
        out = {"code": self.code, "source": self.source, "value": self.value, "unit": self.unit,
               "evidence": self.evidence, "confidence": self.confidence}
        if isinstance(self.value, dict) and self.value.get("instruction_step") is not None:
            out["instruction_step"] = self.value["instruction_step"]
        return out


# --------------------------------------------------------------------------
# Deterministic text matching
# --------------------------------------------------------------------------
def phrase_pattern(phrase: str) -> str:
    """Regex for a whole word or phrase. Spaces and hyphens are interchangeable
    ('cast iron' = 'cast-iron'); an optional plural 's'/'es' is allowed on the last word."""
    parts = [re.escape(p) for p in re.split(r"[\s\-]+", phrase.strip().lower()) if p]
    return r"(?<![\w])" + r"[\s\-]+".join(parts) + r"(?:e?s)?(?![\w])"


def compile_phrases(phrases) -> re.Pattern:
    return re.compile("|".join(phrase_pattern(p) for p in sorted(phrases, key=len, reverse=True)), re.I)


_NEGATION = re.compile(
    r"\b(?:not|no|never|without|avoid|skip|nor|dont|don't|do\s+not|doesnt|doesn't|isnt|isn't|"
    r"needn't|need\s+not|neednt|cannot|can't|cant|won't|wont)\b", re.I)


def is_negated(text: str, match_start: int, window_words: int = 4) -> bool:
    """True when a negation word appears within `window_words` words before the match.
    The window never crosses a sentence boundary, so 'Do not stir. Chill it.' does not
    negate 'chill'."""
    before = text[:match_start]
    before = re.split(r"[.;!?]", before)[-1]
    words = before.split()[-window_words:]
    return bool(_NEGATION.search(" ".join(words)))


@dataclass(frozen=True)
class Step:
    number: int
    text: str


_STEP_START = re.compile(r"^\s*(\d+)[.)]\s*(.*)$")


def parse_steps(instructions: str | None) -> list[Step]:
    """Split RecipeFacts.instructions ('1. text' per step) into numbered steps.

    A line without a number continues the previous step, so a step that contains a line
    break keeps its number. Text with no numbering at all becomes unnumbered steps
    (number 0) rather than being dropped."""
    if not instructions or not instructions.strip():
        return []
    steps: list[list] = []
    for line in instructions.split("\n"):
        if not line.strip():
            continue
        m = _STEP_START.match(line)
        if m:
            steps.append([int(m.group(1)), m.group(2).strip()])
        elif steps:
            steps[-1][1] = (steps[-1][1] + " " + line.strip()).strip()
        else:
            steps.append([0, line.strip()])
    return [Step(n, t) for n, t in steps if t]


def positive_hits(text: str, pattern: re.Pattern) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    """(affirmed, negated) matches of `pattern` in `text`, each as (matched string, offset)."""
    affirmed, negated = [], []
    for m in pattern.finditer(text):
        (negated if is_negated(text, m.start()) else affirmed).append((m.group(0), m.start()))
    return affirmed, negated


# --------------------------------------------------------------------------
# Starch in the recipe (GLY-015, GLY-005)
#
# GLY-015's own trigger text is 'cooked rice/pasta/potato cooling', so those three are the
# starches it names. No ingredient code says 'rice' or 'potato' (ING_GRAIN is every cereal
# and ING_COOKED_STARCH is tagged on nothing), hence the ingredient NAME is matched, by
# whole word. ING_PASTA is used as well when it is tagged.
# --------------------------------------------------------------------------
STARCH_WORDS = (
    "rice", "pasta", "spaghetti", "macaroni", "penne", "fettuccine", "linguine", "orzo",
    "rotini", "noodle", "potato", "potatoes",
)
_NOT_STARCH_FOOD = re.compile(r"\brice\s+(?:vinegar|wine|flour|paper|milk|bran|syrup|cake|krispies)\b"
                              r"|\bpotato\s+(?:starch|chip|chips|flour)\b", re.I)
_STARCH_RE = compile_phrases(STARCH_WORDS)


def starch_mentions(text: str) -> list[str]:
    """Starch words in `text`, ignoring non-staple uses such as 'rice vinegar'."""
    cleaned = _NOT_STARCH_FOOD.sub(" ", text)
    return [m.group(0).lower() for m in _STARCH_RE.finditer(cleaned)]


def recipe_starch_ingredients(facts) -> list[dict]:
    """Ingredients of the recipe that are a rice/pasta/potato starch, with why."""
    found = []
    for ing in facts.ingredients:
        words = starch_mentions(ing.ingredient_name)
        if "ING_PASTA" in ing.rule_codes or words:
            found.append({"ingredient_id": ing.ingredient_id, "name": ing.ingredient_name,
                          "matched_on": "ING_PASTA tag" if ("ING_PASTA" in ing.rule_codes and not words)
                          else "ingredient name: %s" % words[0]})
    return found


# --------------------------------------------------------------------------
# Cooling and reheating (GLY-015)
# --------------------------------------------------------------------------
# 'cool' as a verb or participle only; 'cool water', 'cool whip' are not cooling a dish.
_COOL = re.compile(
    r"(?<![\w])(?:cool(?:s|ed|ing)?(?![\w])(?![\s\-]+(?:water|whip|ranch|breeze|air|mint|dressing))"
    r"|chill(?:s|ed|ing)?(?![\w])(?![\s\-]+(?:water|wine|glass|plate|bowl))"
    r"|refrigerat\w*|fridge|refrigerator)", re.I)
_REFRIGERATE = re.compile(r"(?<![\w])(?:refrigerat\w*|fridge|refrigerator|chill(?:s|ed|ing)?)(?![\w])", re.I)
_REHEAT = re.compile(
    r"(?<![\w])(?:re[\s\-]?heat(?:s|ed|ing)?|re[\s\-]?warm(?:s|ed|ing)?|"
    r"warm(?:s|ed|ing)?\s+(?:\w+\s+){0,2}?(?:up|through))(?![\w])", re.I)


def cooling_scan(steps: list[Step]) -> dict:
    """Per-step cooling, refrigeration and reheating mentions.

    Returns {'cooling': [...], 'refrigeration': [...], 'reheating': [...], 'negated': [...],
    'unattributed': [...]}, each entry {'instruction_step', 'text', 'matched', 'starch'}.
    A mention counts only when the SAME step names a starch (rice, pasta, potato): a
    bare 'Cool completely.' cannot be tied to the starch, so it is kept under
    'unattributed' instead of triggering GLY-015."""
    out = {"cooling": [], "refrigeration": [], "reheating": [], "negated": [], "unattributed": []}
    for st in steps:
        starch = starch_mentions(st.text)
        for kind, pattern in (("cooling", _COOL), ("refrigeration", _REFRIGERATE), ("reheating", _REHEAT)):
            affirmed, negated = positive_hits(st.text, pattern)

            def ref(hit, st=st, starch=starch):
                word, offset = hit
                return {"instruction_step": st.number, "text": st.text, "matched": word.lower(),
                        "starch": starch[0] if starch else None, "position": (st.number, offset)}

            for hit in negated:
                out["negated"].append({**ref(hit), "kind": kind})
            for hit in affirmed:
                (out[kind] if starch else out["unattributed"]).append({**ref(hit), "kind": kind})
    return out


def process_cool_reheat_facts(facts) -> list[DerivedFact]:
    """PROC_COOL_REHEAT facts: one per affirmed cooling/reheating mention in a step that
    names a starch, and only when the recipe actually contains that kind of starch.

    This turns the old cooling_detected / reheating_detected booleans into structured
    facts that keep the step number and the step text."""
    steps = parse_steps(facts.instructions)
    if not steps or not recipe_starch_ingredients(facts):
        return []
    scan = cooling_scan(steps)
    out: list[DerivedFact] = []
    for role in ("cooling", "refrigeration", "reheating"):
        for hit in scan[role]:
            out.append(DerivedFact(
                code="PROC_COOL_REHEAT", source="recipe_process",
                value={"role": role, "instruction_step": hit["instruction_step"],
                       "matched": hit["matched"], "starch": hit["starch"]},
                evidence=hit["text"], confidence="high"))
    return out


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------
def collect_candidate_facts(facts, context=None) -> list[DerivedFact]:
    """Every non-ingredient fact that can call a rule. Order is stable.

    Ingredient facts are not repeated here; they continue to come from RecipeFacts
    (ingredient_codes), exactly as before."""
    out: list[DerivedFact] = []
    out += process_cool_reheat_facts(facts)
    for builder in _extra_builders():
        out += builder(facts, context)
    return out


def _extra_builders():
    """Fact builders from later phases, imported lazily so each phase is optional."""
    builders = []
    for mod, fn in (("nutrition_facts", "nutrition_candidate_facts"),
                    ("meal_facts", "meal_candidate_facts"),
                    ("equipment_facts", "equipment_candidate_facts")):
        try:
            module = __import__(mod)
        except ModuleNotFoundError as exc:
            if exc.name != mod:          # a real import error inside the module must surface
                raise
            continue
        builders.append(getattr(module, fn))
    return builders
