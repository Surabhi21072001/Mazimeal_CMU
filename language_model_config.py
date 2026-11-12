"""Points DSPy at gpt-oss-120b on Groq. The key is read from the environment, never stored."""
import os

import dspy

API_BASE = "https://api.groq.com/openai/v1"
MODEL = "openai/openai/gpt-oss-120b"  # "openai/" = OpenAI-compatible API, then Groq's model id
API_KEY_ENV_VAR = "GPT_OSS_120B_API_KEY"
MAX_OUTPUT_TOKENS = 12000  # reasoning tokens count; the Chef returns the whole recipe, and long answers were cut off


def configure_language_model() -> None:
    api_key = os.environ.get(API_KEY_ENV_VAR)
    if not api_key:
        raise RuntimeError(f"Set the {API_KEY_ENV_VAR} environment variable.")
    dspy.configure(lm=dspy.LM(MODEL, api_base=API_BASE, api_key=api_key, max_tokens=MAX_OUTPUT_TOKENS), track_usage=True)
