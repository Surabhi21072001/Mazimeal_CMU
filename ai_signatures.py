"""DSPy signatures only. The docstrings are the prompts; GEPA may rewrite them."""
import dspy

from domain_models import AlreadyAppliedFact, ApplicableFact, RecipeChange, SkippedItem


class SelectApplicableFacts(dspy.Signature):
    """For every nutrition fact, decide whether this recipe already does it, could do it, or has no use for it.
    Do not rewrite the recipe.

    Think like a cook who knows these rules and wants the best version of this recipe for the nutrient
    benefit each fact describes. Read the ingredients AND the steps together: how an ingredient is
    prepared matters as much as whether it is there.

    You get a list of facts, each as "rule_id (rule name): evidence summary". The rule name says what
    the fact is about. Put EVERY fact in exactly one of three lists:
    - already_applied_facts: the recipe already does what the fact recommends, so nothing needs to change.
      Give evidence_quote: the exact words from the recipe's ingredients or steps that show it,
      copied word for word from one ingredient line or one step.
    - applicable_facts: the recipe has the ingredient or preparation the fact is about and does NOT yet do
      what the fact recommends, so applying the fact would improve the recipe. List the ingredients that
      make it apply as trigger_ingredients, in the recipe's own wording. If the fact only matters for a
      preparation this recipe does not use (for example it matters when an ingredient is heated but the
      recipe serves it raw), it is not applicable.
    - skipped_facts: nothing in the recipe connects to the fact. Give a short, specific reason tied to
      this recipe.
    Use only the rule_ids you were given. Never invent a fact. Never put a fact in two lists.
    If governance_feedback is not empty, it lists mistakes in your previous answer. Fix each one.
    """

    recipe: str = dspy.InputField(desc="Recipe title, ingredient lines and steps")
    fact_summaries: list[str] = dspy.InputField(desc='One "rule_id (rule name): evidence summary" line per fact')
    governance_feedback: str = dspy.InputField(desc="Mistakes in your previous answer, or empty")
    applicable_facts: list[ApplicableFact] = dspy.OutputField(
        desc="Facts that would improve the recipe and are not yet applied, each with its trigger ingredients"
    )
    already_applied_facts: list[AlreadyAppliedFact] = dspy.OutputField(
        desc="Facts the recipe already carries out, each with a word-for-word quote from the recipe"
    )
    skipped_facts: list[SkippedItem] = dspy.OutputField(
        desc="Facts with no connection to the recipe, each with a reason"
    )


class SelectApplicableBioavailabilityFacts(SelectApplicableFacts):
    """For every BIOAVAILABILITY fact, decide whether this recipe already does it, could do it, or has no
    use for it. Do not rewrite the recipe.

    A bioavailability fact says how preparing or processing a food (crushing, cooking, soaking,
    chopping, grinding) changes how much of a nutrient the body can use. Think like a cook who knows
    these rules and wants the most usable nutrients from this recipe. Read the ingredients AND the steps
    together: how an ingredient is prepared matters as much as whether it is there.

    You get a list of facts, each as "rule_id (rule name): evidence summary". The rule name says what
    the fact is about. Put EVERY fact in exactly one of three lists:
    - already_applied_facts: the steps or ingredients already do what the fact recommends, so nothing
      needs to change. Give evidence_quote: the exact words from the recipe that show it, copied word
      for word from one ingredient line or one step.
    - applicable_facts: the recipe has the ingredient the fact is about and prepares it in a way that
      misses the benefit, so changing the preparation would improve the recipe. List the ingredients that
      make it apply as trigger_ingredients, in the recipe's own wording. If the fact only matters for a
      preparation this recipe does not use (for example it matters when an ingredient is heated but the
      recipe serves it raw), it is not applicable.
    - skipped_facts: nothing in the recipe connects to the fact. Give a short, specific reason tied to
      this recipe.
    Use only the rule_ids you were given. Never invent a fact. Never put a fact in two lists.
    If governance_feedback is not empty, it lists mistakes in your previous answer. Fix each one.
    """


class SelectApplicableSynergyFacts(SelectApplicableFacts):
    """For every SYNERGY fact, decide whether this recipe already does it, could do it, or has no use for it.
    Do not rewrite the recipe.

    A synergy fact says that two things eaten together change absorption or use (for example vitamin C with
    plant iron, or fat with carotenoids). Each fact therefore has two sides: a nutrient SOURCE the recipe
    must really contain (the rule name tells you which: iron from beans, carotenoids from carrots, vitamin D
    from fish or eggs) and a PARTNER that helps absorb it. Think like a cook who knows these pairings and
    wants the most absorbable nutrients from this recipe. Read the ingredients AND the steps together.

    You get a list of facts, each as "rule_id (rule name): evidence summary". Put EVERY fact in exactly one
    of three lists:
    - already_applied_facts: the recipe already contains BOTH sides, so nothing needs to change.
      Give evidence_quote: words copied exactly from ONE ingredient line or ONE step that show it. Never join
      two lines in one quote. If the two sides are on different lines, quote the line of the partner.
      Only text already in the recipe counts here, not pending actions.
    - applicable_facts: the recipe really contains the source side and the partner is MISSING, so adding the
      partner (a food or ingredient the Chef can add) would improve the recipe. List the ingredients that
      are the source side as trigger_ingredients, copied from the recipe or from a pending action with plain
      keyboard characters, exactly as written. Do not mark a fact applicable when the recipe has no real
      source of the nutrient (for example, a vitamin D fact needs a vitamin D food in the recipe), when
      the partner is already there, or when the pairing is about the rest of the meal and not the recipe.
    - skipped_facts: the source side is not in the recipe, or no change would help. Give a short, specific
      reason tied to this recipe.
    The partner must be what the fact names, not a look-alike. A generic acid such as vinegar is not vitamin C,
    and a food with a little incidental fat is not a fat source. If only a look-alike is present, the partner
    is still missing.
    pending_bioavailability_actions are changes the Chef will make to this recipe. Count what they add or
    change as part of the recipe when deciding whether the source side is there or the partner can be added.
    Use only the rule_ids you were given. Never invent a fact. Never put a fact in two lists.
    If governance_feedback is not empty, it lists mistakes in your previous answer. Fix each one.
    """

    pending_bioavailability_actions: list[str] = dspy.InputField(
        desc="Approved bioavailability actions the Chef will apply, as 'rule_id: action'"
    )


class ApplyRecommendedActions(dspy.Signature):
    """Rewrite the recipe by applying the approved actions. Change nothing else.

    Each action is "rule_id: action. How to apply it". For each one, either:
    - Apply it, and record a recipe change that cites its rule_id; or
    - Decline it in skipped_actions with a specific reason (for example it conflicts with another
      action or with the dish). Never invent an action that was not approved.

    Recipe changes:
    - Copy text_before and text_after word for word from the original recipe and from your updated
      recipe. The same text must appear in updated_ingredients or updated_steps.
    - Add: text_before is empty. Remove: text_after is empty. Swap or technique change: both filled.
    - One change may cite several rule_ids when it satisfies all of them.
    - Keep every other ingredient and step exactly as written.
    - updated_ingredients and updated_steps must contain EVERY ingredient line and EVERY step of the
      original recipe, changed or not, in the original order. Never summarize, merge or drop a line.
    - Add an ingredient only if a step in the updated recipe uses it, and write it like the other ingredient
      lines, with no hedges such as "optional". If an action adds a food, add it to the ingredients and
      work it into a step in the same change.
    Apply each action exactly as written. Do not change its amount or timing, and do not invent quantities
    the action does not state. If an amount or timing could be adapted to this dish, leave the recipe as
    the action says and write the idea in adaptation_notes as "rule_id: suggestion". Notes are never applied.
    If governance_feedback is not empty, it lists mistakes in your previous answer. Fix each one.
    """

    recipe: str = dspy.InputField(desc="The original recipe: title, ingredient lines and steps")
    recommended_actions: list[str] = dspy.InputField(desc='One "rule_id: action. How to apply it" line per action')
    governance_feedback: str = dspy.InputField(desc="Mistakes in your previous answer, or empty")
    updated_ingredients: list[str] = dspy.OutputField(desc="The full ingredient list after your changes")
    updated_steps: list[str] = dspy.OutputField(desc="The full list of steps after your changes")
    recipe_changes: list[RecipeChange] = dspy.OutputField(desc="Every change you made, citing rule_ids")
    skipped_actions: list[SkippedItem] = dspy.OutputField(desc="Every action you declined, with a reason")
    adaptation_notes: list[str] = dspy.OutputField(
        desc='Suggested amount or timing adaptations, each as "rule_id: suggestion". Not applied to the recipe.'
    )


class VerifyActionWasApplied(dspy.Signature):
    """Check whether the updated recipe carries out the recommended action.

    Compare the two recipes against the recommended action itself. Answer true only if the updated
    recipe really does what the action says and the original recipe did not already do it.
    evidence_line quotes the line of the updated recipe that proves it, or says what is missing.
    """

    recommended_action: str = dspy.InputField(desc="The action the updated recipe should carry out")
    original_recipe: str = dspy.InputField()
    updated_recipe: str = dspy.InputField()
    was_applied: bool = dspy.OutputField()
    evidence_line: str = dspy.OutputField(desc="Quote from the updated recipe, or what is missing")
