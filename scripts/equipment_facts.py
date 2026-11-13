#!/usr/bin/env python3
"""Equipment as a fact: SYN-012 (iron cookware with moist acidic foods).

SYN-012's trigger is PROC_COOKWARE. It is not an ingredient property, and equipment is NEVER
derived from ingredients. A recipe's equipment comes from four places, each labelled:

  structured            a row in recipe_equipment stated by a structured import
  admin_review          a row a reviewer confirmed, or REJECTED to correct the extraction
  instruction_extraction  deterministic phrase matching over recipe_steps (this module)
  request_context       equipment the caller declares for this meal

Extraction rules, all deterministic:
  * whole words and phrases only; plural and hyphen/space variants allowed; 'pot' never matches
    'potato', and 'pot roast' and 'baking pan' are not cooking vessels;
  * a negated mention ('do not use a cast iron skillet') is not a mention;
  * every fact keeps the step number and the step text;
  * the ABSENCE of a mention proves nothing: no mention means 'not stated', never 'not used';
  * uncertain readings (a Dutch oven may be bare or enameled iron) are held at
    review_status 'pending_review', so a person can settle them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from derived_facts import DerivedFact, compile_phrases, is_negated, parse_steps


@dataclass(frozen=True)
class EquipmentDef:
    code: str
    phrases: tuple[str, ...]
    material: str                 # cast_iron | enameled_cast_iron | unknown | non_iron | unspecified
    confidence: str               # confidence of a runtime extraction
    review_status: str            # status of a runtime extraction


CAST_IRON = EquipmentDef("EQUIP_CAST_IRON", ("cast iron",), "cast_iron", "high", "auto")
ENAMELED = EquipmentDef("EQUIP_ENAMELED_CAST_IRON",
                        ("enameled cast iron", "enamelled cast iron", "enamel coated cast iron",
                         "enamel-coated cast iron", "enameled iron"), "enameled_cast_iron", "medium", "pending_review")
DUTCH_OVEN = EquipmentDef("EQUIP_DUTCH_OVEN", ("dutch oven",), "unknown", "low", "pending_review")
NON_IRON = EquipmentDef("EQUIP_NONIRON_COOKWARE",
                        ("nonstick", "non stick", "stainless steel", "aluminum", "aluminium", "ceramic", "copper"),
                        "non_iron", "high", "auto")
# Cooking vessels that name no material. Not evidence for or against iron.
VESSELS = ("skillet", "frying pan", "fry pan", "saute pan", "sauté pan", "saucepan", "sauce pan", "saucepot",
           "stockpot", "stock pot", "wok", "pot", "pan", "slow cooker", "crock pot", "crockpot",
           "pressure cooker", "casserole")
UNSPECIFIED = EquipmentDef("EQUIP_COOKWARE_UNSPECIFIED", VESSELS, "unspecified", "medium", "auto")

CATALOG = {d.code: d for d in (CAST_IRON, ENAMELED, DUTCH_OVEN, NON_IRON, UNSPECIFIED)}

_ENAMELED_RE = compile_phrases(ENAMELED.phrases)
_CAST_IRON_RE = compile_phrases(CAST_IRON.phrases)
_DUTCH_RE = compile_phrases(DUTCH_OVEN.phrases)
_MATERIAL_RE = compile_phrases(NON_IRON.phrases)
_VESSEL_RE = compile_phrases(VESSELS)
# Uses of these words that are not a cooking vessel: dishes, bakeware, techniques.
_NOT_A_VESSEL = re.compile(
    r"\b(?:baking|cake|loaf|muffin|pie|sheet|roasting|cookie|bundt|springform|brownie|tart|tube|bread|jelly[\s-]?roll)"
    r"[\s-]+pans?\b|\bpot[\s-]+(?:roast|pie|stickers?|holders?|liquor)\b|\bpotstickers?\b|\bhot[\s-]?pot\b"
    r"|\bpan[\s-]+(?:fry|fried|frying|seared?|roast(?:ed|ing)?|broil(?:ed|ing)?)\b", re.I)


def _scrub(text: str) -> str:
    """Replace non-vessel uses with spaces so a phrase match cannot land inside them."""
    return _NOT_A_VESSEL.sub(lambda m: " " * len(m.group(0)), text)


def _affirmed(pattern: re.Pattern, text: str) -> list[str]:
    return [m.group(0).lower() for m in pattern.finditer(text) if not is_negated(text, m.start())]


def extract_from_text(text: str) -> list[tuple[EquipmentDef, str]]:
    """Equipment named in one piece of text, as (definition, matched words).

    A material counts only next to a cooking vessel word ('stainless steel bowl' is not
    cookware), and a generic vessel is dropped when the same text names its material."""
    found: list[tuple[EquipmentDef, str]] = []
    # Enameled iron first, and removed, so its 'cast iron' is not read as bare cast iron.
    enameled = _affirmed(_ENAMELED_RE, text)
    rest = _ENAMELED_RE.sub(lambda m: " " * len(m.group(0)), text)
    for w in enameled:
        found.append((ENAMELED, w))
    cast = _affirmed(_CAST_IRON_RE, rest)
    for w in cast:
        found.append((CAST_IRON, w))
    if any(is_negated(rest, m.start()) for m in _CAST_IRON_RE.finditer(rest)):
        # 'Do not use a cast iron skillet' says what NOT to use; the skillet it names is not
        # a statement that a skillet is used, so nothing further is read from this text.
        return found
    for w in _affirmed(_DUTCH_RE, rest):
        found.append((DUTCH_OVEN, w))
    clean = _scrub(rest)
    vessels = _affirmed(_VESSEL_RE, clean)
    materials = _affirmed(_MATERIAL_RE, clean)
    if materials and vessels:
        found.append((NON_IRON, materials[0]))
    named_material = bool(enameled or cast or (materials and vessels))
    if vessels and not named_material:
        found.append((UNSPECIFIED, vessels[0]))
    return found


def _fact(defn: EquipmentDef, source: str, step: int | None, text: str | None, matched: str | None,
          confidence: str | None = None, review_status: str | None = None) -> DerivedFact:
    return DerivedFact(
        code="PROC_COOKWARE", source="equipment",
        value={"equipment_code": defn.code, "material": defn.material, "equipment_source": source,
               "review_status": review_status or defn.review_status, "matched": matched, "instruction_step": step},
        evidence=text, confidence=confidence or defn.confidence)


def equipment_candidate_facts(facts, context=None) -> list[DerivedFact]:
    """PROC_COOKWARE facts for the recipe's cookware, from every source, one per code and step.

    Order of precedence: a REJECTED stored row removes that code from extraction; stored rows
    are reported as stored; extraction fills in what the steps name; request context adds what
    the caller declares."""
    out: list[DerivedFact] = []
    stored = list(getattr(facts, "equipment", ()) or ())
    rejected = {e.equipment_code for e in stored if e.review_status == "rejected"}
    seen: set[tuple] = set()

    def add(f: DerivedFact):
        key = (f.value["equipment_code"], f.value["instruction_step"], f.value["equipment_source"])
        if key not in seen:
            seen.add(key)
            out.append(f)

    for row in stored:
        defn = CATALOG.get(row.equipment_code)
        if defn is None or row.review_status == "rejected":
            continue
        # A confirmed row is settled; anything else keeps the status it was stored with.
        add(_fact(defn, row.source, row.evidence_step, row.evidence_text, None,
                  confidence="high" if row.review_status == "confirmed" else row.confidence,
                  review_status=row.review_status))

    for st in parse_steps(facts.instructions):
        for defn, matched in extract_from_text(st.text):
            if defn.code not in rejected:
                add(_fact(defn, "instruction_extraction", st.number or None, st.text, matched))

    declared = getattr(context, "equipment", None)
    for phrase in declared or ():
        text = phrase.replace("_", " ")
        for defn, matched in extract_from_text(text):
            if defn.code not in rejected:
                add(_fact(defn, "request_context", None, "declared in the request: %s" % text, matched))
    return out
