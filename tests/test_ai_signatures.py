from ai_signatures import (
    ApplyRecommendedActions,
    SelectApplicableBioavailabilityFacts,
    SelectApplicableFacts,
    SelectApplicableSynergyFacts,
    VerifyActionWasApplied,
)


def test_bioavailability_selector_has_the_base_fields():
    assert list(SelectApplicableBioavailabilityFacts.input_fields) == [
        "recipe", "fact_summaries", "governance_feedback"]
    assert list(SelectApplicableBioavailabilityFacts.output_fields) == ["applicable_facts", "already_applied_facts", "skipped_facts"]


def test_synergy_selector_adds_pending_actions_only():
    assert list(SelectApplicableSynergyFacts.input_fields) == [
        "recipe", "fact_summaries", "governance_feedback", "pending_bioavailability_actions"]
    assert list(SelectApplicableSynergyFacts.output_fields) == ["applicable_facts", "already_applied_facts", "skipped_facts"]


def test_children_have_their_own_instructions():
    instructions = {
        SelectApplicableFacts.instructions,
        SelectApplicableBioavailabilityFacts.instructions,
        SelectApplicableSynergyFacts.instructions,
    }
    assert len(instructions) == 3
    assert "BIOAVAILABILITY" in SelectApplicableBioavailabilityFacts.instructions
    assert "SYNERGY" in SelectApplicableSynergyFacts.instructions


def test_chef_and_verifier_fields():
    assert list(ApplyRecommendedActions.input_fields) == ["recipe", "recommended_actions", "governance_feedback"]
    assert list(ApplyRecommendedActions.output_fields) == [
        "updated_ingredients", "updated_steps", "recipe_changes", "skipped_actions", "adaptation_notes"]
    assert list(VerifyActionWasApplied.input_fields) == [
        "recommended_action", "original_recipe", "updated_recipe"]
    assert list(VerifyActionWasApplied.output_fields) == ["was_applied", "evidence_line"]
