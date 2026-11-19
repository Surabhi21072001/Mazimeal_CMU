#!/usr/bin/env python3
"""Inhibitor rules whose text supports a deterministic verdict: INH-005, INH-006, INH-007, plus the
guard for the four `do_not_automate` rules (INH-003, 008, 009, 010).

What each rule's STORED text supports (scripts/../schema/seed/business_rules.sql):

  INH-006  'Minimize heat, water, oxygen exposure, and long holding times.' / 'use fresh/raw where safe
           or brief low-water cooking; avoid long hot holding.'
           The text says 'brief' and 'long' and gives no number, so there is NO duration threshold in this
           code. VITC_PROLONGED_HEAT is explicit and UNSET: while it is unset a heated vitamin C
           ingredient is NEEDS_CONTEXT and APPLICABLE cannot be returned.
  INH-007  'Prefer brief steaming or restore myrosinase after cooking.' / 'If high-heat cooking is used,
           pair with mustard powder.' 'High-heat' is not defined, so MYROSINASE_HIGH_HEAT is a PROPOSED
           list that is UNREVIEWED and is never used for a verdict until it is marked reviewed.
  INH-005  'Frequent raw egg whites. Cook egg whites. Ordinary cooked egg intake is not a concern.'
           Cooked is decidable from the steps; 'frequent' is not decidable from one recipe, so a raw egg
           white is NEEDS_CONTEXT with frequency listed as missing and APPLICABLE is unreachable.

Every verdict is per ingredient first (scripts/ingredient_steps.py) and then aggregated:
APPLICABLE if any ingredient is confirmed applicable; otherwise NEEDS_CONTEXT if any is unresolved;
NOT_APPLICABLE only when every relevant ingredient is clearly handled appropriately.
"""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass

import ingredient_steps as IS
from derived_facts import DerivedFact, parse_steps, is_negated


def _ev():
    """evaluate_rules, imported late: it imports this module to register the evaluators."""
    import evaluate_rules
    return evaluate_rules


# --------------------------------------------------------------------------
# Reviewed configuration (explicit, and unset or unreviewed)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ProlongedHeatDefinition:
    """What counts as 'prolonged' heat for vitamin C (INH-006). Nothing is approved yet."""
    minutes_at_or_above: float | None = None      # a heated ingredient at or above this is prolonged
    methods: tuple[str, ...] = ()                 # methods that are prolonged whatever the time (e.g. 'slow_cook')
    review_status: str = "unset"                  # unset | reviewed
    source: str | None = None                     # who reviewed it, and on what evidence

    def usable(self) -> bool:
        return self.review_status == "reviewed" and (self.minutes_at_or_above is not None or bool(self.methods))

    def as_dict(self) -> dict:
        return {"minutes_at_or_above": self.minutes_at_or_above, "methods": list(self.methods),
                "review_status": self.review_status, "source": self.source, "usable": self.usable()}


@dataclass(frozen=True)
class HighHeatDefinition:
    """Which cooking methods are 'high-heat' for myrosinase (INH-007).

    `methods` is a PROPOSAL so a reviewer has something to approve or change; it is not used for any
    verdict until review_status is 'reviewed'."""
    methods: tuple[str, ...] = ("roast", "bake", "broil", "grill", "fry", "stir_fry", "saute", "sear")
    review_status: str = "unreviewed"             # unreviewed | reviewed
    source: str | None = None

    def usable(self) -> bool:
        return self.review_status == "reviewed" and bool(self.methods)

    def as_dict(self) -> dict:
        return {"methods": list(self.methods), "review_status": self.review_status, "source": self.source,
                "usable": self.usable()}


VITC_PROLONGED_HEAT = ProlongedHeatDefinition()
MYROSINASE_HIGH_HEAT = HighHeatDefinition()

OPEN_DECISIONS = {
    "INH-006": "Which duration or method is 'prolonged' for vitamin C, and whether the rule applies only when "
               "vitamin C optimization is the member's goal (the stored goal list cannot express it).",
    "INH-007": "Which cooking methods are 'high-heat' for myrosinase.",
    "INH-005": "How often raw egg white is eaten (meal history); one recipe cannot show 'frequent'.",
}


# --------------------------------------------------------------------------
# Shared result helpers
# --------------------------------------------------------------------------
def _step_texts(facts) -> dict[int, str]:
    return {s.number: s.text for s in parse_steps(facts.instructions)}


def _matched_steps(facts, treatments) -> tuple:
    ev = _ev()
    texts = _step_texts(facts)
    seen: dict[int, object] = {}
    for t in treatments:
        for m in t.mentions:
            if m.instruction_step not in seen:
                seen[m.instruction_step] = ev.MatchedStep(text=texts.get(m.instruction_step, m.segment),
                                                          step_number=m.instruction_step or None)
    return tuple(seen[k] for k in sorted(seen))


def _dedupe(missing: list[dict]) -> list[dict]:
    out, seen = [], set()
    for m in missing:
        key = (m["field"], m["reason"])
        if key not in seen:
            seen.add(key)
            out.append(m)
    return out


def _finish(c, per, checked, reason_prefix, evidence, steps, config_missing=()):
    """Aggregate per-ingredient judgements into one result. See the module docstring."""
    ev = _ev()
    S = ev.ApplicabilityStatus
    verdicts = [p["verdict"] for p in per]
    if "APPLICABLE" in verdicts:
        status = S.APPLICABLE
    elif "NEEDS_CONTEXT" in verdicts:
        status = S.NEEDS_CONTEXT
    else:
        status = S.NOT_APPLICABLE
    chosen = [p for p in per if p["verdict"] == status.value]
    n_each = {v: verdicts.count(v) for v in ("APPLICABLE", "NOT_APPLICABLE", "NEEDS_CONTEXT")}
    reason = "%s: %s (ingredients: %d applicable, %d not applicable, %d unresolved)." % (
        reason_prefix, chosen[0]["reason"], n_each["APPLICABLE"], n_each["NOT_APPLICABLE"], n_each["NEEDS_CONTEXT"])
    missing = _dedupe([m for p in per for m in p["missing"]] + list(config_missing)) \
        if status == S.NEEDS_CONTEXT else []
    resolved = status != S.NEEDS_CONTEXT
    passed = tuple(checked[:2]) if resolved or all(p["tied"] for p in per) else tuple(checked[:1])
    failed = (checked[2],) if status == S.APPLICABLE else ()
    if status == S.NOT_APPLICABLE:
        passed = tuple(checked)
    evidence = dict(evidence, aggregation="APPLICABLE wins; otherwise NEEDS_CONTEXT if any ingredient is unresolved; "
                                          "otherwise NOT_APPLICABLE only when every ingredient is handled appropriately",
                    ingredient_verdicts=n_each)
    result = ev._make(c, status, checked, passed, failed, reason, missing=missing, evidence=evidence)
    return dataclasses.replace(result, matched_steps=steps)


def _mention_evidence(t) -> list[dict]:
    return [m.as_dict() for m in t.mentions]


def _unresolved_by_association(t, what):
    """The judgement for an ingredient whose handling the steps do not establish, or None."""
    if t.state == "no_instructions":
        return dict(verdict="NEEDS_CONTEXT", tied=False,
                    reason="there are no instructions to show how %s is handled" % t.ingredient_name,
                    missing=[{"field": "recipe.instructions",
                              "reason": "%s needs the steps to see how %s is handled" % (what, t.ingredient_name)}])
    if t.state == "not_mentioned":
        return dict(verdict="NEEDS_CONTEXT", tied=False,
                    reason="no step names %s, so it is not assumed raw" % t.ingredient_name,
                    missing=[{"field": "recipe.instructions.ingredient_step",
                              "reason": "%s is not named in any step (aliases tried: %s); how it is handled is unknown "
                                        "and it is not assumed raw" % (t.ingredient_name, ", ".join(t.aliases))}])
    if t.state == "unresolved_mix":
        clear = next(m for m in t.mentions if m.role != "neutral")
        steps = ", ".join(str(m.instruction_step) for m in t.unresolved)
        return dict(verdict="NEEDS_CONTEXT", tied=True,
                    reason="%s is %s at step %s but is also named at step %s without saying how it is used"
                           % (t.ingredient_name, "used raw or after cooking" if clear.role != "heated" else "heated briefly",
                              clear.instruction_step, steps),
                    missing=[{"field": "recipe.instructions.ingredient_treatment",
                              "reason": "%s is also named at step %s without saying whether it is heated, raw or added after "
                                        "cooking, so the clear step at %s cannot decide for the whole ingredient"
                                        % (t.ingredient_name, steps, clear.instruction_step)}])
    if t.state == "neutral_only":
        steps = ", ".join(str(s) for s in t.steps)
        return dict(verdict="NEEDS_CONTEXT", tied=True,
                    reason="step %s names %s but nothing there says whether it is heated or used raw" % (steps, t.ingredient_name),
                    missing=[{"field": "recipe.instructions.ingredient_treatment",
                              "reason": "step %s names %s without saying whether it is heated, used raw or added after "
                                        "cooking" % (steps, t.ingredient_name)}])
    return None


def _first(mentions, role=None):
    return next((m for m in mentions if role is None or m.role == role), None)


# --------------------------------------------------------------------------
# INH-006  vitamin C: heat
# --------------------------------------------------------------------------
def _judge_vitc(t) -> dict:
    stop = _unresolved_by_association(t, "INH-006")
    base = dict(ingredient=t.ingredient_name, ingredient_id=t.ingredient_id, state=t.state,
                mentions=_mention_evidence(t))
    if stop:
        return {**base, **stop}
    if t.state == "raw":
        m = _first(t.mentions, "after_cooking") or _first(t.mentions, "raw")
        how = ("added after cooking (%s)" % ", ".join(m.reading.after)) if m.role == "after_cooking" else \
              ("used raw or as a garnish (%s)" % ", ".join(m.reading.raw))
        return {**base, "verdict": "NOT_APPLICABLE", "tied": True,
                "reason": "%s is %s at step %s" % (t.ingredient_name, how, m.instruction_step), "missing": []}
    if t.state == "brief_heat":
        m = t.heated[0]
        return {**base, "verdict": "NOT_APPLICABLE", "tied": True, "brief_words": list(m.reading.brief),
                "methods": list(m.reading.methods),
                "reason": "%s is heated only briefly (step %s: '%s')" % (
                    t.ingredient_name, m.instruction_step, ", ".join(m.reading.brief)), "missing": []}
    return {**base, **_judge_heated_vitc(t)}


def _judge_heated_vitc(t) -> dict:
    cfg = VITC_PROLONGED_HEAT
    heated = t.heated
    methods = sorted({x for m in heated for x in m.reading.methods})
    durations = [d for m in heated for d in m.reading.durations]
    step = heated[0].instruction_step
    detail = dict(methods=methods, durations=[d.as_dict() for d in durations], tied=True,
                  also_raw_or_after_cooking=t.mixed)
    where = "step %s (%s%s)" % (", ".join(str(m.instruction_step) for m in heated), "/".join(methods) or "heat",
                                ", " + durations[0].text if durations else "")
    if not cfg.usable():
        return {**detail, "verdict": "NEEDS_CONTEXT",
                "reason": "%s is heated at %s and no reviewed definition of prolonged heat exists" % (t.ingredient_name, where),
                "missing": [{"field": "reviewed_definition.vitamin_c_prolonged_heat",
                             "reason": "INH-006 says to minimize prolonged heat but gives no duration or method; "
                                       "VITC_PROLONGED_HEAT is %s. %s is heated at %s"
                                       % (cfg.review_status, t.ingredient_name, where)}]}
    if t.mixed:
        return {**detail, "verdict": "NEEDS_CONTEXT",
                "reason": "%s is heated in one step and used raw or added after cooking in another" % t.ingredient_name,
                "missing": [{"field": "recipe.instructions.ingredient_split",
                             "reason": "%s is both heated and used raw/after cooking; which portion is meant is unclear"
                                       % t.ingredient_name}]}
    if set(methods) & set(cfg.methods):
        return {**detail, "verdict": "APPLICABLE",
                "reason": "%s is cooked by a method defined as prolonged (%s) at %s" % (
                    t.ingredient_name, ", ".join(sorted(set(methods) & set(cfg.methods))), where), "missing": []}
    if cfg.minutes_at_or_above is not None:
        known = [d for d in durations if d.minutes_low is not None]
        if any(d.minutes_low >= cfg.minutes_at_or_above for d in known):
            return {**detail, "verdict": "APPLICABLE",
                    "reason": "%s is heated for %s, at or above the reviewed %g minutes (%s)" % (
                        t.ingredient_name, known[0].text, cfg.minutes_at_or_above, where), "missing": []}
        if known and len(known) == len(durations) and all(d.minutes_high < cfg.minutes_at_or_above for d in known):
            return {**detail, "verdict": "NOT_APPLICABLE",
                    "reason": "%s is heated for less than the reviewed %g minutes (%s)" % (
                        t.ingredient_name, cfg.minutes_at_or_above, where), "missing": []}
    return {**detail, "verdict": "NEEDS_CONTEXT",
            "reason": "%s is heated at %s but its duration or method cannot be classified" % (t.ingredient_name, where),
            "missing": [{"field": "recipe.instructions.heating_duration",
                         "reason": "%s is heated at step %s without a duration that can be compared with the reviewed "
                                   "definition" % (t.ingredient_name, step)}]}


def evaluate_inh_006(c, facts, pf) -> object:
    """Vitamin C foods: keep heat, water, oxygen and holding time down.

    Per ingredient, from its own steps (see the module docstring). Raw, garnish, added after cooking and
    explicitly brief heating are NOT_APPLICABLE; an ingredient the steps do not tie down, or heating that
    cannot be classified by a reviewed definition, is NEEDS_CONTEXT; APPLICABLE needs a reviewed
    definition, which does not exist yet. Not gated on a member goal (an open product decision)."""
    checked = ("a vitamin C ingredient is present", "each vitamin C ingredient is tied to an instruction step",
               "no prolonged heat exposure")
    ts = IS.treatments_for(facts, "NUT_VITC")
    ev = _ev()
    if not ts:
        return ev._needs_context(c, checked, "No ingredient line carries the vitamin C tag, so there is nothing to follow into the steps.",
                                 missing=[{"field": "recipe.ingredients.NUT_VITC",
                                           "reason": "no ingredient of this recipe is tagged as a vitamin C food"}])
    per = [_judge_vitc(t) for t in ts]
    evidence = {"ingredients": per, "prolonged_heat_definition": VITC_PROLONGED_HEAT.as_dict(),
                "goal_gating": "not applied: the member goal list cannot express vitamin C optimization (open decision)",
                "storage": "not evaluated: storage time is not part of a recipe's steps"}
    return _finish(c, per, checked, "Vitamin C", evidence, _matched_steps(facts, ts))


# --------------------------------------------------------------------------
# INH-007  crucifers: myrosinase
# --------------------------------------------------------------------------
def _judge_crucifer(t, mustards) -> dict:
    stop = _unresolved_by_association(t, "INH-007")
    base = dict(ingredient=t.ingredient_name, ingredient_id=t.ingredient_id, state=t.state,
                mentions=_mention_evidence(t))
    if stop:
        return {**base, **stop}
    if t.state == "raw":
        m = _first(t.mentions, "after_cooking") or _first(t.mentions, "raw")
        return {**base, "verdict": "NOT_APPLICABLE", "tied": True,
                "reason": "%s is used raw or added after cooking (step %s)" % (t.ingredient_name, m.instruction_step),
                "missing": []}
    heated = t.heated
    methods = sorted({x for m in heated for x in m.reading.methods})
    where = "step %s (%s)" % (", ".join(str(m.instruction_step) for m in heated), "/".join(methods) or "heat")
    detail = dict(methods=methods, tied=True, durations=[d.as_dict() for m in heated for d in m.reading.durations])
    if t.state == "brief_heat" and set(methods) <= {"steam"} and methods:
        m = heated[0]
        return {**base, **detail, "verdict": "NOT_APPLICABLE", "brief_words": list(m.reading.brief),
                "reason": "%s is steamed briefly (step %s: '%s')" % (t.ingredient_name, m.instruction_step, ", ".join(m.reading.brief)),
                "missing": []}
    timing, mention = IS.restoration_timing(t, mustards)
    mus = [m.as_dict() for m in mustards]
    if timing == "restored":
        return {**base, **detail, "verdict": "NOT_APPLICABLE", "restoration": {"timing": timing, "mustard": mention.as_dict()},
                "reason": "%s is heated at %s and mustard powder is added afterwards (step %s)" % (
                    t.ingredient_name, where, mention.instruction_step), "missing": []}
    if timing == "unclear":
        return {**base, **detail, "verdict": "NEEDS_CONTEXT", "restoration": {"timing": timing, "mustard": mus},
                "reason": "%s is heated at %s and an accepted mustard form is present but not clearly added after cooking" % (
                    t.ingredient_name, where),
                "missing": [{"field": "recipe.instructions.mustard_timing",
                             "reason": "mustard powder is present but the steps do not show it added after %s is cooked "
                                       "(or it is only in the ingredient list)" % t.ingredient_name}]}
    cfg = MYROSINASE_HIGH_HEAT
    if cfg.usable():
        if set(methods) & set(cfg.methods):
            return {**base, **detail, "verdict": "APPLICABLE", "restoration": {"timing": timing},
                    "reason": "%s is cooked by a reviewed high-heat method (%s) at %s with no mustard powder added after"
                              % (t.ingredient_name, ", ".join(sorted(set(methods) & set(cfg.methods))), where), "missing": []}
        return {**base, **detail, "verdict": "NEEDS_CONTEXT", "restoration": {"timing": timing},
                "reason": "%s is heated at %s by a method not classified in the reviewed list" % (t.ingredient_name, where),
                "missing": [{"field": "reviewed_definition.myrosinase_high_heat_methods",
                             "reason": "method(s) %s are not in the reviewed high-heat list" % ", ".join(methods)}]}
    proposed = sorted(set(methods) & set(cfg.methods))
    return {**base, **detail, "verdict": "NEEDS_CONTEXT", "restoration": {"timing": timing},
            "method_in_unreviewed_list": proposed,
            "reason": "%s is heated at %s and no reviewed list of high-heat methods exists" % (t.ingredient_name, where),
            "missing": [{"field": "reviewed_definition.myrosinase_high_heat_methods",
                         "reason": "INH-007 says 'if high-heat cooking is used' without defining it; MYROSINASE_HIGH_HEAT is "
                                   "%s. %s is heated at %s" % (cfg.review_status, t.ingredient_name, where)}]}


def evaluate_inh_007(c, facts, pf) -> object:
    """Cruciferous vegetables: prefer brief steaming, or restore myrosinase after cooking.

    NOT_APPLICABLE: raw or added after cooking; brief steaming (the words 'briefly'/'quickly' with
    steaming); or heated with mustard powder / ground mustard / dry mustard added afterwards with clear
    timing. NEEDS_CONTEXT: anything else heated, because 'high-heat' is undefined and its candidate list is
    unreviewed. APPLICABLE is unreachable until that list is reviewed."""
    checked = ("a cruciferous ingredient is present", "each cruciferous ingredient is tied to an instruction step",
               "myrosinase is not lost to high heat")
    ts = IS.treatments_for(facts, "ING_CRUCIFER")
    ev = _ev()
    if not ts:
        return ev._needs_context(c, checked, "No ingredient line carries the crucifer tag, so there is nothing to follow into the steps.",
                                 missing=[{"field": "recipe.ingredients.ING_CRUCIFER",
                                           "reason": "no ingredient of this recipe is tagged as a cruciferous vegetable"}])
    mustards = IS.mustard_mentions(facts)
    per = [_judge_crucifer(t, mustards) for t in ts]
    evidence = {"ingredients": per, "mustard_mentions": [m.as_dict() for m in mustards],
                "accepted_mustard_forms": ["mustard powder", "ground mustard", "dry mustard"],
                "high_heat_definition": MYROSINASE_HIGH_HEAT.as_dict()}
    return _finish(c, per, checked, "Cruciferous vegetables", evidence, _matched_steps(facts, ts))


# --------------------------------------------------------------------------
# INH-005  raw egg white
# --------------------------------------------------------------------------
EGG_WHITE_RE = re.compile(r"(?<![\w])egg[\s-]+whites?(?![\w])", re.I)
RAW_EGG_RE = re.compile(r"(?<![\w])(?:raw|uncooked)[\s-]+(?:whole[\s-]+)?eggs?(?![\w])", re.I)
PASTEURIZED_RE = re.compile(r"(?<![\w])(?:pasteuri[sz]ed|carton|cartoned|liquid[\s-]+egg)(?![\w])", re.I)


@dataclass(frozen=True)
class EggMention:
    subject: str                  # egg_white | raw_whole_egg
    origin: str                   # ingredient | instruction
    instruction_step: int | None
    text: str
    pasteurized: bool
    reading: object | None        # SegmentReading for an instruction mention
    cooked_cue: str | None = None  # the heat word tied directly to the egg white, if any

    def state(self) -> str:
        """cooked | raw | unclear. Only explicit words decide; a negated heat word decides nothing.

        COOKED needs a heat word directly before the egg ('scramble the egg whites', 'hard-boiled egg whites').
        A cooking word elsewhere in the segment ('fold the egg whites into the baked crust') is not tied to the
        egg, so it does not count: a false 'cooked' would be a wrong NOT_APPLICABLE."""
        if self.reading is None:
            return "unclear"
        if self.cooked_cue:
            return "cooked"
        if self.subject == "raw_whole_egg" or self.reading.raw:
            return "raw"
        return "unclear"

    def as_dict(self) -> dict:
        r = self.reading
        return {"subject": self.subject, "origin": self.origin, "instruction_step": self.instruction_step,
                "text": self.text, "pasteurized": self.pasteurized, "state": self.state(),
                "cooked_cue": self.cooked_cue, "heat_words": list(r.heat) if r else [],
                "raw_words": list(r.raw) if r else [], "negated_heat_words": list(r.negated_heat) if r else []}


def _cooked_cue(segment: str, subject_start: int) -> str | None:
    """A non-negated heat word at the start of the segment (within three words) and no more than one word
    before the egg: an imperative ('Gently scramble the egg whites') or a participle ('hard-boiled egg whites')."""
    blank = lambda m: " " * len(m.group(0))
    scrubbed = IS._NOT_HEAT.sub(blank, IS._AFTER_RE.sub(blank, segment))
    for m in IS._HEAT_RE.finditer(scrubbed):
        if m.end() > subject_start or is_negated(scrubbed, m.start()):
            continue
        if len(scrubbed[:m.start()].split()) <= 3 and len(scrubbed[m.end():subject_start].split()) <= 1:
            return m.group(0).lower()
    return None


def egg_mentions(facts) -> list[EggMention]:
    out = [EggMention("egg_white", "ingredient", None, i.ingredient_name,
                      bool(PASTEURIZED_RE.search(i.ingredient_name)), None)
           for i in facts.ingredients if EGG_WHITE_RE.search(i.ingredient_name)]
    for st in parse_steps(facts.instructions):
        for seg in IS.split_segments(st.text):
            reading = IS.read_segment(seg)
            for pat, name in ((EGG_WHITE_RE, "egg_white"), (RAW_EGG_RE, "raw_whole_egg")):
                m = pat.search(seg)
                if not m:
                    continue
                # 'Do not use egg whites' removes the egg; 'Do not cook the egg whites' does not.
                if is_negated(seg, m.start()) and not reading.negated_heat:
                    continue
                out.append(EggMention(name, "instruction", st.number, seg, bool(PASTEURIZED_RE.search(seg)),
                                      reading, _cooked_cue(seg, m.start())))
                break
    return out


def inhibitor_candidate_facts(facts, context=None) -> list[DerivedFact]:
    """ING_RAW_EGG_WHITE, from the recipe's own text: an egg WHITE named in an ingredient or a step, or a
    whole egg explicitly called raw. It is never an ingredient tag, and a plain 'eggs' calls nothing
    (BIO-011 covers whole eggs). The state (raw, cooked, unclear) is decided by the evaluator."""
    return [DerivedFact(code="ING_RAW_EGG_WHITE", source="recipe_process",
                        value={"subject": m.subject, "origin": m.origin, "instruction_step": m.instruction_step,
                               "pasteurized": m.pasteurized},
                        evidence=m.text, confidence="medium")
            for m in egg_mentions(facts)]


def evaluate_inh_005(c, facts, pf) -> object:
    """Raw egg white (avidin binds biotin; the concern is FREQUENT raw intake). Action: cook egg whites.

    NOT_APPLICABLE every mention is explicitly cooked ('Ordinary cooked egg intake is not a concern').
    NEEDS_CONTEXT  a raw mention (frequency is missing: one recipe cannot show 'frequent'), or a state the
                   steps leave unclear, or no egg white named.
    APPLICABLE     unreachable: it needs meal-history frequency, which does not exist yet.
    Pasteurization is recorded but changes nothing: it addresses microbes, and the rule says nothing about it."""
    ev = _ev()
    checked = ("an egg white is named", "its state is stated", "the egg white is cooked")
    ms = egg_mentions(facts)
    evidence = {"egg_mentions": [m.as_dict() for m in ms],
                "frequency": "not available: INH-005 is about frequent raw intake and no meal history exists"}
    if not ms:
        return ev._needs_context(c, checked, "No egg white is named in the ingredients or steps, and a whole egg's state is not assumed.",
                                 missing=[{"field": "recipe.instructions.egg_white_state",
                                           "reason": "the recipe does not say whether egg white is used raw or cooked"}],
                                 evidence=evidence)
    # Only what the STEPS say can decide the state. An ingredient-list line says an egg white is
    # present, not what is done to it.
    ms_steps = [m for m in ms if m.origin == "instruction"]
    states = [m.state() for m in ms_steps]
    note = " (pasteurized product: this addresses microbes, not the rule's concern)" if any(m.pasteurized for m in ms) else ""
    steps = tuple(ev.MatchedStep(text=_step_texts(facts).get(m.instruction_step, m.text), step_number=m.instruction_step)
                  for m in ms if m.instruction_step)
    if "raw" in states:
        m = ms_steps[states.index("raw")]
        r = ev._needs_context(
            c, checked, "Egg white is used raw at step %s%s; whether that is frequent is not known." % (m.instruction_step, note),
            missing=[{"field": "meal_history.raw_egg_white_frequency",
                      "reason": "INH-005 concerns frequent raw egg white; one recipe cannot show how often it is eaten"}],
            evidence=evidence, passed=checked[:2], failed=(checked[2],))
        return dataclasses.replace(r, matched_steps=steps)
    if states and all(s == "cooked" for s in states):
        r = ev._make(c, ev.ApplicabilityStatus.NOT_APPLICABLE, checked, checked, (),
                     "Every mention of egg white is cooked; ordinary cooked egg intake is not a concern%s." % note, evidence=evidence)
        return dataclasses.replace(r, matched_steps=steps)
    unclear = [m for m in ms_steps if m.state() == "unclear"] or ms
    where = ("step %s" % unclear[0].instruction_step) if unclear[0].instruction_step else "the ingredient list"
    r = ev._needs_context(
        c, checked, "Egg white is named at %s but the steps do not say whether it is cooked or raw%s." % (where, note),
        missing=[{"field": "recipe.instructions.egg_white_state",
                  "reason": "egg white at %s has no explicit cooking or raw wording" % where}],
        evidence=evidence, passed=checked[:1], failed=(checked[1],))
    return dataclasses.replace(r, matched_steps=steps)


# --------------------------------------------------------------------------
# do_not_automate rules: INH-003, INH-008, INH-009, INH-010
# --------------------------------------------------------------------------
def _provided(values) -> str:
    return "omitted" if values is None else ("empty" if len(values) == 0 else "provided")


def evaluate_manual_advisory(c, facts, pf, ctx=None) -> object:
    """A rule the workbook marks do_not_automate. It never produces an automatic verdict.

    Nothing about medication or supplements is inferred from the recipe, and no interaction logic exists.
    If one of these rules is ever called, the result says it is a manual advisory. The evidence reports only
    WHETHER member medication and supplement lists were omitted, empty or provided; never their contents."""
    ev = _ev()
    checked = ("the rule may be automated",)
    context = {"medications": _provided(getattr(ctx, "medications", None)),
               "supplements": _provided(getattr(ctx, "supplements", None))}
    evidence = {"manual_advisory": True, "automation_status": c.automation_status, "instruction": c.recipe_engine_instruction,
                "member_context": context,
                "note": "no interaction logic is implemented; medication and supplement use is never inferred from ingredients"}
    return ev._needs_context(
        c, checked,
        "%s is a manual advisory (%s): it is routed to clinician or supplement review, not decided automatically."
        % (c.rule_id, c.automation_status),
        missing=[{"field": "manual_review",
                  "reason": "%s: %s" % (c.rule_id, c.action or c.recipe_engine_instruction or "flag for review")}],
        evidence=evidence, failed=checked)


evaluate_manual_advisory.takes_context = True

EVALUATORS = {
    "INH-005": evaluate_inh_005,
    "INH-006": evaluate_inh_006,
    "INH-007": evaluate_inh_007,
    "INH-003": evaluate_manual_advisory,
    "INH-008": evaluate_manual_advisory,
    "INH-009": evaluate_manual_advisory,
    "INH-010": evaluate_manual_advisory,
}
