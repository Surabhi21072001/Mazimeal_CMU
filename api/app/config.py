"""Settings, all from the environment so nothing needs editing to switch modes."""
import os
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"

# Where recipe, household and recommendation data comes from.
#   fixture   the json files in api/fixtures (default while the other
#             workstreams are still in progress)
#   supabase  their live functions, once we have a project of our own
REPO = os.environ.get("MAZI_REPO", "fixture")

# Who writes the suggestion text on the cook screen.
#   template  the rule's own words, rearranged. No model, no hallucination.
#   local     a small local model (Ollama's API) rephrases the template output
#   api       a hosted model, for the comparison we want to run later
PROVIDER = os.environ.get("MAZI_PROVIDER", "template")

# Any OpenAI-compatible chat endpoint. Ollama serves one at :11434/v1 and
# mlx-lm serves one at :8080/v1, so the same code runs either runtime and the
# small-versus-large comparison is a change of two variables.
LLM_URL = os.environ.get("MAZI_LLM_URL", "http://127.0.0.1:11434/v1")
LLM_MODEL = os.environ.get("MAZI_LLM_MODEL", "mlx-community/gemma-3-4b-it-4bit")
LLM_TIMEOUT = float(os.environ.get("MAZI_LLM_TIMEOUT", "60"))

# The frontend runs on Vite's dev server; add the deployed origin when there is one.
CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "MAZI_CORS_ORIGINS",
        "http://localhost:5173,http://localhost:5181,http://127.0.0.1:5173,http://127.0.0.1:5181",
    ).split(",")
    if o.strip()
]

# Vercel gives every push its own preview host, so an exact list cannot cover
# them and each new branch would otherwise be blocked by the browser with no
# server-side error to find. A pattern covers them once.
CORS_ORIGIN_REGEX = os.environ.get("MAZI_CORS_ORIGIN_REGEX") or None
