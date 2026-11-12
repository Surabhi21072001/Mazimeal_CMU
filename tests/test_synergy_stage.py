import dspy

from domain_models import ApplicableFact, Recipe, RecipeChange, SkippedItem
from nutrition_fact_repository import NutritionFactRepository
from recipe_enhancement_pipeline import RecipeEnhancementPipeline

RECIPE = Recipe(
    title="Tomato Soup",
    ingredients=["4 ripe tomatoes", "2 cloves garlic", "1 tbsp olive oil"],
    steps=["Chop the tomatoes.", "Fry the garlic.", "Simmer with the tomatoes."],
)
repository = NutritionFactRepository()
SYNERGY_IDS = repository.fetch_rule_ids("synergy")
BIO_GARLIC = ApplicableFact(rule_id="BIO-002", trigger_ingredients=["garlic"])


def fake_synergy_selector(applicable: dict[str, list[str]]):
    """Ids in `applicable` apply, every other synergy fact is skipped. Records what the selector was shown."""
    calls = []

    def selector(recipe, fact_summaries, governance_feedback, pending_bioavailability_actions):
        calls.append({"pending": pending_bioavailability_actions, "feedback": governance_feedback})
        return dspy.Prediction(
            applicable_facts=[ApplicableFact(rule_id=i, trigger_ingredients=t) for i, t in applicable.items()],
            already_applied_facts=[],
            skipped_facts=[SkippedItem(rule_id=i, reason="no") for i in SYNERGY_IDS if i not in applicable],
        )

    return selector, calls


def test_synergy_selector_sees_the_approved_bio_actions_as_pending():
    selector, calls = fake_synergy_selector({"SYN-002": ["olive oil"]})
    pipeline = RecipeEnhancementPipeline(repository)
    pipeline.synergy_selector = selector
    facts, report = pipeline.select_synergy_facts(RECIPE, [BIO_GARLIC])
    assert [f.rule_id for f in facts] == ["SYN-002"]
    assert report.stage_name == "synergy" and report.given_rule_ids == SYNERGY_IDS and report.attempts == 1
    assert len(calls[0]["pending"]) == 1 and calls[0]["pending"][0].startswith("BIO-002:")


def test_with_no_bio_facts_the_pending_list_is_empty():
    selector, calls = fake_synergy_selector({})
    pipeline = RecipeEnhancementPipeline(repository)
    pipeline.synergy_selector = selector
    pipeline.select_synergy_facts(RECIPE, [])
    assert calls[0]["pending"] == []


def test_synergy_trigger_found_only_in_pending_actions_is_accepted():
    selector, _ = fake_synergy_selector({"SYN-002": ["unsaturated culinary oil"]})  # words of BIO-003's action
    pipeline = RecipeEnhancementPipeline(repository)
    pipeline.synergy_selector = selector
    tomato_fact = ApplicableFact(rule_id="BIO-003", trigger_ingredients=["tomatoes"])
    facts, report = pipeline.select_synergy_facts(RECIPE, [tomato_fact])
    assert [f.rule_id for f in facts] == ["SYN-002"] and report.errors == []


def test_synergy_trigger_not_in_recipe_or_pending_is_retried_then_dropped():
    selector, calls = fake_synergy_selector({"SYN-001": ["lentils"]})
    pipeline = RecipeEnhancementPipeline(repository)
    pipeline.synergy_selector = selector
    facts, report = pipeline.select_synergy_facts(RECIPE, [])
    assert facts == [] and report.attempts == 3 and calls[1]["feedback"].startswith("S3")


# The whole pipeline
GOOD_STEP = "Crush the garlic and rest 10 minutes, then fry the garlic."
OIL_STEP = "Finish with a drizzle of olive oil."


def test_forward_runs_bio_then_synergy_then_the_chef_on_both_sets_of_facts():
    chef_calls = []

    def fake_bio_selector(recipe, fact_summaries, governance_feedback):
        given = repository.fetch_rule_ids("bioavailability")
        return dspy.Prediction(
            applicable_facts=[BIO_GARLIC], already_applied_facts=[],
            skipped_facts=[SkippedItem(rule_id=i, reason="no") for i in given if i != "BIO-002"])

    def fake_chef(recipe, recommended_actions, governance_feedback):
        chef_calls.append(recommended_actions)
        return dspy.Prediction(
            updated_ingredients=RECIPE.ingredients,
            updated_steps=[RECIPE.steps[0], GOOD_STEP, RECIPE.steps[2], OIL_STEP],
            recipe_changes=[
                RecipeChange(rule_ids=["BIO-002"], text_before="Fry the garlic.", text_after=GOOD_STEP),
                RecipeChange(rule_ids=["SYN-002"], text_before="", text_after=OIL_STEP),
            ],
            skipped_actions=[], adaptation_notes=[])

    synergy_selector, _ = fake_synergy_selector({"SYN-002": ["olive oil"]})
    pipeline = RecipeEnhancementPipeline(repository)
    pipeline.bioavailability_selector, pipeline.synergy_selector, pipeline.chef = fake_bio_selector, synergy_selector, fake_chef
    pipeline.action_verifier = lambda recommended_action, original_recipe, updated_recipe: dspy.Prediction(
        was_applied=True, evidence_line="ok")

    result = pipeline(RECIPE)
    assert [report.stage_name for report in result.stage_reports] == ["bioavailability", "synergy", "chef"]
    assert [line[:7] for line in chef_calls[0]] == ["BIO-002", "SYN-002"]
    assert result.recipe.steps[-1] == OIL_STEP
    assert result.stage_reports[2].accepted_rule_ids == ["BIO-002", "SYN-002"]


def test_failed_synergy_stage_still_lets_the_bio_facts_reach_the_chef():
    chef_calls = []

    def fake_bio_selector(recipe, fact_summaries, governance_feedback):
        given = repository.fetch_rule_ids("bioavailability")
        return dspy.Prediction(
            applicable_facts=[BIO_GARLIC], already_applied_facts=[],
            skipped_facts=[SkippedItem(rule_id=i, reason="no") for i in given if i != "BIO-002"])

    def fake_chef(recipe, recommended_actions, governance_feedback):
        chef_calls.append(recommended_actions)
        return dspy.Prediction(
            updated_ingredients=RECIPE.ingredients,
            updated_steps=[RECIPE.steps[0], GOOD_STEP, RECIPE.steps[2]],
            recipe_changes=[RecipeChange(rule_ids=["BIO-002"], text_before="Fry the garlic.", text_after=GOOD_STEP)],
            skipped_actions=[], adaptation_notes=[])

    broken_synergy_selector, _ = fake_synergy_selector({"SYN-001": ["lentils"]})  # never in the recipe
    pipeline = RecipeEnhancementPipeline(repository)
    pipeline.bioavailability_selector, pipeline.synergy_selector, pipeline.chef = fake_bio_selector, broken_synergy_selector, fake_chef
    pipeline.action_verifier = lambda recommended_action, original_recipe, updated_recipe: dspy.Prediction(
        was_applied=True, evidence_line="ok")

    result = pipeline(RECIPE)
    assert result.stage_reports[1].accepted_rule_ids == [] and result.stage_reports[1].attempts == 3
    assert [line[:7] for line in chef_calls[0]] == ["BIO-002"]
    assert result.recipe.steps[1] == GOOD_STEP
