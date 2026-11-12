"""The retry loop shared by every governed stage. Orchestration layer."""
from typing import Callable

import dspy
from dspy.utils.exceptions import AdapterParseError

MAX_RETRIES = 2
UNREADABLE_ANSWER_ERROR = (
    "FORMAT: your last answer could not be read as the required output fields. It may have been cut off. "
    "Return every output field, and keep the answer short."
)


def run_with_governance_retry(
    model_step: Callable[[str], dspy.Prediction],
    validate: Callable[[dspy.Prediction], list[str]],
    max_retries: int = MAX_RETRIES,
) -> tuple[dspy.Prediction | None, list[str], int]:
    """Run model_step, validate it, and on failure rerun it with the exact error list as feedback.

    model_step takes governance_feedback ("" on the first attempt) and returns a prediction.
    validate returns the list of rule violations (empty means pass).
    An answer the adapter cannot parse (for example cut off) counts as a failed attempt.
    Returns (prediction or None if every attempt failed, every violation seen, number of attempts).
    """
    all_errors: list[str] = []
    governance_feedback = ""
    for attempt in range(1, max_retries + 2):
        try:
            prediction = model_step(governance_feedback)
        except AdapterParseError:  # a truncated or malformed answer counts as a failed attempt, not a crash
            errors = [UNREADABLE_ANSWER_ERROR]
        else:
            errors = validate(prediction)
        if not errors:
            return prediction, all_errors, attempt
        all_errors.extend(errors)
        governance_feedback = "\n".join(errors)
    return None, all_errors, max_retries + 1
