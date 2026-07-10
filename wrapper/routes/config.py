"""GET /api/config — hand the browser the model names the wrapper uses.

The server's API keys are only included when EXPOSE_CONFIG_KEYS=1 (a localhost
demo convenience). On a public deployment leave it unset — visitors paste
their own key into the UI banner instead.
"""
import os

from fastapi import APIRouter

from .. import llm

router = APIRouter()


@router.get("/api/config")
def config():
    expose = os.environ.get("EXPOSE_CONFIG_KEYS", "").lower() in ("1", "true", "yes")
    return {
        "gemini_key": os.environ.get("GEMINI_API_KEY", "") if expose else "",
        "anthropic_key": os.environ.get("ANTHROPIC_API_KEY", "") if expose else "",
        "gemini_model": llm.GEMINI_MODEL,
        "anthropic_model": llm.ANTHROPIC_MODEL,
    }
