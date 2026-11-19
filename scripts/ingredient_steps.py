#!/usr/bin/env python3
"""Which instruction step handles WHICH ingredient, and how.

The older process facts ask "is anything in this recipe heated?". INH-006 and INH-007 need a
narrower question: is THIS ingredient heated, raw, or added after cooking, and for how long?
This module answers it deterministically from the recipe's own steps and keeps the evidence.

Design rules (all conservative; a mistake must fall toward NEEDS_CONTEXT, never toward a verdict):

  * Ingredient names are reduced to aliases by removing a fixed list of DESCRIPTORS only
    ('frozen', 'chopped', 'wedge'). A name is never reduced to a single overly generic word
    ('pepper', 'sauce', 'sprouts'), so 'green bell pepper' can match 'bell pepper' but
    'green pepper' cannot match every 'pepper'. When the aliases are poor the ingredient is simply
    not found, which is NEEDS_CONTEXT.
  * An ingredient is associated with a step only by a whole-word alias match in that step.
  * A step is cut into sentences and then into segments at commas and 'then'. A heating, raw or
    brief cue counts for an ingredient only when it is in the SAME segment as the ingredient.
    A cue in another segment of the step is not borrowed: that is 'neutral', which is unresolved.
  * Heat cues are read GENEROUSLY (a false 'heated' leads to NEEDS_CONTEXT); raw, garnish and
    brief cues are read STRICTLY (a false 'raw' would lead to a wrong NOT_APPLICABLE).
  * A negated cue ('do not boil', 'avoid cooking') is recorded but is not evidence of either
    heat or raw. It leaves the mention neutral.
  * An ingredient that no step names is 'not_mentioned'. It is never assumed raw.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from derived_facts import Step, compile_phrases, is_negated, parse_steps

# --------------------------------------------------------------------------
# Ingredient names
# --------------------------------------------------------------------------
DESCRIPTORS = frozenset("""
fresh frozen chopped diced sliced minced shredded grated crushed ground cooked canned raw dried
large small medium whole baby organic finely thinly coarsely torn packed drained rinsed trimmed
peeled seeded cored halved quartered florets floret wedge wedges slice slices tidbits chunks chunk
pieces piece cubed cubes bunch head heads leaves leaf stalks stalk
""".split())

# One-word results that are too generic to stand for an ingredient on their own.
GENERIC = frozenset("""
pepper peppers bell green red yellow orange white black juice sauce paste oil water salt chile chiles chili
chilies chilli fruit fruits vegetable vegetables greens leaves leaf sprouts sprout seeds seed mix blend powder
""".split())

_WORDS = re.compile(r"[a-z]+(?:'[a-z]+)?")


def _words(name: str) -> list[str]:
    return _WORDS.findall(name.lower())


_IRREGULAR = {"chilies": "chili", "chiles": "chile", "leaves": "leaf", "olives": "olive"}


def _singular(word: str) -> str:
    if word in _IRREGULAR:
        return _IRREGULAR[word]
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("oes") and len(word) > 4:
        return word[:-2]
    if word.endswith("ses") or word.endswith("ss") or word.endswith("us"):
        return word
    if word.endswith("s") and len(word) > 3:
        return word[:-1]
    return word


def canonical_key(name: str) -> str:
    """A normalised ingredient identity: descriptors removed, last word singular.
    'fresh tomatoes', 'Tomatoes' and 'tomato' share a key; 'tomato paste' does not."""
    words = [w for w in _words(name) if w not in DESCRIPTORS]
    if not words:
        words = _words(name)
    if words:
        words[-1] = _singular(words[-1])
    return " ".join(words)


def _generic(phrase: str) -> bool:
    return len(phrase.split()) == 1 and (phrase in GENERIC or _singular(phrase) in GENERIC)


def aliases(name: str) -> list[str]:
    """Phrases that may stand for this ingredient in a step, most specific first.

    Always the name as written and the descriptor-free name. Longer names also yield their
    trailing phrases ('green bell pepper' -> 'bell pepper') but never a lone generic word."""
    full = " ".join(_words(name))
    stripped = [w for w in _words(name) if w not in DESCRIPTORS]
    out: list[str] = []

    def add(phrase):
        phrase = phrase.strip()
        if phrase and phrase not in out and not _generic(phrase):
            out.append(phrase)
        # The singular form too: 'tomatoes' in the list, 'tomato' in the step. (The matcher
        # already accepts a plural of whatever is listed.)
        parts = phrase.split()
        if parts:
            single = " ".join(parts[:-1] + [_singular(parts[-1])])
            if single != phrase and single not in out and not _generic(single):
                out.append(single)

    add(full)
    add(" ".join(stripped))
    for i in range(1, len(stripped)):
        add(" ".join(stripped[i:]))   # generic one-word tails are refused by add()
    if not out and full:                       # nothing survived the generic filter: keep the name itself
        out.append(full)
    return out


# --------------------------------------------------------------------------
# Cue vocabulary
# --------------------------------------------------------------------------
HEAT_METHODS = {
    "steam": ("steam", "steamed", "steaming", "steams"),
    "boil": ("boil", "boiled", "boiling", "boils", "parboil", "parboiled"),
    "simmer": ("simmer", "simmered", "simmering"),
    "blanch": ("blanch", "blanched", "blanching"),
    "poach": ("poach", "poached", "poaching"),
    "saute": ("saute", "sauté", "sautee", "sauteed", "sautéed", "sautéing", "sauteing"),
    "stir_fry": ("stir-fry", "stir fry", "stir-fried", "stir fried", "stir-frying"),
    "fry": ("fry", "fried", "frying", "fries", "pan-fry", "pan-fried", "deep-fry", "deep-fried"),
    "roast": ("roast", "roasted", "roasting", "roasts"),
    "bake": ("bake", "baked", "baking", "bakes"),
    "broil": ("broil", "broiled", "broiling"),
    "grill": ("grill", "grilled", "grilling"),
    "sear": ("sear", "seared", "searing"),
    "braise": ("braise", "braised", "braising"),
    "stew": ("stew", "stewed", "stewing"),
    "microwave": ("microwave", "microwaved", "microwaving"),
    "slow_cook": ("slow cook", "slow-cook", "slow cooked", "slow-cooked", "slow cooker", "crock pot", "crockpot"),
    "pressure_cook": ("pressure cook", "pressure-cook", "pressure cooked", "pressure cooker"),
    "scramble": ("scramble", "scrambled", "scrambling"),
    "brown": ("brown", "browned", "browning"),
    "toast": ("toast", "toasted", "toasting"),
    "char": ("char", "charred", "charring"),
    "caramelize": ("caramelize", "caramelized", "caramelise", "caramelised"),
    "sweat": ("sweat", "sweated", "sweating"),
    "griddle": ("griddle", "griddled"),
    "cook": ("cook", "cooked", "cooking", "cooks", "overcook", "overcooked"),
    "heat": ("heated", "heating", "reheat", "reheated", "warm through", "heat through"),
}
_HEAT_PHRASES = [p for ps in HEAT_METHODS.values() for p in ps]
_HEAT_RE = compile_phrases(_HEAT_PHRASES)
# 'cooking spray', 'cooking oil', 'cooking time' name a product or a quantity, not an act of heating.
_NOT_HEAT = re.compile(r"\bcooking[\s-]+(?:spray|oil|oils|time|times|liquid|liquids|water|wine|sherry|utensils?|"
                       r"temperature|surface|method|directions|instructions|juices)\b"
                       r"|\bbaking[\s-]+(?:powder|soda|mix|dish|dishes|pan|pans|sheet|sheets|tray|trays|paper|parchment|"
                       r"chocolate|spray|stone)\b|\b(?:frying|roasting|grilling|broiling)[\s-]+(?:pan|pans|rack|tray|dish)\b", re.I)
_METHOD_OF = {p: m for m, ps in HEAT_METHODS.items() for p in ps}

# Added after cooking. Removed from the text BEFORE heat cues are read, because 'after cooking'
# contains the word 'cooking'.
AFTER_COOKING = ("after cooking", "once cooked", "when cooked", "off the heat", "off heat",
                 "remove from the heat", "removed from the heat", "from the heat", "before serving",
                 "just before serving", "at the end", "to finish", "finish with", "when done",
                 "at the table", "once done", "when ready to serve")
_AFTER_RE = compile_phrases(AFTER_COOKING)

# Used without cooking. Strict: only words that say so.
RAW_CUES = ("raw", "uncooked", "garnish", "garnished", "for garnish", "to garnish", "top with", "topped with",
            "serve with", "served with", "serve over", "serve alongside", "sprinkle", "sprinkled", "drizzle",
            "drizzled", "squeeze over", "squeezed over", "squeeze on")
_RAW_RE = compile_phrases(RAW_CUES)

# 'Brief' as the rule's own qualitative wording. Only explicit words; never inferred from the method.
BRIEF_WORDS = ("briefly", "quickly", "brief", "quick")
_BRIEF_RE = compile_phrases(BRIEF_WORDS)
# 'quick-cooking oats' and 'quick bread' use the word without describing the heating.
_NOT_BRIEF = re.compile(r"[\s-]+(?:cooking|cook|oats|bread|breads|release|rise|pickle|pickled|start)", re.I)

_DURATION = re.compile(
    r"(?P<lo>\d+(?:\.\d+)?)(?:\s*(?:-|–|to|or)\s*(?P<hi>\d+(?:\.\d+)?))?\s*"
    r"(?P<unit>seconds?|secs?|minutes?|mins?|hours?|hrs?)\b", re.I)
_QUALITATIVE_LONG = re.compile(r"\b(?:overnight|all day|all night|several hours|for hours)\b", re.I)


def _minutes(value: float, unit: str) -> float:
    unit = unit.lower()
    if unit.startswith("sec"):
        return value / 60.0
    if unit.startswith("h"):
        return value * 60.0
    return value


@dataclass(frozen=True)
class Duration:
    text: str
    minutes_low: float | None
    minutes_high: float | None

    def as_dict(self) -> dict:
        return {"text": self.text, "minutes_low": self.minutes_low, "minutes_high": self.minutes_high}


def parse_durations(text: str) -> list[Duration]:
    out = []
    for m in _DURATION.finditer(text):
        lo = _minutes(float(m.group("lo")), m.group("unit"))
        hi = _minutes(float(m.group("hi")), m.group("unit")) if m.group("hi") else lo
        out.append(Duration(m.group(0), lo, hi))
    for m in _QUALITATIVE_LONG.finditer(text):
        out.append(Duration(m.group(0), None, None))
    return out


# A neutral mention is harmless when it is plain preparation ('slice the lemon'). Anything else
# ('add to the pan', 'if using fresh lemons') leaves part of the ingredient's handling unknown.
PREP_VERBS = ("chop", "slice", "cut", "dice", "mince", "peel", "wash", "rinse", "core", "trim", "juice", "squeeze",
              "zest", "grate", "halve", "quarter", "seed", "drain", "shred", "pat", "stem", "hull", "pit", "separate",
              "measure", "thinly", "finely", "coarsely", "roughly")
_PREP_RE = compile_phrases(PREP_VERBS)
MIX_VERBS = ("add", "mix", "stir", "combine", "toss", "pour", "place", "put", "fold", "blend", "whisk", "season",
             "marinate", "coat", "layer", "arrange", "spread", "stuff", "fill", "transfer", "return", "using", "use")
_MIX_RE = compile_phrases(MIX_VERBS)


def split_segments(step_text: str) -> list[str]:
    """Sentences, then segments at commas and 'then'. Never splits on 'and' (see module doc)."""
    segments: list[str] = []
    for sentence in re.split(r"(?<=[.!?;])\s+", step_text.strip()):
        for part in re.split(r",|\bthen\b|\bafter which\b", sentence, flags=re.I):
            part = part.strip(" .;!?")
            if part:
                segments.append(part)
    return segments


# --------------------------------------------------------------------------
# Reading one segment
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class SegmentReading:
    heat: tuple[str, ...]          # affirmed heat words
    methods: tuple[str, ...]       # their methods, in order, without repeats
    negated_heat: tuple[str, ...]
    raw: tuple[str, ...]
    after: tuple[str, ...]
    brief: tuple[str, ...]
    durations: tuple[Duration, ...]


def read_segment(segment: str) -> SegmentReading:
    after = [m.group(0).lower() for m in _AFTER_RE.finditer(segment) if not is_negated(segment, m.start())]
    # Remove the after-cooking phrases and non-heat 'cooking X' before reading heat.
    blank = lambda m: " " * len(m.group(0))
    scrubbed = _NOT_HEAT.sub(blank, _AFTER_RE.sub(blank, segment))
    heat, negated = [], []
    for m in _HEAT_RE.finditer(scrubbed):
        (negated if is_negated(scrubbed, m.start()) else heat).append(m.group(0).lower())
    methods: list[str] = []
    for w in heat:
        key = re.sub(r"[\s\-]+", " ", w)
        method = _METHOD_OF.get(w) or _METHOD_OF.get(key) or _METHOD_OF.get(w.rstrip("s"), "cook")
        if method not in methods:
            methods.append(method)
    # Specific methods outrank the generic words that accompany them ('cook' beside 'simmer').
    specific = [m for m in methods if m not in ("cook", "heat")]
    methods = specific or methods
    raw = [m.group(0).lower() for m in _RAW_RE.finditer(scrubbed) if not is_negated(scrubbed, m.start())]
    brief = [m.group(0).lower() for m in _BRIEF_RE.finditer(scrubbed)
             if not is_negated(scrubbed, m.start()) and not _NOT_BRIEF.match(scrubbed[m.end():])]
    return SegmentReading(tuple(heat), tuple(methods), tuple(negated), tuple(raw), tuple(after), tuple(brief),
                          tuple(parse_durations(scrubbed)) if heat else ())


# --------------------------------------------------------------------------
# One ingredient across the recipe
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Mention:
    instruction_step: int
    segment: str
    role: str                       # heated | raw | after_cooking | neutral
    alias: str
    reading: SegmentReading
    prep_only: bool = False         # a neutral mention that is plain preparation

    def as_dict(self) -> dict:
        r = self.reading
        return {"instruction_step": self.instruction_step, "segment": self.segment, "role": self.role,
                "alias": self.alias, "prep_only": self.prep_only, "heat_words": list(r.heat), "methods": list(r.methods),
                "negated_heat_words": list(r.negated_heat), "raw_words": list(r.raw),
                "after_cooking_words": list(r.after), "brief_words": list(r.brief),
                "durations": [d.as_dict() for d in r.durations]}


@dataclass(frozen=True)
class Treatment:
    """How the recipe's steps treat one ingredient.

    state: no_instructions | not_mentioned | neutral_only | raw | brief_heat | heated | unresolved_mix

    'unresolved_mix' means the clear handling (raw or brief heat) is only part of the story: the ingredient is
    also named somewhere without saying what is done with it, so the clear part is not allowed to decide."""
    ingredient_id: str
    ingredient_name: str
    key: str
    aliases: tuple[str, ...]
    state: str
    mentions: tuple[Mention, ...]
    mixed: bool = False             # heated in one place and raw/after cooking in another

    @property
    def heated(self) -> tuple[Mention, ...]:
        return tuple(m for m in self.mentions if m.role == "heated")

    @property
    def unresolved(self) -> tuple[Mention, ...]:
        return tuple(m for m in self.mentions if m.role == "neutral" and not m.prep_only)

    @property
    def steps(self) -> tuple[int, ...]:
        return tuple(sorted({m.instruction_step for m in self.mentions}))

    def as_dict(self) -> dict:
        return {"ingredient_id": self.ingredient_id, "name": self.ingredient_name, "key": self.key,
                "aliases": list(self.aliases), "state": self.state, "mixed_treatment": self.mixed,
                "unresolved_steps": sorted({m.instruction_step for m in self.unresolved}),
                "mentions": [m.as_dict() for m in self.mentions]}


def _classify(reading: SegmentReading) -> str:
    if reading.heat:
        return "heated"
    if reading.after:
        return "after_cooking"
    if reading.raw:
        return "raw"
    return "neutral"


def treatment_of(ingredient_id: str, ingredient_name: str, steps: list[Step]) -> Treatment:
    names = tuple(aliases(ingredient_name))
    key = canonical_key(ingredient_name)
    if not steps:
        return Treatment(ingredient_id, ingredient_name, key, names, "no_instructions", ())
    patterns = [(a, compile_phrases([a])) for a in names]
    mentions: list[Mention] = []
    for st in steps:
        for seg in split_segments(st.text):
            hit = next((a for a, p in patterns if p.search(seg)), None)
            if hit is None:
                continue
            reading = read_segment(seg)
            role = _classify(reading)
            prep = role == "neutral" and bool(_PREP_RE.search(seg)) and not _MIX_RE.search(seg)
            mentions.append(Mention(st.number, seg, role, hit, reading, prep))
    if not mentions:
        return Treatment(ingredient_id, ingredient_name, key, names, "not_mentioned", ())
    heated = [m for m in mentions if m.role == "heated"]
    unheated = [m for m in mentions if m.role in ("raw", "after_cooking")]
    loose = [m for m in mentions if m.role == "neutral" and not m.prep_only]
    if heated:
        all_brief = all(m.reading.brief for m in heated)
        state = "brief_heat" if all_brief else "heated"
        if state == "brief_heat" and loose:
            state = "unresolved_mix"
        return Treatment(ingredient_id, ingredient_name, key, names, state, tuple(mentions),
                         mixed=bool(unheated))
    if unheated:
        return Treatment(ingredient_id, ingredient_name, key, names, "unresolved_mix" if loose else "raw",
                         tuple(mentions))
    return Treatment(ingredient_id, ingredient_name, key, names, "neutral_only", tuple(mentions))


def treatments_for(facts, code: str) -> list[Treatment]:
    """One Treatment per ingredient line of the recipe that carries `code`."""
    steps = parse_steps(facts.instructions)
    return [treatment_of(i.ingredient_id, i.ingredient_name, steps)
            for i in facts.ingredients if code in i.rule_codes]


# --------------------------------------------------------------------------
# Mustard (INH-007)
# --------------------------------------------------------------------------
# Only these forms are accepted as active myrosinase to restore. 'Dijon', 'prepared', 'yellow',
# a sauce, or a bare 'mustard' are NOT, and neither is a seed (a ground mustard SEED is excluded
# by the lookahead so it stays unconfirmed).
MUSTARD_RE = re.compile(
    r"(?<![\w])(?:mustard[\s-]+powder|ground[\s-]+mustard|dry[\s-]+mustard)(?![\w])(?![\s-]+seeds?\b)", re.I)


@dataclass(frozen=True)
class MustardMention:
    instruction_step: int | None      # None for an ingredient line
    text: str
    origin: str                       # ingredient | instruction
    heated: bool
    after_cooking: bool

    def as_dict(self) -> dict:
        return {"instruction_step": self.instruction_step, "text": self.text, "origin": self.origin,
                "heated": self.heated, "after_cooking_words": self.after_cooking}


def mustard_mentions(facts) -> list[MustardMention]:
    out = [MustardMention(None, i.ingredient_name, "ingredient", False, False)
           for i in facts.ingredients if MUSTARD_RE.search(i.ingredient_name)]
    for st in parse_steps(facts.instructions):
        for seg in split_segments(st.text):
            m = MUSTARD_RE.search(seg)
            if m and not is_negated(seg, m.start()):
                r = read_segment(seg)
                out.append(MustardMention(st.number, seg, "instruction", bool(r.heat), bool(r.after)))
    return out


def restoration_timing(treatment: Treatment, mustards: list[MustardMention]) -> tuple[str, MustardMention | None]:
    """Does a valid mustard form come AFTER this ingredient's cooking?

    'restored'   a mustard mention with no heat, in a later step than the last heating of the
                 ingredient, or in the same step with an explicit after-cooking cue
    'unclear'    mustard is present but its timing against the cooking is not stated or is not after
    'absent'     no accepted mustard form in the recipe"""
    if not mustards:
        return "absent", None
    last_heat = max((m.instruction_step for m in treatment.heated), default=None)
    if last_heat is None:
        return "unclear", mustards[0]
    for m in mustards:
        if m.origin != "instruction" or m.heated:
            continue
        if m.instruction_step > last_heat or (m.instruction_step == last_heat and m.after_cooking):
            return "restored", m
    return "unclear", mustards[0]
