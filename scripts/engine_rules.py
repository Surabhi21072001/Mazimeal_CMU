#!/usr/bin/env python3
"""Engine-level rules: INH-012 (competing optimizer goals).

INH-012 is not about food. Its own text calls it 'an engineering safety rule', and its instruction
is to 'run conflict checks' so the optimizer does not 'maximize one nutrient without checking
tradeoffs' (example: cooking tomatoes can raise lycopene bioavailability while lowering vitamin C
retention). It therefore cannot be triggered by an ingredient, a nutrient or a step. It is a
question about the OTHER rules' results, so it runs in a second stage, after every ordinary
candidate rule has been evaluated:

    primary_results = evaluate_primary_rules(...)
    engine_results  = evaluate_engine_rules(facts, context, primary_results)

What it does and does not do
----------------------------
  * It reads the primary results and never changes them. They are frozen dataclasses and the
    list is not modified; the engine result is a new, separate entry.
  * It FLAGS a tradeoff. The rule says to check, not to choose, so it suppresses nothing and
    re-ranks nothing. The result states that explicitly (`suppressed_rules` and
    `priority_changes` are always present and empty) so a future change that does alter a
    primary result has to say so in the same place.
  * It records which primary results caused it to run.
  * It runs once. Its own result is never an input (engine rules are filtered out of the
    primary results it reads), so it cannot call itself.

Which pairs conflict is data, in CONFLICT_PAIRS, not code. The list holds only what the rule's
own text names. Adding a pair is a reviewed configuration change; nothing is inferred.
"""
from __future__ import annotations

from dataclasses import dataclass

from derived_facts import DerivedFact

ENGINE_RULE_IDS = frozenset({"INH-012"})
ENGINE_TRIGGER_CODE = "RULE_CONFLICT"


@dataclass(frozen=True)
class ConflictPair:
    """Two primary rules whose recommendations pull in opposite directions."""
    members: tuple[str, str]       # primary rule ids, sorted
    shared_process: str            # what both act on
    effect: str                    # the tradeoff, in words
    source: str                    # where the pair comes from
    review_status: str = "wording"  # taken directly from the rule's text; no inference

    def __post_init__(self):
        if tuple(sorted(self.members)) != tuple(self.members) or len(set(self.members)) != 2:
            raise ValueError("members must be two distinct rule ids in sorted order")

    def as_dict(self) -> dict:
        return {"members": list(self.members), "shared_process": self.shared_process,
                "effect": self.effect, "source": self.source, "review_status": self.review_status}


CONFLICT_PAIRS: tuple[ConflictPair, ...] = (
    ConflictPair(
        members=("BIO-003", "INH-006"),
        shared_process="cooking tomatoes",
        effect="cooking tomatoes with fat raises lycopene bioavailability (BIO-003) while heat lowers vitamin C "
               "retention (INH-006)",
        source="INH-012 recipe_engine_instruction: 'tomato cooking may increase lycopene bioavailability while "
               "lowering vitamin C retention'"),
)

_METADATA = ("rule_id", "rule_name", "automation_status", "trigger_code", "rule_category", "rule_type",
             "evidence_tier", "target_code", "target_nutrient_or_outcome", "action", "recipe_engine_instruction",
             "mechanism", "conditions_and_limits", "source_title", "source_url")


def _load_rule(conn, rule_id):
    """INH-012's DetectedRule from business_rules (active only), or None."""
    import detect_rules as D
    cur = conn.cursor()
    try:
        cur.execute(D._q(conn, "SELECT %s FROM business_rules WHERE rule_id = ? AND is_active = TRUE"
                         % ", ".join(_METADATA)), (rule_id,))
        row = cur.fetchone()
        meta = dict(zip(_METADATA, row)) if row else None
    except Exception:
        if hasattr(conn, "rollback"):
            conn.rollback()
        cur = conn.cursor()
        cur.execute(D._q(conn, "SELECT rule_id, rule_name, automation_status, trigger_code FROM business_rules "
                               "WHERE rule_id = ? AND is_active = TRUE"), (rule_id,))
        row = cur.fetchone()
        meta = dict(zip(("rule_id", "rule_name", "automation_status", "trigger_code"), row)) if row else None
    return meta


def conflicts_present(primary_results, pairs=None):
    """Configured pairs whose members were BOTH called as ordinary candidates, in a stable order.

    A member that was never a candidate cannot conflict; it is simply absent."""
    pairs = CONFLICT_PAIRS if pairs is None else pairs
    index = {r.rule_id: r for r in primary_results if r.rule_id not in ENGINE_RULE_IDS}
    return [(p, index[p.members[0]], index[p.members[1]])
            for p in sorted(pairs, key=lambda p: p.members) if p.members[0] in index and p.members[1] in index]


def pair_state(a, b) -> str:
    """'conflict' both recommendations are live; 'none' one is not being recommended;
    'undetermined' at least one has no decision yet."""
    statuses = {str(a.applicability_status), str(b.applicability_status)}
    if "NOT_APPLICABLE" in statuses:
        return "none"
    if statuses == {"APPLICABLE"}:
        return "conflict"
    return "undetermined"


def evaluate_engine_rules(conn, facts, context, primary_results, pairs=None):
    """The engine-level results for a set of primary results. Returns a new list; the input is
    not modified. Empty when no configured pair has both members among the primary results."""
    import evaluate_rules as ev
    from evaluate_rules import ApplicabilityStatus as S

    found = conflicts_present(primary_results, pairs)
    if not found:
        return []
    meta = _load_rule(conn, "INH-012")
    if meta is None or meta.get("trigger_code") != ENGINE_TRIGGER_CODE:
        return []

    triggers = []
    for pair, a, b in found:
        triggers.append(DerivedFact(
            code=ENGINE_TRIGGER_CODE, source="engine_result",
            value={"rules": list(pair.members), "state": pair_state(a, b),
                   "statuses": {a.rule_id: str(a.applicability_status), b.rule_id: str(b.applicability_status)},
                   "shared_process": pair.shared_process},
            evidence="%s (%s) and %s (%s) both act on %s" % (
                a.rule_id, a.applicability_status, b.rule_id, b.applicability_status, pair.shared_process),
            confidence="high"))
    rule = ev.DetectedRule(
        reason="engine-level check over primary results: " + "; ".join(t.evidence for t in triggers),
        trigger_source="engine_result", matched_facts=tuple(triggers), **meta)

    checked = ("a configured conflict pair is present among the primary results",
               "both rules of the pair have a decision", "both recommendations are live")
    states = [t.value["state"] for t in triggers]
    evidence = {
        "triggered_by": [{"rule_id": r.rule_id, "applicability_status": str(r.applicability_status),
                          "trigger_code": r.trigger_code}
                         for _, a, b in found for r in (a, b)],
        "pairs": [{**p.as_dict(), "state": pair_state(a, b)} for p, a, b in found],
        # The rule asks for a check, not a choice: no primary result is suppressed or re-ranked.
        "suppressed_rules": [],
        "priority_changes": [],
        "annotations": [{"rule_ids": list(p.members), "note": "check the tradeoff: " + p.effect}
                        for p, a, b in found if pair_state(a, b) != "none"],
    }

    if "conflict" in states:
        live = [t for t in triggers if t.value["state"] == "conflict"]
        result = ev._make(rule, S.APPLICABLE, checked, checked, (),
            "Competing goals: %s. Check the tradeoff before maximizing either." % live[0].value["shared_process"]
            + " " + [p.effect for p, a, b in found if pair_state(a, b) == "conflict"][0],
            evidence=evidence)
    elif "undetermined" in states:
        missing = []
        for p, a, b in found:
            for r in (a, b):
                if str(r.applicability_status) == "NEEDS_CONTEXT":
                    missing.append({"field": "primary_results.%s" % r.rule_id,
                                    "reason": "%s has no decision yet (%s), so whether it conflicts with %s cannot "
                                              "be decided" % (r.rule_id, r.reason, [m for m in p.members if m != r.rule_id][0])})
        result = ev._make(rule, S.NEEDS_CONTEXT, checked, checked[:1], checked[1:2],
            "A configured conflict pair is present but at least one of its rules has no decision yet.",
            missing=missing, evidence=evidence)
    else:
        result = ev._make(rule, S.NOT_APPLICABLE, checked, checked[:2], checked[2:],
            "A configured pair is present but one of its recommendations is not being made, so nothing competes.",
            evidence=evidence)
    return [ev._enrich(result, rule, facts, {})]
