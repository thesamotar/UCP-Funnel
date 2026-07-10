"""Provider-agnostic LLM client for the wrapper's internal reasoning.

Works with either a Claude key (ANTHROPIC_API_KEY) or a Gemini key
(GEMINI_API_KEY) — whichever is set. If both are set, LLM_PROVIDER
("anthropic" | "gemini") picks; default preference is anthropic.

Used in two pipeline stages:
  - translate: decide which Tata retailer handles the query + extract params
  - enhance:   fill blank fields in retailer responses (web search grounding
               when the provider supports it, plain generation otherwise)

No fallbacks: every call has a hard timeout, and any failure raises LLMError.
The caller decides whether the stage is essential (translate → error response)
or optional (enhance → skipped).
"""
import asyncio
import json
import os
import re

import httpx

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Hard per-call deadlines (seconds). Search-grounded calls are given longer
# because the provider browses the web before answering.
TIMEOUT_S = float(os.environ.get("LLM_TIMEOUT_S", "25"))
SEARCH_TIMEOUT_S = float(os.environ.get("LLM_SEARCH_TIMEOUT_S", "45"))

_JSON_BLOCK = re.compile(r"\{.*\}|\[.*\]", re.S)


class LLMError(RuntimeError):
    """An LLM call failed, timed out, or returned something unusable."""


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


async def _generate_anthropic(prompt: str, use_search: bool, timeout: float) -> str:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=anthropic_key(), timeout=timeout, max_retries=0)
    kwargs: dict = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": prompt}],
    }
    if use_search:
        kwargs["tools"] = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}]

    async def run() -> str:
        # Always stream: non-streaming requests with search tools run long and
        # get dropped upstream (the exact hang this replaces). The stream keeps
        # the read timeout from firing, so enforce wall-clock time ourselves.
        async with client.messages.stream(**kwargs) as stream:
            response = await asyncio.wait_for(stream.get_final_message(), timeout)
        return "".join(b.text for b in response.content if b.type == "text")

    try:
        return await run()
    except Exception:
        if not use_search:
            raise
        # web search unavailable or too slow — one plain retry, still the LLM
        kwargs.pop("tools", None)
        return await run()


async def _generate_gemini(prompt: str, use_search: bool, timeout: float) -> str:
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
    return "".join(p.get("text", "") for p in parts)


async def generate(prompt: str, use_search: bool = False, timeout: float | None = None) -> str:
    active = provider()
    if not active:
        raise LLMError("no LLM key configured — set ANTHROPIC_API_KEY or GEMINI_API_KEY")
    if timeout is None:
        timeout = SEARCH_TIMEOUT_S if use_search else TIMEOUT_S
    try:
        if active == "anthropic":
            text = await _generate_anthropic(prompt, use_search, timeout)
        else:
            text = await _generate_gemini(prompt, use_search, timeout)
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError(f"{active} call failed: {exc}") from exc
    if not text:
        raise LLMError(f"{active} returned an empty response")
    return text


async def generate_json(prompt: str, use_search: bool = False) -> dict | list:
    """Ask the LLM for JSON and parse leniently (strips prose/code fences)."""
    text = await generate(prompt, use_search=use_search)
    match = _JSON_BLOCK.search(text)
    if not match:
        raise LLMError(f"no JSON in LLM response: {text[:120]!r}")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise LLMError(f"unparseable JSON from LLM: {exc}") from exc
