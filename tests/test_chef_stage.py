import dspy

from domain_models import ApplicableFact, Recipe, RecipeChange, SkippedItem
from nutrition_fact_repository import NutritionFactRepository
from recipe_enhancement_pipeline import RecipeEnhancementPipeline

RECIPE = Recipe(
    title="Tomato Soup",
    ingredients=["4 ripe tomatoes", "2 cloves garlic", "1 tbsp olive oil"],
    steps=["Chop the tomatoes.", "Fry the garlic.", "Simmer with the tomatoes."],
)
FACTS = [ApplicableFact(rule_id="BIO-002", trigger_ingredients=["garlic"])]
GOOD_STEP = "Crush the garlic and rest 10 minutes, then fry the garlic."
GOOD_PREDICTION = dict(
    updated_ingredients=RECIPE.ingredients,
    updated_steps=[RECIPE.steps[0], GOOD_STEP, RECIPE.steps[2]],
    recipe_changes=[RecipeChange(rule_ids=["BIO-002"], text_before="Fry the garlic.", text_after=GOOD_STEP)],
    skipped_actions=[],
    adaptation_notes=["BIO-002: ten minutes may be long for a quick soup"],
)


def make_pipeline(chef_predictions, verdicts=(True,)):
    chef_calls, verifier_calls = [], []
    remaining = list(chef_predictions)

    def fake_chef(recipe, recommended_actions, governance_feedback):
        chef_calls.append((recommended_actions, governance_feedback))
        return dspy.Prediction(**remaining.pop(0))

    verdict_iter = iter(verdicts)

    def fake_verifier(recommended_action, original_recipe, updated_recipe):
        verifier_calls.append(recommended_action)
        return dspy.Prediction(was_applied=next(verdict_iter), evidence_line="evidence")

    pipeline = RecipeEnhancementPipeline(NutritionFactRepository())
    pipeline.chef, pipeline.action_verifier = fake_chef, fake_verifier
    return pipeline, chef_calls, verifier_calls


def test_good_rewrite_is_verified_and_shipped_with_notes():
    pipeline, chef_calls, verifier_calls = make_pipeline([GOOD_PREDICTION])
    result = pipeline.apply_recommended_actions(RECIPE, FACTS)
    assert result.recipe.steps[1] == GOOD_STEP
    assert result.change_log == GOOD_PREDICTION["recipe_changes"]
    assert result.adaptation_notes == GOOD_PREDICTION["adaptation_notes"]
    report = result.stage_reports[0]
    assert report.stage_name == "chef" and report.attempts == 1 and report.errors == []
    assert report.accepted_rule_ids == ["BIO-002"]
    assert chef_calls[0][0][0].startswith("BIO-002: Crush or mince")
    assert len(verifier_calls) == 1 and verifier_calls[0].startswith("BIO-002:")


def test_verifier_rejection_is_fed_back_and_retried():
    pipeline, chef_calls, _ = make_pipeline([GOOD_PREDICTION, GOOD_PREDICTION], verdicts=(False, True))
    result = pipeline.apply_recommended_actions(RECIPE, FACTS)
    assert result.stage_reports[0].attempts == 2
    assert chef_calls[0][1] == "" and chef_calls[1][1].startswith("C4") and "evidence" in chef_calls[1][1]
    assert result.recipe.steps[1] == GOOD_STEP


def test_chef_that_keeps_failing_ships_the_original_recipe():
    unrequested = dict(GOOD_PREDICTION, recipe_changes=[RecipeChange(rule_ids=["BIO-99"], text_after=GOOD_STEP)])
    pipeline, chef_calls, verifier_calls = make_pipeline([unrequested] * 3)
    result = pipeline.apply_recommended_actions(RECIPE, FACTS)
    assert result.recipe == RECIPE and result.change_log == [] and result.adaptation_notes == []
    report = result.stage_reports[0]
    assert report.attempts == 3 and len(chef_calls) == 3 and report.accepted_rule_ids == []
    assert verifier_calls == []  # the verifier never runs while C1 to C5 errors remain
    assert any(error.startswith("C2") for error in report.errors)


def test_declining_with_a_reason_is_recorded():
    declined = dict(
        GOOD_PREDICTION, updated_steps=RECIPE.steps, recipe_changes=[], adaptation_notes=[],
        skipped_actions=[SkippedItem(rule_id="BIO-002", reason="garlic is raw in this dish")],
    )
    pipeline, _, verifier_calls = make_pipeline([declined])
    result = pipeline.apply_recommended_actions(RECIPE, FACTS)
    assert result.recipe == RECIPE and result.change_log == []
    assert result.stage_reports[0].skipped_reasons == {"BIO-002": "garlic is raw in this dish"}
    assert result.stage_reports[0].attempts == 1 and verifier_calls == []


def test_no_approved_facts_skips_the_chef():
    pipeline, chef_calls, _ = make_pipeline([])
    result = pipeline.apply_recommended_actions(RECIPE, [])
    assert result.recipe == RECIPE and chef_calls == [] and result.stage_reports[0].attempts == 0


def test_list_markers_the_chef_copies_are_ignored_and_not_shipped():
    marked = dict(GOOD_PREDICTION)
    marked["updated_ingredients"] = [f"- {line}" for line in RECIPE.ingredients]
    marked["updated_steps"] = [f"{n}. {line}" for n, line in enumerate(
        [RECIPE.steps[0], GOOD_STEP, RECIPE.steps[2]], 1)]
    marked["recipe_changes"] = [
        RecipeChange(rule_ids=["BIO-002"], text_before="2. Fry the garlic.", text_after=f"2. {GOOD_STEP}")]
    pipeline, _, _ = make_pipeline([marked])
    result = pipeline.apply_recommended_actions(RECIPE, FACTS)
    report = result.stage_reports[0]
    assert report.attempts == 1 and report.errors == []
    assert result.recipe.steps == [RECIPE.steps[0], GOOD_STEP, RECIPE.steps[2]]
    assert result.recipe.ingredients == RECIPE.ingredients


def test_result_carries_the_sources_of_the_applied_facts_only():
    pipeline, _, _ = make_pipeline([GOOD_PREDICTION])
    result = pipeline.apply_recommended_actions(RECIPE, FACTS)
    expected = NutritionFactRepository().fetch_evidence_sources(["BIO-002"])
    assert result.evidence_sources == expected and expected["BIO-002"]


def test_result_has_no_sources_when_the_chef_ships_the_original():
    bad = dict(GOOD_PREDICTION, updated_steps=RECIPE.steps, recipe_changes=[])  # applies nothing, declines nothing
    pipeline, _, _ = make_pipeline([bad, bad, bad])
    result = pipeline.apply_recommended_actions(RECIPE, FACTS)
    assert result.change_log == [] and result.evidence_sources == {}
