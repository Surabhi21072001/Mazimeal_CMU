#!/usr/bin/env python3
"""Who is eating, and how: the evaluation context.

RecipeFacts describes the RECIPE. This module describes the MEMBER and the INTENDED MEAL,
so the two are never mixed. An evaluation without a context behaves exactly as it did
before this module existed.

"Omitted" is not "empty"
------------------------
Every list-valued user field is `None` when the caller did not provide it and a tuple
(possibly empty) when they did:

    conditions=None   we were not told      -> a rule that needs it returns NEEDS_CONTEXT
    conditions=()     the caller says none  -> the absence of a condition may be relied on

The engine never turns `None` into `()`. A rule that says "avoid in iron overload" cannot
be answered by a request that simply left conditions out.

What the context may contain is limited to what a rule's own text asks for. Nothing in
this module logs or prints values: conditions and medications are health information.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


def normalize_token(value) -> str:
    """'Iron Overload', 'iron-overload' and ' IRON_OVERLOAD ' are the same token."""
    return re.sub(r"[\s\-]+", "_", str(value).strip().lower()).strip("_")


def _tokens(values) -> tuple[str, ...] | None:
    """None stays None (not provided); anything else becomes a tuple of normalised tokens."""
    if values is None:
        return None
    if isinstance(values, str):
        values = (values,)
    return tuple(t for t in (normalize_token(v) for v in values) if t)


@dataclass(frozen=True)
class MealContext:
    """The meal the member intends to eat. Never inferred from the recipe.

    intended_portions   servings the member will actually eat (2.0 = two servings)
    meal_position       free label such as 'breakfast' or 'last_meal_of_day'
    eating_sequence     food categories in the order they will be eaten, e.g.
                        ('non_starchy_vegetables', 'protein', 'starch')
    accompanying_foods  other foods eaten with the recipe
    post_meal_activity  what the member plans to do afterwards ('walk', 'none', ...);
                        an addition to the sketch, needed by GLY-010
    """
    intended_portions: float | None = None
    meal_position: str | None = None
    eating_sequence: tuple[str, ...] = ()
    accompanying_foods: tuple[str, ...] = ()
    post_meal_activity: str | None = None

    def __post_init__(self):
        if self.intended_portions is not None and not (self.intended_portions > 0):
            raise ValueError("intended_portions must be greater than zero")
        object.__setattr__(self, "eating_sequence", tuple(normalize_token(t) for t in self.eating_sequence))
        object.__setattr__(self, "accompanying_foods", tuple(str(t).strip().lower() for t in self.accompanying_foods))

    def as_dict(self) -> dict:
        return {
            "intended_portions": self.intended_portions,
            "meal_position": self.meal_position,
            "eating_sequence": list(self.eating_sequence),
            "accompanying_foods": list(self.accompanying_foods),
            "post_meal_activity": self.post_meal_activity,
        }


@dataclass(frozen=True)
class EvaluationContext:
    """The member and the intended meal. See the module docstring for None vs ().

    Deliberately NOT part of RecipeFacts, and never read from a profile that belongs to
    someone other than the member being evaluated.
    """
    member_id: str | None = None
    conditions: tuple[str, ...] | None = None
    medications: tuple[str, ...] | None = None
    supplements: tuple[str, ...] | None = None
    goals: tuple[str, ...] | None = None
    activity_level: str | None = None
    life_stage: str | None = None
    meal_context: MealContext | None = None
    # Equipment the caller says will be used ('cast iron skillet'). A statement about the meal,
    # not the member, so it does not make the evaluation personal.
    equipment: tuple[str, ...] | None = None

    def __post_init__(self):
        for name in ("conditions", "medications", "supplements", "goals", "equipment"):
            object.__setattr__(self, name, _tokens(getattr(self, name)))
        if self.activity_level is not None:
            object.__setattr__(self, "activity_level", normalize_token(self.activity_level))
        if self.life_stage is not None:
            object.__setattr__(self, "life_stage", normalize_token(self.life_stage))

    def has_member(self) -> bool:
        return self.member_id is not None

    def is_personal(self) -> bool:
        """True when the evaluation is for a particular person: a member id, or any
        member-level field supplied. A meal-only context is not personal."""
        return (self.member_id is not None
                or any(getattr(self, n) is not None
                       for n in ("conditions", "medications", "supplements", "goals",
                                 "activity_level", "life_stage")))

    def as_dict(self, include_health: bool = False) -> dict:
        """Safe summary. Conditions, medications and supplements are omitted unless asked
        for; only whether they were provided is reported."""
        out = {
            "member_id": self.member_id,
            "conditions_provided": self.conditions is not None,
            "medications_provided": self.medications is not None,
            "supplements_provided": self.supplements is not None,
            "goals_provided": self.goals is not None,
            "activity_level": self.activity_level,
            "meal_context": self.meal_context.as_dict() if self.meal_context else None,
        }
        if include_health:
            out.update(conditions=self.conditions, medications=self.medications,
                       supplements=self.supplements)
        return out

    def __repr__(self) -> str:                      # keeps health data out of logs and tracebacks
        return "EvaluationContext(member_id=%r, %s)" % (
            self.member_id,
            ", ".join("%s=%s" % (n, "provided" if getattr(self, n) is not None else "omitted")
                      for n in ("conditions", "medications", "supplements", "goals")))


# --------------------------------------------------------------------------
# Caution vocabulary
#
# Each concept below is something a rule's OWN limits text names. The alias lists are a
# proposed vocabulary: they have NOT had clinical review, which is why every result that
# depends on one says so (review_status). A condition that matches no alias is simply not
# recognised; the engine never infers a condition from anything else.
#
# effect:
#   not_applicable  the rule itself says to avoid it for these people
#   needs_context   the rule says individual or clinical constraints apply, so the engine
#                   will not decide
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class CautionConcept:
    concept: str
    aliases: frozenset[str]
    effect: str
    rule_text: str
    review_status: str = "proposed_not_clinically_reviewed"


def _concept(concept, aliases, effect, rule_text) -> CautionConcept:
    return CautionConcept(concept, frozenset(normalize_token(a) for a in aliases), effect, rule_text)


CAUTION_CONCEPTS: dict[str, CautionConcept] = {c.concept: c for c in (
    _concept("iron_overload", ("iron_overload", "hemochromatosis", "haemochromatosis"),
             "not_applicable", "SYN-012: population_scope 'avoid in iron overload'"),
    _concept("gi_condition", ("gi_condition", "ibs", "irritable_bowel_syndrome", "ibd", "crohns_disease",
                              "crohn_s_disease", "ulcerative_colitis", "colitis", "gastroparesis", "sibo"),
             "needs_context", "GLY-002: 'avoid abrupt high doses in users with GI conditions without review'"),
    _concept("kidney_disease", ("kidney_disease", "ckd", "chronic_kidney_disease", "renal_disease",
                                "protein_restricted_diet"),
             "needs_context", "GLY-003: 'kidney disease and protein prescriptions require clinical constraints'"),
    _concept("reflux", ("reflux", "gerd", "acid_reflux"),
             "needs_context", "GLY-009: vinegar 'can worsen reflux'; 'when tolerated'"),
    _concept("mobility_or_medical_limit", ("injury", "fall_risk", "cardiac_condition", "heart_disease",
                                           "exercise_restriction", "mobility_limitation"),
             "needs_context", "GLY-010: 'injury, fall risk, cardiac limits, or exercise restrictions need "
                              "individualized guidance'"),
    _concept("fat_handling_condition", ("gallbladder_disease", "gallstones", "cholecystitis", "pancreatitis",
                                        "pancreatic_insufficiency", "fat_malabsorption"),
             "needs_context", "INH-011: 'respect gallbladder, pancreatic, fat-malabsorption, and "
                              "prescribed-diet constraints'"),
    _concept("high_energy_need_or_vulnerable_stage",
             ("pregnancy", "pregnant", "lactation", "lactating", "child", "children", "older_adult",
              "athlete", "high_energy_needs"),
             "needs_context", "GLY-011: 'avoid underfeeding children, pregnancy, lactation, older adults, "
                              "athletes, or users with high energy needs'"),
)}


def _alias_matches(alias: str, token: str) -> bool:
    """Exact, or the token continues the alias after an underscore ('pregnancy_wk_12' for
    'pregnancy'). Never a bare substring: 'ibs' must not match 'gibson'."""
    return token == alias or token.startswith(alias + "_")


def matched_cautions(tokens, concepts) -> list[CautionConcept]:
    """Caution concepts (by name) whose aliases appear in `tokens`. `tokens` may be None."""
    if not tokens:
        return []
    return [CAUTION_CONCEPTS[c] for c in concepts
            if any(_alias_matches(a, t) for a in CAUTION_CONCEPTS[c].aliases for t in tokens)]
