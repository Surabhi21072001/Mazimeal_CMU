import dspy
from dspy.utils.exceptions import AdapterParseError

from governance_retry import run_with_governance_retry


def test_passes_first_time_without_feedback():
    feedback_seen = []

    def model_step(feedback):
        feedback_seen.append(feedback)
        return dspy.Prediction(value=1)

    prediction, errors, attempts = run_with_governance_retry(model_step, lambda p: [])
    assert prediction.value == 1 and errors == [] and attempts == 1
    assert feedback_seen == [""]


def test_retry_passes_exact_errors_as_feedback_then_succeeds():
    feedback_seen = []

    def model_step(feedback):
        feedback_seen.append(feedback)
        return dspy.Prediction(ok=len(feedback_seen) == 2)

    def validate(prediction):
        return [] if prediction.ok else ["S1: first", "S3: second"]

    prediction, errors, attempts = run_with_governance_retry(model_step, validate)
    assert prediction.ok and attempts == 2
    assert feedback_seen == ["", "S1: first\nS3: second"]
    assert errors == ["S1: first", "S3: second"]


def test_gives_up_after_two_retries():
    calls = []

    def model_step(feedback):
        calls.append(feedback)
        return dspy.Prediction()

    prediction, errors, attempts = run_with_governance_retry(model_step, lambda p: ["S2: bad"])
    assert prediction is None and attempts == 3 and len(calls) == 3
    assert errors == ["S2: bad"] * 3


def cut_off_answer():
    return AdapterParseError("JSONAdapter", dspy.Signature("question -> answer"), "{ truncated")


def test_unreadable_answer_is_a_failed_attempt_and_the_retry_can_succeed():
    feedback_seen = []

    def model_step(feedback):
        feedback_seen.append(feedback)
        if len(feedback_seen) == 1:
            raise cut_off_answer()
        return dspy.Prediction(value=1)

    prediction, errors, attempts = run_with_governance_retry(model_step, lambda p: [])
    assert prediction.value == 1 and attempts == 2
    assert errors[0].startswith("FORMAT") and feedback_seen[1] == errors[0]


def test_unreadable_answer_every_time_returns_none_instead_of_crashing():
    def model_step(feedback):
        raise cut_off_answer()

    prediction, errors, attempts = run_with_governance_retry(model_step, lambda p: [])
    assert prediction is None and attempts == 3 and len(errors) == 3
