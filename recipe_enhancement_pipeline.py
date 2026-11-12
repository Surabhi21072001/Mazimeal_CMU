"""Orchestration: the only layer that touches both the LM and the repository.

Stages: bioavailability selector, synergy selector (sees the approved bio actions as pending), Chef (with the C4 verifier).
"""
import dspy

from ai_signatures import (
    ApplyRecommendedActions,
    SelectApplicableBioavailabilityFacts,
    SelectApplicableSynergyFacts,
    VerifyActionWasApplied,
)
from domain_models import (
    ApplicableFact,
    Recipe,
    RecipeChange,
    RecipeEnhancementResult,
    StageGovernanceReport,
)
from governance_retry import run_with_governance_retry
from governance_rules import validate_fact_selection, validate_recipe_changes, without_list_markers
from nutrition_fact_repository import NutritionFactRepository


class RecipeEnhancementPipeline(dspy.Module):
    def __init__(self, fact_repository: NutritionFactRepository):
        super().__init__()
        self.fact_repository = fact_repository
        self.bioavailability_selector = dspy.Predict(SelectApplicableBioavailabilityFacts)
        self.synergy_selector = dspy.Predict(SelectApplicableSynergyFacts)
        self.chef = dspy.Predict(ApplyRecommendedActions)
        self.action_verifier = dspy.Predict(VerifyActionWasApplied)

    def forward(self, recipe: Recipe) -> RecipeEnhancementResult:
        """Bioavailability selector, then synergy selector (which sees the bio actions as pending), then the Chef."""
        bio_facts, bio_report = self.select_bioavailability_facts(recipe)
        synergy_facts, synergy_report = self.select_synergy_facts(recipe, bio_facts)
        result = self.apply_recommended_actions(recipe, bio_facts + synergy_facts)
        result.stage_reports = [bio_report, synergy_report] + result.stage_reports
        return result

    def select_bioavailability_facts(
        self, recipe: Recipe
    ) -> tuple[list[ApplicableFact], StageGovernanceReport]:
        """Run the bio selector under S1 to S4. A selector that still fails contributes no facts."""
        return self._run_selector("bioavailability", self.bioavailability_selector, recipe)

    def select_synergy_facts(
        self, recipe: Recipe, approved_bio_facts: list[ApplicableFact]
    ) -> tuple[list[ApplicableFact], StageGovernanceReport]:
        """Run the synergy selector under S1 to S4. It sees the approved bio actions as pending, and S3 accepts
        trigger ingredients found in them. A selector that still fails contributes no facts."""
        actions = self.fact_repository.fetch_recommended_actions([fact.rule_id for fact in approved_bio_facts])
        pending_actions = [
            f"{rule_id}: {action.description}. {action.engine_instruction}" for rule_id, action in actions.items()
        ]
        return self._run_selector(
            "synergy", self.synergy_selector, recipe, pending_actions=pending_actions)

    def _run_selector(
        self, category: str, selector, recipe: Recipe, pending_actions: list[str] | None = None
    ) -> tuple[list[ApplicableFact], StageGovernanceReport]:
        recipe_text = recipe.as_prompt_text()
        given_rule_ids = self.fact_repository.fetch_rule_ids(category)
        fact_summaries = self.fact_repository.fetch_fact_summaries(category)
        extra_inputs = {} if pending_actions is None else {"pending_bioavailability_actions": pending_actions}

        prediction, errors, attempts = run_with_governance_retry(
            model_step=lambda governance_feedback: selector(
                recipe=recipe_text,
                fact_summaries=fact_summaries,
                governance_feedback=governance_feedback,
                **extra_inputs,
            ),
            validate=lambda prediction: validate_fact_selection(
                given_rule_ids,
                prediction.applicable_facts,
                prediction.already_applied_facts,
                prediction.skipped_facts,
                recipe_text,
                pending_actions_text="\n".join(pending_actions or []),
            ),
        )

        if prediction is None:
            applicable_facts, skipped_reasons, already_applied_quotes = [], {}, {}
        else:
            applicable_facts = prediction.applicable_facts
            skipped_reasons = {item.rule_id: item.reason for item in prediction.skipped_facts}
            already_applied_quotes = {
                fact.rule_id: fact.evidence_quote for fact in prediction.already_applied_facts
            }
        report = StageGovernanceReport(
            stage_name=category,
            given_rule_ids=given_rule_ids,
            accepted_rule_ids=[fact.rule_id for fact in applicable_facts],
            skipped_reasons=skipped_reasons,
            errors=errors,
            attempts=attempts,
            already_applied_quotes=already_applied_quotes,
        )
        return applicable_facts, report

    def apply_recommended_actions(
        self, recipe: Recipe, applicable_facts: list[ApplicableFact]
    ) -> RecipeEnhancementResult:
        """Run the Chef under C1 to C5. A Chef that still fails ships the original recipe unchanged."""
        approved_rule_ids = [fact.rule_id for fact in applicable_facts]
        if not approved_rule_ids:
            return RecipeEnhancementResult(
                recipe=recipe,
                change_log=[],
                stage_reports=[StageGovernanceReport(
                    stage_name="chef", given_rule_ids=[], accepted_rule_ids=[],
                    skipped_reasons={}, errors=[], attempts=0)],
            )

        actions = self.fact_repository.fetch_recommended_actions(approved_rule_ids)
        action_lines = {
            rule_id: f"{rule_id}: {action.description}. {action.engine_instruction}"
            for rule_id, action in actions.items()
        }
        recipe_text = recipe.as_prompt_text()

        def validate_chef_output(prediction) -> list[str]:
            updated_recipe = self._recipe_from_chef_output(recipe, prediction)
            result = validate_recipe_changes(
                approved_rule_ids, recipe, updated_recipe,
                prediction.recipe_changes, prediction.skipped_actions,
            )
            if result.errors:
                return result.errors
            return self._verify_unproven_changes(
                result.unproven_changes, action_lines, recipe_text, updated_recipe.as_prompt_text()
            )

        prediction, errors, attempts = run_with_governance_retry(
            model_step=lambda governance_feedback: self.chef(
                recipe=recipe_text,
                recommended_actions=list(action_lines.values()),
                governance_feedback=governance_feedback,
            ),
            validate=validate_chef_output,
        )

        if prediction is None:
            result_recipe, change_log, declined, adaptation_notes = recipe, [], {}, []
        else:
            result_recipe = self._recipe_from_chef_output(recipe, prediction)
            change_log = prediction.recipe_changes
            declined = {item.rule_id: item.reason for item in prediction.skipped_actions}
            adaptation_notes = prediction.adaptation_notes
        applied_rule_ids = sorted({rule_id for change in change_log for rule_id in change.rule_ids})
        report = StageGovernanceReport(
            stage_name="chef",
            given_rule_ids=approved_rule_ids,
            accepted_rule_ids=applied_rule_ids,
            skipped_reasons=declined,
            errors=errors,
            attempts=attempts,
        )
        return RecipeEnhancementResult(
            recipe=result_recipe, change_log=change_log, stage_reports=[report],
            adaptation_notes=adaptation_notes,
            evidence_sources=self.fact_repository.fetch_evidence_sources(applied_rule_ids),
        )

    @staticmethod
    def _recipe_from_chef_output(recipe: Recipe, prediction) -> Recipe:
        """The Chef sees numbered steps and dashed ingredients and sometimes copies the markers. Drop them."""
        return Recipe(
            title=recipe.title,
            ingredients=[without_list_markers(line) for line in prediction.updated_ingredients],
            steps=[without_list_markers(line) for line in prediction.updated_steps],
        )

    def _verify_unproven_changes(
        self,
        unproven_changes: list[RecipeChange],
        action_lines: dict[str, str],
        original_recipe_text: str,
        updated_recipe_text: str,
    ) -> list[str]:
        """Rule C4: judge each rewrite against the fact's own action, never the Chef's description."""
        errors = []
        for change in unproven_changes:
            for rule_id in change.rule_ids:
                verdict = self.action_verifier(
                    recommended_action=action_lines[rule_id],
                    original_recipe=original_recipe_text,
                    updated_recipe=updated_recipe_text,
                )
                if not verdict.was_applied:
                    errors.append(
                        f'C4: the change (before: "{change.text_before}", after: "{change.text_after}") '
                        f"does not carry out {rule_id}. Verifier: {verdict.evidence_line}"
                    )
        return errors
