"""GET /api/config — public boot config for the frontend.

Hands the browser the Supabase project URL + anon (publishable) key so
supabase-js can run login, and the model name for the header chip. No LLM
keys ever leave the server — chat goes through POST /api/chat.
"""
import os

from fastapi import APIRouter

from .. import llm

router = APIRouter()


@router.get("/api/config")
def config():
    return {
        "supabase_url": os.environ.get("SUPABASE_URL", ""),
        "supabase_anon_key": os.environ.get("SUPABASE_ANON_KEY", ""),
        "provider": llm.provider(),
        "model": llm.ANTHROPIC_MODEL if llm.provider() == "anthropic" else llm.GEMINI_MODEL,
    }
