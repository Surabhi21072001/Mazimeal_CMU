"""
The question box on the cook screen.

Unlike the suggestions, a question is not known in advance, so there is nothing
to pre-generate and nothing to review. That makes the grounding rules stricter,
not looser:

  - the model is given the recipe, its ingredients, its steps, the matched
    rules and the member's open targets, and told to answer from those alone;
  - it is told to say it does not know rather than guess;
  - numbers in the answer must already appear in that context, or the answer is
    refused - the same guard the rewrites use.

Without a model running, the box says so instead of pretending.
"""
from __future__ import annotations

import httpx

from . import config
from .validate import borrowed_numbers, looks_like_prose

SYSTEM = (
    "You answer a home cook's question about one recipe. "
    "Use only the facts in CONTEXT. If the answer is not there, say you do not know "
    "and suggest who could answer it. "
    "Never invent a number, a duration, a nutrition figure or a health claim. "
    "Two or three sentences, plain words, no greeting."
)

REFUSAL = (
    "The assistant needs a model running. Start one and set MAZI_PROVIDER=local, "
    "or read the suggestions above, which come from the rules themselves."
)


def build_context(recipe: dict, member: dict | None) -> str:
    lines = [f"Recipe: {recipe.get('name')} ({recipe.get('meal')}, {recipe.get('servings')} servings, {recipe.get('time_min')} min)"]

    ingredients = ", ".join(
        f"{i['quantity']} {i['unit']} {i['name']}" for i in recipe.get("ingredients", [])
    )
    lines.append(f"Ingredients: {ingredients}")

    for nutrient in recipe.get("nutrition_per_serving", []):
        lines.append(
            f"Nutrition per serving: {nutrient['label']} {nutrient['value']} {nutrient['unit']} "
            f"({nutrient['source']})"
        )

    for step in recipe.get("steps", []):
        lines.append(f"Step {step['step_number']}: {step['instruction']}")

    for rule in recipe.get("matched_rules", []):
        # needs_review rules belong to the reviewer console. Showing them here
        # would let the model talk about our internal process to a cook.
        if rule.get("status") == "needs_review":
            continue
        lines.append(
            f"Rule {rule['rule_id']} ({rule.get('status')}, evidence {rule.get('evidence_tier')}): "
            f"{rule.get('engine_action')} {rule.get('why')}"
        )

    if member:
        prefs = member.get("preferences") or {}
        # Safety first: without these the model cannot answer "can I eat this",
        # and a wrong answer there matters more than anywhere else on the page.
        allergies = ", ".join(prefs.get("allergies") or []) or "none recorded"
        dislikes = ", ".join(prefs.get("dislikes") or []) or "none recorded"
        conditions = ", ".join(member.get("conditions") or []) or "none recorded"
        lines.append(
            f"{member['name']} is {member.get('age')}, allergies: {allergies}; "
            f"dislikes: {dislikes}; conditions: {conditions}"
        )
        if prefs.get("dietary_patterns"):
            lines.append(f"{member['name']} eats: {', '.join(prefs['dietary_patterns'])}")

        for target in member.get("targets", []):
            line = (
                f"{member['name']} still needs {target['remaining']} {target['unit']} of "
                f"{target['label']} today, out of a daily target of {target['target']} {target['unit']}"
            )
            # Spell the comparison out. "raised for iron deficiency" alone was
            # too oblique for a small model to use when asked why.
            if target.get("baseline") is not None and target["baseline"] != target["target"]:
                line += (
                    f". That target is {target['target']} instead of the standard "
                    f"{target['baseline']} {target['unit']}"
                )
                if target.get("adjusted_reason"):
                    line += f" because of {target['adjusted_reason']}"
            lines.append(line)

    return "\n".join(lines)


def answer(recipe: dict, member: dict | None, question: str) -> dict:
    if config.PROVIDER != "local":
        return {"answer": REFUSAL, "source": "unavailable", "model": None}

    context = build_context(recipe, member)
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.LLM_URL}/chat/completions",
                json={
                    "model": config.LLM_MODEL,
                    "temperature": 0.2,
                    "max_tokens": 220,
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}"},
                    ],
                },
                timeout=config.LLM_TIMEOUT,
            )
            response.raise_for_status()
            choices = response.json().get("choices") or [{}]
            text = (choices[0].get("message") or {}).get("content", "").strip()
    except Exception as exc:  # the model is down, slow, or returned nonsense
        return {"answer": REFUSAL, "source": "unavailable", "model": None, "error": str(exc)[:120]}

    text = text.strip().strip('"')
    if not looks_like_prose(text):
        return {
            "answer": "The model did not give a usable answer. Try asking it another way.",
            "source": "rejected",
            "model": config.LLM_MODEL,
        }

    invented = borrowed_numbers(text, context + " " + question)
    if invented:
        return {
            "answer": (
                "That answer was dropped because it used figures this recipe does not have "
                f"({', '.join(sorted(invented))}). Ask again, or check the nutrition panel."
            ),
            "source": "rejected",
            "model": config.LLM_MODEL,
            "invented_numbers": sorted(invented),
        }

    return {"answer": text, "source": "local", "model": config.LLM_MODEL}
