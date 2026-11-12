import dspy

from domain_models import AlreadyAppliedFact, ApplicableFact, Recipe, SkippedItem
from nutrition_fact_repository import NutritionFactRepository
from recipe_enhancement_pipeline import RecipeEnhancementPipeline

RECIPE = Recipe(
    title="Tomato Soup",
    ingredients=["4 ripe tomatoes", "2 cloves garlic", "1 tbsp olive oil"],
    steps=["Chop the tomatoes.", "Simmer with garlic and oil."],
)
repository = NutritionFactRepository()
GIVEN = repository.fetch_rule_ids("bioavailability")


def judge_everything_skipped_except(applicable: dict[str, list[str]], already_applied: dict[str, str] | None = None):
    """A fake selector: ids in `applicable` apply, ids in `already_applied` (id -> quote) are done, the rest are skipped."""
    already_applied = already_applied or {}
    calls = []

    def fake_selector(recipe, fact_summaries, governance_feedback):
        calls.append(governance_feedback)
        return dspy.Prediction(
            applicable_facts=[ApplicableFact(rule_id=i, trigger_ingredients=t) for i, t in applicable.items()],
            already_applied_facts=[AlreadyAppliedFact(rule_id=i, evidence_quote=q) for i, q in already_applied.items()],
            skipped_facts=[
                SkippedItem(rule_id=i, reason="not in this recipe")
                for i in GIVEN if i not in applicable and i not in already_applied
            ],
        )

    return fake_selector, calls


def make_pipeline(selector):
    pipeline = RecipeEnhancementPipeline(repository)
    pipeline.bioavailability_selector = selector
    return pipeline


def test_good_selection_is_accepted_on_first_attempt():
    selector, calls = judge_everything_skipped_except({"BIO-003": ["tomatoes"], "BIO-002": ["Garlic"]})
    facts, report = make_pipeline(selector).select_bioavailability_facts(RECIPE)
    assert [f.rule_id for f in facts] == ["BIO-003", "BIO-002"]
    assert report.attempts == 1 and report.errors == [] and calls == [""]
    assert report.stage_name == "bioavailability"
    assert report.given_rule_ids == GIVEN
    assert report.accepted_rule_ids == ["BIO-003", "BIO-002"]
    assert report.skipped_reasons["BIO-004"] == "not in this recipe"


def test_ungrounded_selection_is_retried_with_feedback_and_then_dropped():
    selector, calls = judge_everything_skipped_except({"BIO-004": ["carrot"]})  # no carrot in the recipe
    facts, report = make_pipeline(selector).select_bioavailability_facts(RECIPE)
    assert facts == [] and report.accepted_rule_ids == [] and report.skipped_reasons == {}
    assert report.attempts == 3 and len(calls) == 3
    assert calls[0] == "" and calls[1].startswith("S3") and '"carrot"' in calls[1]
    assert len(report.errors) == 3


def test_already_applied_facts_are_recorded_but_not_sent_to_the_chef():
    selector, _ = judge_everything_skipped_except(
        {"BIO-003": ["tomatoes"]}, already_applied={"BIO-002": "Simmer with garlic and oil"})
    facts, report = make_pipeline(selector).select_bioavailability_facts(RECIPE)
    assert [f.rule_id for f in facts] == ["BIO-003"]
    assert report.accepted_rule_ids == ["BIO-003"]
    assert report.already_applied_quotes == {"BIO-002": "Simmer with garlic and oil"}
    assert "BIO-002" not in report.skipped_reasons and report.errors == []


def test_invented_already_applied_quote_is_retried_then_dropped():
    selector, calls = judge_everything_skipped_except({}, already_applied={"BIO-002": "Crush the garlic and rest it"})
    facts, report = make_pipeline(selector).select_bioavailability_facts(RECIPE)
    assert facts == [] and report.already_applied_quotes == {} and report.attempts == 3
    assert calls[1].startswith("S4") and "Crush the garlic" in calls[1]
