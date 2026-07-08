"""Provider-agnostic LLM client for the wrapper's internal reasoning.

Works with either a Claude key (ANTHROPIC_API_KEY) or a Gemini key
(GEMINI_API_KEY) — whichever is set. If both are set, LLM_PROVIDER
("anthropic" | "gemini") picks; default preference is anthropic.

Used in two pipeline stages:
  - translate: decide which Tata retailer handles the query + extract params
  - enhance:   fill blank fields in retailer responses (web search grounding
               when the provider supports it, plain generation otherwise)

Everything degrades gracefully: with no key at all the callers fall back to
deterministic heuristics so the demo still runs end to end.
"""
import json
import os
import re

import httpx

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

_JSON_BLOCK = re.compile(r"\{.*\}|\[.*\]", re.S)


def gemini_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or None


def anthropic_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or None


def provider() -> str | None:
    forced = os.environ.get("LLM_PROVIDER")
    if forced in ("anthropic", "gemini"):
        return forced if (anthropic_key() if forced == "anthropic" else gemini_key()) else None
    if anthropic_key():
        return "anthropic"
    if gemini_key():
        return "gemini"
    return None


async def _generate_anthropic(prompt: str, use_search: bool) -> str | None:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=anthropic_key())
    kwargs: dict = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": prompt}],
    }
    if use_search:
        kwargs["tools"] = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}]
    try:
        response = await client.messages.create(**kwargs)
    except Exception:
        if not use_search:
            raise
        # web search may not be enabled for this org/model — retry plain
        kwargs.pop("tools", None)
        response = await client.messages.create(**kwargs)
    return "".join(b.text for b in response.content if b.type == "text") or None


async def _generate_gemini(prompt: str, use_search: bool, timeout: float) -> str | None:
    body: dict = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1},
    }
    if use_search:
        body["tools"] = [{"google_search": {}}]
    url = f"{GEMINI_API_BASE}/{GEMINI_MODEL}:generateContent"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, params={"key": gemini_key()}, json=body)
        resp.raise_for_status()
        data = resp.json()
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts) or None


async def generate(prompt: str, use_search: bool = False, timeout: float = 45.0) -> str | None:
    active = provider()
    if not active:
        return None
    try:
        if active == "anthropic":
            return await _generate_anthropic(prompt, use_search)
        return await _generate_gemini(prompt, use_search, timeout)
    except Exception as exc:  # demo: any LLM failure just triggers the fallback path
        print(f"[llm] {active} call failed: {exc}")
        return None


async def generate_json(prompt: str, use_search: bool = False) -> dict | list | None:
    """Ask the LLM for JSON and parse leniently (strips prose/code fences)."""
    text = await generate(prompt, use_search=use_search)
    if not text:
        return None
    match = _JSON_BLOCK.search(text)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
