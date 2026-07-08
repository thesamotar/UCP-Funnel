"""GET /api/config — localhost demo convenience: hand the browser the same
keys and model names the wrapper itself uses."""
import os

from fastapi import APIRouter

from .. import llm

router = APIRouter()


@router.get("/api/config")
def config():
    return {
        "gemini_key": os.environ.get("GEMINI_API_KEY", ""),
        "anthropic_key": os.environ.get("ANTHROPIC_API_KEY", ""),
        "gemini_model": llm.GEMINI_MODEL,
        "anthropic_model": llm.ANTHROPIC_MODEL,
    }
