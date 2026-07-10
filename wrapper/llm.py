"""Provider-agnostic LLM client.

Works with either a Claude key (ANTHROPIC_API_KEY) or a Gemini key
(GEMINI_API_KEY) — whichever is set. If both are set, LLM_PROVIDER
("anthropic" | "gemini") picks; default preference is anthropic.

Two entry points:
  - generate/generate_json: single-prompt calls for the pipeline stages
    (translate routing, enhance gap-filling)
  - chat: multi-turn tool-use conversations for the /api/chat proxy — ONE
    server-side key powers every signed-in user's chat

No fallbacks: every call has a hard timeout, and any failure raises LLMError.
Anthropic calls always stream (non-streaming long calls get dropped upstream)
with the wall clock enforced by asyncio.wait_for.
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
# because the provider browses the web before answering; chat turns can carry
# long tool-use histories.
TIMEOUT_S = float(os.environ.get("LLM_TIMEOUT_S", "25"))
SEARCH_TIMEOUT_S = float(os.environ.get("LLM_SEARCH_TIMEOUT_S", "45"))
CHAT_TIMEOUT_S = float(os.environ.get("LLM_CHAT_TIMEOUT_S", "60"))

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


# --- multi-turn chat with tools (the /api/chat proxy) -------------------------
# History turns use the frontend's neutral shape:
#   {role: 'user', text}                                — user message
#   {role: 'model', text?, toolCalls?: [{id,name,args}]} — assistant turn
#   {toolResults: [{id, name, result}]}                  — executed tool results
# Tool defs are neutral too: {name, description, properties, required}.


async def _chat_anthropic(history: list[dict], system: str | None,
                          tools: list[dict] | None, timeout: float) -> dict:
    from anthropic import AsyncAnthropic

    messages = []
    for turn in history:
        if turn.get("role") == "user" and turn.get("text") is not None:
            messages.append({"role": "user", "content": turn["text"]})
        elif turn.get("role") == "model":
            content = []
            if turn.get("text"):
                content.append({"type": "text", "text": turn["text"]})
            for c in turn.get("toolCalls") or []:
                content.append({"type": "tool_use", "id": c["id"], "name": c["name"],
                                "input": c.get("args") or {}})
            if content:
                messages.append({"role": "assistant", "content": content})
        elif turn.get("toolResults"):
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": r["id"], "content": json.dumps(r["result"])}
                for r in turn["toolResults"]
            ]})

    kwargs: dict = {"model": ANTHROPIC_MODEL, "max_tokens": 8192, "messages": messages}
    if system:
        kwargs["system"] = system
    if tools:
        kwargs["tools"] = [{
            "name": t["name"], "description": t["description"],
            "input_schema": {"type": "object", "properties": t["properties"],
                             "required": t["required"]},
        } for t in tools]

    client = AsyncAnthropic(api_key=anthropic_key(), timeout=timeout, max_retries=0)
    async with client.messages.stream(**kwargs) as stream:
        response = await asyncio.wait_for(stream.get_final_message(), timeout)
    return {
        "text": "".join(b.text for b in response.content if b.type == "text"),
        "toolCalls": [{"id": b.id, "name": b.name, "args": b.input or {}}
                      for b in response.content if b.type == "tool_use"],
    }


async def _chat_gemini(history: list[dict], system: str | None,
                       tools: list[dict] | None, timeout: float) -> dict:
    import uuid

    contents = []
    for turn in history:
        if turn.get("role") == "user" and turn.get("text") is not None:
            contents.append({"role": "user", "parts": [{"text": turn["text"]}]})
        elif turn.get("role") == "model":
            parts = []
            if turn.get("text"):
                parts.append({"text": turn["text"]})
            for c in turn.get("toolCalls") or []:
                parts.append({"functionCall": {"name": c["name"], "args": c.get("args") or {}}})
            if parts:
                contents.append({"role": "model", "parts": parts})
        elif turn.get("toolResults"):
            contents.append({"role": "user", "parts": [
                {"functionResponse": {"name": r["name"], "response": {"result": r["result"]}}}
                for r in turn["toolResults"]
            ]})

    body: dict = {"contents": contents, "generationConfig": {"temperature": 0.7}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if tools:
        body["tools"] = [{"functionDeclarations": [{
            "name": t["name"], "description": t["description"],
            "parameters": {"type": "OBJECT", "properties": t["properties"],
                           "required": t["required"]},
        } for t in tools]}]

    url = f"{GEMINI_API_BASE}/{GEMINI_MODEL}:generateContent"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, params={"key": gemini_key()}, json=body)
        resp.raise_for_status()
        data = resp.json()
    parts = data["candidates"][0]["content"]["parts"]
    return {
        "text": "".join(p.get("text", "") for p in parts),
        "toolCalls": [{"id": f"call_{uuid.uuid4().hex[:8]}", "name": p["functionCall"]["name"],
                       "args": p["functionCall"].get("args") or {}}
                      for p in parts if p.get("functionCall")],
    }


async def chat(history: list[dict], system: str | None = None,
               tools: list[dict] | None = None) -> dict:
    """One assistant turn over a neutral history. Returns {text, toolCalls}."""
    active = provider()
    if not active:
        raise LLMError("no LLM key configured — set ANTHROPIC_API_KEY or GEMINI_API_KEY")
    try:
        if active == "anthropic":
            return await _chat_anthropic(history, system, tools, CHAT_TIMEOUT_S)
        return await _chat_gemini(history, system, tools, CHAT_TIMEOUT_S)
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError(f"{active} chat call failed: {exc}") from exc


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
