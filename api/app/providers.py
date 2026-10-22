"""
Who writes the suggestion text on the cook screen.

Three implementations behind one signature, chosen by MAZI_PROVIDER:

    template   the rule's own words, rearranged. No model is called, so
               nothing can be invented. This is the default and the fallback.
    local      a small local model rephrases the template output. The rules
               still supply every fact; the model only changes the wording.
    api        a hosted model, for the small-versus-large comparison.

Every implementation returns the same shape, and every suggestion carries the
rule it came from and that rule's source. A model that adds a number the rule
did not contain is discarded and the template output is used instead.
"""
from __future__ import annotations

import httpx

from . import config
from .validate import borrowed_numbers, looks_like_prose

# Rules that describe a change the cook can make come first; a rule that is
# already satisfied is an explanation, not a suggestion. needs_review rules are
# for the reviewer console and never reach the cook screen.
ORDER = {"not_satisfied": 0, "advisory": 1, "satisfied": 2}
HIDDEN = {"needs_review"}

# Length is deliberately not capped. Capping it while also demanding full
# coverage is a contradiction, and a 4B model resolves that by dropping a rule
# rather than compressing - measured, not assumed. The card collapses instead.
SUMMARY_SYSTEM = (
    "You write a short piece of advice telling a home cook what matters about this recipe "
    "nutritionally. You are given every rule that applies to it. "
    "Every rule must be mentioned; none may be left out. Write them as connected advice, "
    "not a list. "
    "Keep every fact; invent nothing; never add a number, a percentage, a duration or a "
    "nutrition claim that is not already there. "
    "Start with the advice itself: no preamble, no greeting, no heading, no quotation marks, "
    "and never say what you are about to do."
)

SYSTEM = (
    "You rewrite one cooking tip so a home cook will read it. "
    "Rules: keep every fact from the input; invent nothing; never add a number, "
    "a percentage, a duration or a nutrition claim that is not already there; "
    "no greeting, no sign-off; one or two sentences, under 35 words; plain words."
)


def _headline(rule: dict) -> str:
    name = rule.get("name") or rule.get("rule_id", "")
    return name[0].upper() + name[1:] if name else "Suggestion"


def template_suggestions(recipe: dict, rule_ids: list[str] | None = None) -> list[dict]:
    """The rule's own sentences, in the order a cook would want them."""
    rules = [r for r in recipe.get("matched_rules", []) if r.get("status") not in HIDDEN]
    if rule_ids:
        rules = [r for r in rules if r["rule_id"] in rule_ids]
    rules.sort(key=lambda r: ORDER.get(r.get("status"), 9))

    out = []
    for rule in rules:
        body = rule.get("engine_action") or ""
        why = rule.get("why")
        if why:
            body = f"{body} {why}"
        out.append(
            {
                "rule_id": rule["rule_id"],
                "headline": _headline(rule),
                "body": body.strip(),
                "evidence_tier": rule.get("evidence_tier"),
                "source_url": rule.get("source_url"),
                "status": rule.get("status"),
            }
        )
    return out


# Words worth more than "the" when checking whether a rule made it into the
# summary: the ingredient or technique the rule is actually about.
STOPWORDS = {
    "the", "and", "with", "from", "that", "this", "them", "they", "your", "into",
    "then", "when", "before", "after", "about", "keep", "same", "meal", "have",
    "which", "while", "their", "there", "where", "well", "away", "more", "than",
}


def _keywords(rule: dict) -> list[str]:
    text = f"{rule.get('engine_action', '')} {rule.get('name', '')}".lower()
    words = {w.strip(".,;:()") for w in text.split() if len(w) > 4}
    return sorted(w for w in words if w not in STOPWORDS)


PREAMBLE = ("okay", "sure", "here's", "here is", "certainly", "of course", "below is")


def strip_preamble(text: str) -> str:
    """Drop the "Okay, here's a paragraph:" opener some models insist on.

    Asking for no preamble helps but does not always work, so the first line is
    removed when it announces the answer instead of being it.
    """
    cleaned = (text or "").strip().strip('"').strip("“”")
    parts = [p for p in cleaned.split("\n") if p.strip()]
    if parts and parts[0].rstrip().endswith(":") and parts[0].lower().startswith(PREAMBLE):
        parts = parts[1:]
    cleaned = " ".join(p.strip() for p in parts).strip().strip('"').strip("“”")
    return cleaned


def _distinctive(rule: dict, others: list[dict]) -> list[str]:
    """Words that belong to this rule and no other one on the recipe.

    "chickpeas" appears in two of the falafel's rules, so finding it proves
    nothing about which of them the summary covered. "soak" and "phytate" only
    belong to one.
    """
    shared = set()
    for other in others:
        if other.get("rule_id") != rule.get("rule_id"):
            shared.update(_keywords(other))
    return [w for w in _keywords(rule) if w not in shared]


def _mentions(summary: str, rule: dict, others: list[dict]) -> bool:
    lowered = summary.lower()
    words = _distinctive(rule, others) or _keywords(rule)
    if not words:
        return True
    # stem-ish match so "soaking" counts for "soak"
    return any(word[:5] in lowered for word in words)


def template_summary(recipe: dict) -> dict | None:
    """One line stitched from the rules themselves. The fallback, and the floor."""
    rules = [r for r in recipe.get("matched_rules", []) if r.get("status") not in HIDDEN]
    if not rules:
        return None
    rules.sort(key=lambda r: ORDER.get(r.get("status"), 9))

    doing = [r["engine_action"].rstrip(".") for r in rules if r.get("status") == "not_satisfied"]
    already = [r["name"] for r in rules if r.get("status") == "satisfied"]
    notes = [r["engine_action"].rstrip(".") for r in rules if r.get("status") == "advisory"]

    parts = []
    if doing:
        parts.append("Worth doing: " + "; ".join(doing) + ".")
    if already:
        parts.append("Already working in your favour: " + "; ".join(already) + ".")
    if notes:
        parts.append("While you eat: " + "; ".join(notes) + ".")

    return {
        "text": " ".join(parts),
        "rule_ids": [r["rule_id"] for r in rules],
        "source": "template",
    }


def local_summary(recipe: dict) -> dict | None:
    """The same facts, read as one paragraph instead of a list."""
    base = template_summary(recipe)
    if not base:
        return None

    rules = [r for r in recipe.get("matched_rules", []) if r.get("status") not in HIDDEN]
    listing = "\n".join(
        f"- {r['rule_id']} ({r.get('status')}): {r.get('engine_action')} {r.get('why')}" for r in rules
    )
    prompt = f"Recipe: {recipe.get('name')}\nRules that apply:\n{listing}\n\nWrite the paragraph."

    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.LLM_URL}/chat/completions",
                json={
                    "model": config.LLM_MODEL,
                    "temperature": 0.3,
                    "max_tokens": 400,
                    "messages": [
                        {"role": "system", "content": SUMMARY_SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=config.LLM_TIMEOUT,
            )
            response.raise_for_status()
            choices = response.json().get("choices") or [{}]
            text = strip_preamble((choices[0].get("message") or {}).get("content", ""))
    except Exception:
        return base

    # Same two guards as the rewrites: readable, and no figures of its own.
    if not looks_like_prose(text, max_chars=1600) or borrowed_numbers(text, listing):
        return base

    # And one more that only a summary needs: it has to actually cover the
    # rules it claims to. A fluent paragraph that quietly drops two of four is
    # worse than the plain stitched version, because it reads complete.
    missed = [r["rule_id"] for r in rules if not _mentions(text, r, rules)]
    if missed:
        return {**base, "dropped_rules": missed}

    return {"text": text, "rule_ids": base["rule_ids"], "source": "local"}


def _rewrite(client: httpx.Client, recipe_name: str, suggestion: dict) -> str | None:
    """One model call for one suggestion. Returns None when the output is unusable."""
    prompt = (
        f"Recipe: {recipe_name}\n"
        f"Tip to rewrite: {suggestion['body']}\n\n"
        "Rewrite the tip."
    )
    try:
        response = client.post(
            f"{config.LLM_URL}/chat/completions",
            json={
                "model": config.LLM_MODEL,
                "temperature": 0.3,
                "max_tokens": 120,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=config.LLM_TIMEOUT,
        )
        response.raise_for_status()
        choices = response.json().get("choices") or [{}]
        text = (choices[0].get("message") or {}).get("content", "").strip()
    except Exception:
        return None

    text = text.strip().strip('"')
    if not looks_like_prose(text):
        return None
    # The model may only rearrange the facts it was given. A number that was
    # not in the source is the clearest sign it invented something.
    if borrowed_numbers(text, suggestion["body"]):
        return None
    return text


def local_suggestions(recipe: dict, rule_ids: list[str] | None = None) -> tuple[list[dict], str]:
    """Template output, rephrased by the local model where the rewrite is clean."""
    base = template_suggestions(recipe, rule_ids)
    if not base:
        return base, "template"

    rewritten = 0
    with httpx.Client() as client:
        for suggestion in base:
            text = _rewrite(client, recipe.get("name", ""), suggestion)
            if text:
                suggestion["body"] = text
                rewritten += 1

    # Nothing survived, so say template rather than claim a model wrote it.
    return base, ("local" if rewritten else "template")


def suggestions_for(recipe: dict, rule_ids: list[str] | None = None) -> tuple[list[dict], str, str | None, dict | None]:
    """Returns the suggestions, where the words came from, the model, and a
    summary that reads every matched rule together rather than one at a time."""
    if config.PROVIDER == "local":
        items, source = local_suggestions(recipe, rule_ids)
        summary = local_summary(recipe)
        return items, source, (config.LLM_MODEL if source == "local" else None), summary
    return template_suggestions(recipe, rule_ids), "template", None, template_summary(recipe)
