"""
Guards on model output.

The product promise is that figures come from the database and the rules, and
that a model only changes wording. These two checks enforce it cheaply: a
rewrite that introduces a number the source did not have is thrown away, and so
is anything that does not read like a sentence.
"""
import re

NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def numbers_in(text: str) -> set[str]:
    return {n.replace(",", "") for n in NUMBER.findall(text or "")}


def borrowed_numbers(candidate: str, source: str) -> set[str]:
    """Numbers the candidate has that the source did not. Empty set is good."""
    return numbers_in(candidate) - numbers_in(source)


def looks_like_prose(text: str, max_chars: int = 400) -> bool:
    """Catch empty strings, refusals, and a model that answered with a list.

    `max_chars` exists because the two callers want different things: a rewrite
    of one tip stays short, while a summary covering every rule on a recipe is
    allowed to run long - the card it sits on collapses.
    """
    if not text or len(text) < 15 or len(text) > max_chars:
        return False
    if text.lstrip().startswith(("-", "*", "#", "{", "[")):
        return False
    lowered = text.lower()
    if lowered.startswith(("i cannot", "i can't", "sorry", "as an ai")):
        return False
    return True
