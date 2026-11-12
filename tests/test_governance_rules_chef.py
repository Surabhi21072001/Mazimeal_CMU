from domain_models import Recipe, RecipeChange, SkippedItem
from governance_rules import validate_recipe_changes

ORIGINAL = Recipe(
    title="Lentil Soup",
    ingredients=["1 cup red lentils", "2 cloves garlic", "1 onion"],
    steps=["Fry the garlic and onion.", "Add the lentils and simmer for 20 minutes."],
)
APPROVED = ["SYN-1", "BIO-2"]


def updated(ingredients=None, steps=None) -> Recipe:
    return Recipe(
        title="Lentil Soup",
        ingredients=ORIGINAL.ingredients if ingredients is None else ingredients,
        steps=ORIGINAL.steps if steps is None else steps,
    )


ADD_LEMON = RecipeChange(rule_ids=["SYN-1"], text_after="1 lemon, juiced")
TECHNIQUE_GARLIC = RecipeChange(
    rule_ids=["BIO-2"],
    text_before="Fry the garlic and onion.",
    text_after="Crush the garlic and rest 10 minutes, then fry the garlic and onion.",
)
GOOD_UPDATE = updated(
    ingredients=ORIGINAL.ingredients + ["1 lemon, juiced"],
    steps=["Crush the garlic and rest 10 minutes, then fry the garlic and onion.", ORIGINAL.steps[1]],
)


def check(updated_recipe, changes, skipped=(), approved=APPROVED):
    return validate_recipe_changes(approved, ORIGINAL, updated_recipe, list(changes), list(skipped))


def rules_of(result):
    return sorted({error[:2] for error in result.errors})


def test_valid_run_passes_and_only_the_rewrite_needs_the_verifier():
    result = check(GOOD_UPDATE, [ADD_LEMON, TECHNIQUE_GARLIC])
    assert result.errors == []
    assert result.unproven_changes == [TECHNIQUE_GARLIC]


def test_declining_with_a_reason_is_valid():
    result = check(ORIGINAL, [], [SkippedItem(rule_id="SYN-1", reason="no lemon fits"), SkippedItem(rule_id="BIO-2", reason="x")])
    assert result.errors == []


def test_c1_action_not_accounted_for():
    result = check(updated(ingredients=ORIGINAL.ingredients + ["1 lemon, juiced"]), [ADD_LEMON])
    assert rules_of(result) == ["C1"] and "BIO-2" in result.errors[0]


def test_c1_applied_and_declined_and_empty_reason():
    result = check(
        updated(ingredients=ORIGINAL.ingredients + ["1 lemon, juiced"]),
        [ADD_LEMON],
        [SkippedItem(rule_id="SYN-1", reason="changed my mind"), SkippedItem(rule_id="BIO-2", reason=" ")],
    )
    assert rules_of(result) == ["C1"] and len(result.errors) == 2


def test_c2_change_cites_nothing_or_unapproved_fact():
    no_citation = RecipeChange(rule_ids=[], text_after="1 lemon, juiced")
    unapproved = RecipeChange(rule_ids=["BIO-99"], text_after="1 lemon, juiced")
    both_updated = updated(ingredients=ORIGINAL.ingredients + ["1 lemon, juiced"])
    skipped = [SkippedItem(rule_id="SYN-1", reason="r"), SkippedItem(rule_id="BIO-2", reason="r")]
    assert rules_of(check(both_updated, [no_citation], skipped)) == ["C2"]
    assert rules_of(check(both_updated, [unapproved], skipped)) == ["C2"]


def test_c2_declining_an_action_that_was_never_approved():
    skipped = [SkippedItem(rule_id="SYN-1", reason="r"), SkippedItem(rule_id="BIO-2", reason="r"), SkippedItem(rule_id="X-1", reason="r")]
    assert rules_of(check(ORIGINAL, [], skipped)) == ["C2"]


def test_c3_added_text_missing_from_new_recipe():
    result = check(ORIGINAL, [ADD_LEMON], [SkippedItem(rule_id="BIO-2", reason="r")])
    assert rules_of(result) == ["C3"] and "1 lemon, juiced" in result.errors[0]


def test_c3_removed_text_still_present():
    change = RecipeChange(rule_ids=["SYN-1"], text_before="1 onion", text_after="1 shallot")
    result = check(updated(ingredients=ORIGINAL.ingredients + ["1 shallot"]), [change], [SkippedItem(rule_id="BIO-2", reason="r")])
    assert rules_of(result) == ["C3"] and "still in the updated recipe" in result.errors[0]


def test_c3_text_before_not_in_original_recipe():
    change = RecipeChange(rule_ids=["SYN-1"], text_before="1 carrot", text_after="1 lemon, juiced")
    result = check(updated(ingredients=ORIGINAL.ingredients + ["1 lemon, juiced"]), [change], [SkippedItem(rule_id="BIO-2", reason="r")])
    assert rules_of(result) == ["C3"] and "original recipe contained" in result.errors[0]


def test_c3_change_with_no_text():
    change = RecipeChange(rule_ids=["SYN-1"])
    assert "C3" in rules_of(check(ORIGINAL, [change], [SkippedItem(rule_id="BIO-2", reason="r")]))


def test_c3_ignores_case_and_whitespace():
    change = RecipeChange(rule_ids=["SYN-1"], text_after="1  LEMON, juiced")
    result = check(updated(ingredients=ORIGINAL.ingredients + ["1 lemon, juiced"]), [change], [SkippedItem(rule_id="BIO-2", reason="r")])
    assert result.errors == []


def test_c5_silent_deletion():
    result = check(updated(ingredients=["1 cup red lentils", "1 onion"]), [], [SkippedItem(rule_id="SYN-1", reason="r"), SkippedItem(rule_id="BIO-2", reason="r")])
    assert rules_of(result) == ["C5"] and "2 cloves garlic" in result.errors[0]


def test_c5_recorded_removal_passes():
    removal = RecipeChange(rule_ids=["BIO-2"], text_before="2 cloves garlic")
    result = check(updated(ingredients=["1 cup red lentils", "1 onion"]), [removal], [SkippedItem(rule_id="SYN-1", reason="r")])
    assert result.errors == []
    assert result.unproven_changes == []


def test_unproven_changes_are_empty_when_there_are_errors():
    result = check(ORIGINAL, [TECHNIQUE_GARLIC], [SkippedItem(rule_id="SYN-1", reason="r")])
    assert result.errors and result.unproven_changes == []
