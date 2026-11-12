"""Business rules as pure functions. No LM, no database, no I/O.

Every error is a sentence written to be fed back to the model as governance_feedback.
"""
import re
from collections import Counter

from domain_models import AlreadyAppliedFact, ApplicableFact, Recipe, RecipeChange, SkippedItem, ValidationResult


def validate_fact_selection(
    given_rule_ids: list[str],
    applicable_facts: list[ApplicableFact],
    already_applied_facts: list[AlreadyAppliedFact],
    skipped_facts: list[SkippedItem],
    recipe_text: str,
    pending_actions_text: str = "",
) -> list[str]:
    """Rules S1 to S4 for one selector run. Returns the list of violations (empty means pass).

    recipe_text: the recipe as the selector saw it (title, ingredients, steps).
    pending_actions_text: for the Synergy selector, the approved bioavailability actions it was shown.
    """
    errors: list[str] = []
    given = set(given_rule_ids)
    applicable_ids = [fact.rule_id for fact in applicable_facts]
    already_applied_ids = [fact.rule_id for fact in already_applied_facts]
    skipped_ids = [item.rule_id for item in skipped_facts]
    all_listed_ids = applicable_ids + already_applied_ids + skipped_ids
    judged = set(all_listed_ids)

    # S1: full accounting. Every given fact is in exactly one of the three lists, and every skip has a reason.
    for rule_id in given_rule_ids:
        if rule_id not in judged:
            errors.append(
                f"S1: fact {rule_id} was not placed in applicable, already applied or skipped. "
                "Judge every fact you were given."
            )
    for rule_id, times_listed in Counter(all_listed_ids).items():
        if times_listed > 1:
            errors.append(
                f"S1: fact {rule_id} is listed {times_listed} times. Put each fact in exactly one list."
            )
    for item in skipped_facts:
        if not item.reason.strip():
            errors.append(f"S1: fact {item.rule_id} was skipped without a reason. Give a reason.")

    # S2: no invented facts.
    for rule_id in sorted(judged - given):
        errors.append(
            f"S2: fact {rule_id} was not in the list you were given. Use only the provided rule_ids."
        )

    # S3: applicable facts are grounded in the recipe. Substring match after ignoring case and extra whitespace.
    searchable_text = _normalize(recipe_text + "\n" + pending_actions_text)
    for fact in applicable_facts:
        if fact.rule_id not in given:
            continue  # already reported by S2
        if not fact.trigger_ingredients:
            errors.append(
                f"S3: fact {fact.rule_id} is applicable but names no trigger ingredient. "
                "List the recipe ingredients that make it apply, in the recipe's own wording."
            )
        for ingredient in fact.trigger_ingredients:
            if _normalize(ingredient) not in searchable_text:
                errors.append(
                    f'S3: fact {fact.rule_id} cites trigger ingredient "{ingredient}", which does not '
                    "appear in the recipe. Use the ingredient's wording from the recipe, "
                    "or mark the fact not applicable."
                )

    # S4: "already applied" is grounded in the recipe. The quote must really be in the recipe itself
    # (not in pending actions, which are not applied yet).
    normalized_recipe = _normalize(without_list_markers(recipe_text))
    for fact in already_applied_facts:
        if fact.rule_id not in given:
            continue  # already reported by S2
        quote = _normalize(without_list_markers(fact.evidence_quote))
        if not quote:
            errors.append(
                f"S4: fact {fact.rule_id} is marked already applied but gives no evidence quote. "
                "Copy the recipe text that shows it, or move the fact to applicable or skipped."
            )
        elif quote not in normalized_recipe:
            errors.append(
                f'S4: fact {fact.rule_id} is marked already applied, citing "{fact.evidence_quote}", '
                "which does not appear in the recipe. Copy the exact words from the ingredients or steps, "
                "or move the fact to applicable or skipped."
            )
    return errors


def validate_recipe_changes(
    approved_rule_ids: list[str],
    original_recipe: Recipe,
    updated_recipe: Recipe,
    recipe_changes: list[RecipeChange],
    skipped_actions: list[SkippedItem],
) -> ValidationResult:
    """Rules C1, C2, C3 and C5 for one Chef run. C4 (the verifier) is run later by the pipeline,
    only on the unproven_changes returned here, and only when there are no errors."""
    errors: list[str] = []
    approved = set(approved_rule_ids)
    original_lines = _recipe_lines(original_recipe)
    updated_lines = _recipe_lines(updated_recipe)
    updated_text = "\n".join(updated_lines)
    original_text = "\n".join(original_lines)
    applied_ids = {rule_id for change in recipe_changes for rule_id in change.rule_ids}
    skipped_ids = [item.rule_id for item in skipped_actions]

    # C1: full accounting. Every approved action is applied or declined with a reason, not both.
    for rule_id in approved_rule_ids:
        if rule_id not in applied_ids and rule_id not in skipped_ids:
            errors.append(
                f"C1: action {rule_id} was neither applied in a recipe change nor declined with a reason. "
                "Apply it or decline it."
            )
        if rule_id in applied_ids and rule_id in skipped_ids:
            errors.append(f"C1: action {rule_id} is both applied and declined. Choose one.")
    for item in skipped_actions:
        if not item.reason.strip():
            errors.append(f"C1: action {item.rule_id} was declined without a reason. Give a reason.")

    # C2: nothing unrequested.
    for change in recipe_changes:
        label = _describe(change)
        if not change.rule_ids:
            errors.append(f"C2: the change {label} cites no approved action. Cite its rule_id or remove the change.")
        for rule_id in change.rule_ids:
            if rule_id not in approved:
                errors.append(
                    f"C2: the change {label} cites {rule_id}, which was not approved. "
                    "Apply only the approved actions."
                )
    for rule_id in sorted(set(skipped_ids) - approved):
        errors.append(f"C2: action {rule_id} was declined but was never in the approved list.")

    # C3: evidence by diff.
    for change in recipe_changes:
        label = _describe(change)
        before = _normalize(without_list_markers(change.text_before))
        after = _normalize(without_list_markers(change.text_after))
        if not before and not after:
            errors.append(f"C3: the change citing {change.rule_ids} records no text_before and no text_after.")
        if after and after not in updated_text:
            errors.append(
                f'C3: the change {label} says the new recipe contains "{change.text_after}", but it does not. '
                "Copy text_after word for word from your updated ingredients or steps."
            )
        if before and before not in original_text:
            errors.append(
                f'C3: the change {label} says the original recipe contained "{change.text_before}", but it did not. '
                "Copy text_before word for word from the original recipe."
            )
        if before and _text_still_present(before, after, updated_lines, updated_text):
            errors.append(
                f'C3: the change {label} says "{change.text_before}" was removed or replaced, '
                "but it is still in the updated recipe."
            )

    # C5: original recipe intact. A disappeared line must be named as text_before in a recorded change.
    changed_texts = [_normalize(without_list_markers(change.text_before)) for change in recipe_changes if change.text_before.strip()]
    for line in original_lines:
        if line in updated_lines:
            continue
        if not any(before in line or line in before for before in changed_texts):
            errors.append(
                f'C5: the original line "{line}" is missing from the updated recipe and no recorded change '
                "names it as text_before. Keep it, or record the change."
            )

    unproven_changes = [] if errors else [change for change in recipe_changes if _needs_verifier(change)]
    return ValidationResult(errors=errors, unproven_changes=unproven_changes)


def _needs_verifier(change: RecipeChange) -> bool:
    """C4 applies to changes whose text was rewritten (Swap, Technique). A diff shows that the new text
    is there, not that it carries out the action. Add and Remove are proven by presence and absence."""
    return bool(change.text_before.strip() and change.text_after.strip())


def _recipe_lines(recipe: Recipe) -> list[str]:
    return [_normalize(without_list_markers(line)) for line in recipe.ingredients + recipe.steps]


def _text_still_present(before: str, after: str, updated_lines: list[str], updated_text: str) -> bool:
    if before in after:  # e.g. "garlic" -> "garlic, crushed": only the standalone old line must be gone
        return before in updated_lines
    return before in updated_text


def _describe(change: RecipeChange) -> str:
    return f'(before: "{change.text_before}", after: "{change.text_after}")'


def without_list_markers(text: str) -> str:
    """Drop the '- ', '1. ' and '5a. ' markers that Recipe.as_prompt_text() puts in front of each line."""
    return re.sub(r"(?m)^\s*(?:\d+[a-z]?\.|-)\s+", "", text)


def _normalize(text: str) -> str:
    """Lower case, one space between words, and typographic hyphens and non-breaking spaces made plain."""
    plain = re.sub("[\u2010\u2011\u2012\u2013\u2014\u2212]", "-", text.replace("\u00a0", " ").replace("\u202f", " "))
    return " ".join(plain.lower().split())
