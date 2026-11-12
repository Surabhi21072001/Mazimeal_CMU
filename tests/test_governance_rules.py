from domain_models import AlreadyAppliedFact, ApplicableFact, SkippedItem
from governance_rules import validate_fact_selection

RECIPE_TEXT = "Lentil Soup\n\nIngredients:\n- 1 cup red lentils\n- 2 cloves garlic\n\nSteps:\n1. Simmer."
GIVEN = ["BIO-1", "BIO-2"]


def select(applicable=(), skipped=(), given=GIVEN, pending="", already=()):
    return validate_fact_selection(given, list(applicable), list(already), list(skipped), RECIPE_TEXT, pending)


def test_valid_selection_passes():
    errors = select(
        applicable=[ApplicableFact(rule_id="BIO-1", trigger_ingredients=["red lentils"])],
        skipped=[SkippedItem(rule_id="BIO-2", reason="no tomatoes in the recipe")],
    )
    assert errors == []


def test_s1_fact_left_unjudged():
    errors = select(applicable=[ApplicableFact(rule_id="BIO-1", trigger_ingredients=["red lentils"])])
    assert len(errors) == 1 and errors[0].startswith("S1") and "BIO-2" in errors[0]


def test_s1_judging_nothing_fails_for_every_fact():
    assert len(select()) == 2


def test_s1_empty_reason():
    errors = select(
        applicable=[ApplicableFact(rule_id="BIO-1", trigger_ingredients=["red lentils"])],
        skipped=[SkippedItem(rule_id="BIO-2", reason="  ")],
    )
    assert len(errors) == 1 and "without a reason" in errors[0]


def test_s1_fact_both_applicable_and_skipped():
    errors = select(
        applicable=[
            ApplicableFact(rule_id="BIO-1", trigger_ingredients=["red lentils"]),
            ApplicableFact(rule_id="BIO-2", trigger_ingredients=["garlic"]),
        ],
        skipped=[SkippedItem(rule_id="BIO-2", reason="not needed")],
    )
    assert len(errors) == 1 and "BIO-2" in errors[0] and "2 times" in errors[0]


def test_s2_invented_fact():
    errors = select(
        applicable=[ApplicableFact(rule_id="BIO-1", trigger_ingredients=["red lentils"])],
        skipped=[
            SkippedItem(rule_id="BIO-2", reason="not relevant"),
            SkippedItem(rule_id="BIO-99", reason="not relevant"),
        ],
    )
    assert len(errors) == 1 and errors[0].startswith("S2") and "BIO-99" in errors[0]


def test_s3_trigger_not_in_recipe():
    errors = select(
        applicable=[
            ApplicableFact(rule_id="BIO-1", trigger_ingredients=["tomato"]),
            ApplicableFact(rule_id="BIO-2", trigger_ingredients=["garlic"]),
        ],
    )
    assert len(errors) == 1 and errors[0].startswith("S3") and '"tomato"' in errors[0]


def test_s3_ignores_case_and_extra_whitespace():
    errors = select(
        applicable=[
            ApplicableFact(rule_id="BIO-1", trigger_ingredients=["Red   Lentils"]),
            ApplicableFact(rule_id="BIO-2", trigger_ingredients=["GARLIC"]),
        ],
    )
    assert errors == []


def test_s3_rephrased_trigger_fails():
    errors = select(
        applicable=[
            ApplicableFact(rule_id="BIO-1", trigger_ingredients=["lentils, red"]),
            ApplicableFact(rule_id="BIO-2", trigger_ingredients=["garlic"]),
        ],
    )
    assert len(errors) == 1 and errors[0].startswith("S3")


def test_s3_no_trigger_ingredients():
    errors = select(
        applicable=[
            ApplicableFact(rule_id="BIO-1", trigger_ingredients=[]),
            ApplicableFact(rule_id="BIO-2", trigger_ingredients=["garlic"]),
        ],
    )
    assert len(errors) == 1 and "no trigger ingredient" in errors[0]


def test_s3_trigger_found_in_pending_actions():
    applicable = [
        ApplicableFact(rule_id="BIO-1", trigger_ingredients=["lemon juice"]),
        ApplicableFact(rule_id="BIO-2", trigger_ingredients=["garlic"]),
    ]
    assert select(applicable=applicable)[0].startswith("S3")
    assert select(applicable=applicable, pending="Add lemon juice at the end.") == []


def test_invented_fact_is_not_also_reported_by_s3():
    errors = select(
        applicable=[
            ApplicableFact(rule_id="BIO-1", trigger_ingredients=["red lentils"]),
            ApplicableFact(rule_id="BIO-99", trigger_ingredients=["tomato"]),
        ],
        skipped=[SkippedItem(rule_id="BIO-2", reason="not relevant")],
    )
    assert [e[:2] for e in errors] == ["S2"]


# Rule S1 with the third list, and rule S4
def test_s1_already_applied_counts_as_judged():
    errors = select(
        applicable=[ApplicableFact(rule_id="BIO-1", trigger_ingredients=["red lentils"])],
        already=[AlreadyAppliedFact(rule_id="BIO-2", evidence_quote="2 cloves garlic")],
    )
    assert errors == []


def test_s1_fact_in_applicable_and_already_applied():
    errors = select(
        applicable=[ApplicableFact(rule_id="BIO-1", trigger_ingredients=["red lentils"])],
        already=[AlreadyAppliedFact(rule_id="BIO-1", evidence_quote="1 cup red lentils")],
        skipped=[SkippedItem(rule_id="BIO-2", reason="not relevant")],
    )
    assert len(errors) == 1 and errors[0].startswith("S1") and "BIO-1" in errors[0]


def test_s2_invented_fact_in_already_applied():
    errors = select(
        already=[AlreadyAppliedFact(rule_id="BIO-99", evidence_quote="2 cloves garlic")],
        skipped=[SkippedItem(rule_id="BIO-1", reason="r"), SkippedItem(rule_id="BIO-2", reason="r")],
    )
    assert [e[:2] for e in errors] == ["S2"]


def test_s4_quote_not_in_recipe():
    errors = select(
        already=[AlreadyAppliedFact(rule_id="BIO-1", evidence_quote="Crush the garlic and rest 10 minutes")],
        skipped=[SkippedItem(rule_id="BIO-2", reason="r")],
    )
    assert len(errors) == 1 and errors[0].startswith("S4") and "BIO-1" in errors[0]


def test_s4_empty_quote():
    errors = select(
        already=[AlreadyAppliedFact(rule_id="BIO-1", evidence_quote="  ")],
        skipped=[SkippedItem(rule_id="BIO-2", reason="r")],
    )
    assert len(errors) == 1 and "no evidence quote" in errors[0]


def test_s4_quote_ignores_case_and_whitespace():
    errors = select(
        already=[AlreadyAppliedFact(rule_id="BIO-1", evidence_quote="2  CLOVES garlic")],
        skipped=[SkippedItem(rule_id="BIO-2", reason="r")],
    )
    assert errors == []


def test_s4_quote_found_only_in_pending_actions_fails():
    errors = select(
        already=[AlreadyAppliedFact(rule_id="BIO-1", evidence_quote="lemon juice")],
        skipped=[SkippedItem(rule_id="BIO-2", reason="r")],
        pending="Add lemon juice at the end.",
    )
    assert len(errors) == 1 and errors[0].startswith("S4")


def test_s4_quote_may_span_lines_and_include_list_numbers():
    recipe = "Soup\n\nIngredients:\n- lentils\n\nSteps:\n1. Cook the lentils in water.\n2. Bring to a boil and simmer."
    errors = validate_fact_selection(
        ["BIO-1"], [], [AlreadyAppliedFact(rule_id="BIO-1", evidence_quote="Cook the lentils in water.\n2. Bring to a boil")], [],
        recipe)
    assert errors == []


def test_s3_and_s4_treat_typographic_hyphens_and_nonbreaking_spaces_as_plain():
    recipe = "Soup\n\nIngredients:\n- low-fat yogurt\n\nSteps:\n1. Serve with low-fat yogurt."
    errors = validate_fact_selection(
        ["BIO-1", "BIO-2"],
        [ApplicableFact(rule_id="BIO-1", trigger_ingredients=["low\u2011fat\u202fyogurt"])],
        [AlreadyAppliedFact(rule_id="BIO-2", evidence_quote="Serve with low\u2011fat yogurt")],
        [], recipe)
    assert errors == []


def test_without_list_markers_handles_inserted_step_labels():
    from governance_rules import without_list_markers
    assert without_list_markers("5a. Soak the beans.\n- lime juice\n12. Serve.") == "Soak the beans.\nlime juice\nServe."
    assert without_list_markers("1.5 cups water") == "1.5 cups water"
