"""Domain models: Pydantic data only."""
from typing import Literal

from pydantic import BaseModel, Field


class RecommendedAction(BaseModel):
    description: str
    code: str
    engine_instruction: str


class EvidenceSource(BaseModel):
    title: str
    type: str
    url: str
    review_date: str


class Evidence(BaseModel):
    tier: Literal["A", "B", "C"]
    summary: str
    sources: list[EvidenceSource]


class NutritionFact(BaseModel):
    """One fact record, the JSON shape in docs/implementation-spec.md."""

    rule_id: str
    rule_name: str
    category: Literal["bioavailability", "synergy"]
    action: RecommendedAction
    evidence: Evidence


class Recipe(BaseModel):
    title: str
    ingredients: list[str]
    steps: list[str]

    def as_prompt_text(self) -> str:
        ingredient_lines = "\n".join(f"- {line}" for line in self.ingredients)
        step_lines = "\n".join(f"{number}. {line}" for number, line in enumerate(self.steps, 1))
        return f"{self.title}\n\nIngredients:\n{ingredient_lines}\n\nSteps:\n{step_lines}"


class ApplicableFact(BaseModel):
    """A fact a selector judged applicable. trigger_ingredients use the recipe's own wording."""

    rule_id: str
    trigger_ingredients: list[str]


class AlreadyAppliedFact(BaseModel):
    """A fact the recipe already carries out. evidence_quote is text copied from the recipe that shows it."""

    rule_id: str
    evidence_quote: str


class SkippedItem(BaseModel):
    """A fact a selector judged not applicable, or an action the Chef declined, with the reason."""

    rule_id: str
    reason: str


class RecipeChange(BaseModel):
    """Add: text_before empty. Remove: text_after empty. Swap and Technique: both filled."""

    rule_ids: list[str]
    text_before: str = ""
    text_after: str = ""


class ValidationResult(BaseModel):
    errors: list[str] = Field(default_factory=list)
    unproven_changes: list[RecipeChange] = Field(default_factory=list)


class StageGovernanceReport(BaseModel):
    stage_name: str
    given_rule_ids: list[str]
    accepted_rule_ids: list[str]
    skipped_reasons: dict[str, str]
    errors: list[str]
    attempts: int
    already_applied_quotes: dict[str, str] = Field(default_factory=dict)  # selectors only: rule_id -> quote


class RecipeEnhancementResult(BaseModel):
    recipe: Recipe
    change_log: list[RecipeChange]
    stage_reports: list[StageGovernanceReport]
    adaptation_notes: list[str] = Field(default_factory=list)  # Chef suggestions, never applied
    evidence_sources: dict[str, list[EvidenceSource]] = Field(default_factory=dict)  # rule_id -> sources, applied facts only
