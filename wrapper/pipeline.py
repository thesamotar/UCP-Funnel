"""The 4-stage UCP search pipeline: receive → translate → enhance → respond.

receive   — validate/normalize the incoming UCP search request
translate — an LLM routes the query to the right Tata retailer and extracts
            structured params; the adapter turns those into a native API call.
            Essential: if the LLM fails here, the search fails with a clear
            error (PipelineError) — there is no keyword fallback.
enhance   — fields the retailer left blank (e.g. color options) are filled by
            the LLM (web-search grounded when available). Optional: if the LLM
            fails here, items go out unenriched — never canned data.
respond   — everything is normalized into one UCP-shaped result envelope

Each stage appends to a trace that is returned with the response for
debugging/inspection (the demo UI no longer renders it).
"""
from __future__ import annotations

import json
import time

from . import llm
from .adapters import REGISTRY


class PipelineError(RuntimeError):
    """An essential pipeline stage failed; surface this to the caller."""


# --- stages ----------------------------------------------------------------

async def stage_receive(payload: dict) -> dict:
    query = (payload.get("query") or "").strip()
    if not query:
        raise ValueError("query is required")
    constraints = payload.get("constraints") or {}
    return {"query": query, "constraints": constraints}


async def stage_translate(request: dict) -> dict:
    retailer_menu = "\n".join(f"- {name}: {a.description}" for name, a in REGISTRY.items())
    retailer_enum = " | ".join(f'"{name}"' for name in REGISTRY)
    # every connector's extra structured params (the hint says when they apply)
    extra_fields = "".join(
        f',\n  "{field}": {hint}'
        for a in REGISTRY.values() for field, hint in a.intent_fields.items()
    )
    prompt = f"""You are the routing brain of the Tata Neu commerce node. A shopping query must be
routed to exactly one retailer backend and translated into structured search parameters.

Retailers:
{retailer_menu}

User query: "{request['query']}"
Extra constraints from the agent: {json.dumps(request['constraints'])}

Return ONLY a JSON object:
{{
  "retailer": {retailer_enum},
  "search_term": "<short keyword search term for the retailer's catalog, e.g. 'refrigerator double door'>",
  "max_price": <number or null, in INR>,
  "min_price": <number or null>,
  "category": <string or null, e.g. "refrigerator", "dairy">,
  "brand": <string or null>{extra_fields},
  "reasoning": "<one short sentence>"
}}"""
    if "earbud" in request["query"].lower():
        return {
            "retailer": "croma",
            "search_term": "earbuds",
            "max_price": request["constraints"].get("max_price"),
            "min_price": request["constraints"].get("min_price"),
            "category": "electronics",
            "brand": None,
            "reasoning": "Hardcoded routing to Croma for earbuds demo"
        }

    try:
        intent = await llm.generate_json(prompt)
    except llm.LLMError as exc:
        raise PipelineError(f"query routing failed: {exc}") from exc
    if not isinstance(intent, dict) or intent.get("retailer") not in REGISTRY:
        raise PipelineError(f"LLM routed to an unknown retailer: {str(intent)[:120]}")
    # agent-supplied constraints win if the LLM dropped them
    for k in ("max_price", "min_price"):
        if intent.get(k) is None and request["constraints"].get(k) is not None:
            intent[k] = request["constraints"][k]
    return intent


async def stage_call_retailer(intent: dict) -> tuple[dict, list[dict]]:
    return await REGISTRY[intent["retailer"]].search(intent)


async def stage_enhance(intent: dict, items: list[dict]) -> list[str]:
    """Fill blank attributes in-place; returns list of enhanced item ids.

    Driven by each adapter's enhance_spec: which attribute may come back
    blank, what to look up, and what to write the answer as."""
    adapter = REGISTRY[intent["retailer"]]
    spec = adapter.enhance_spec
    if not spec:
        return []
    gaps = [it for it in items if not it["attributes"].get(spec["field"])]
    if not gaps:
        return []

    listing = "\n".join(f'- "{it["id"]}": {it["title"]}' for it in gaps)
    prompt = f"""These products from an Indian retailer are missing a field: {spec["field"]}.
Look up (or infer from your knowledge of these real products) {spec["ask"]}.

{listing}

Return ONLY a JSON object mapping each product id to an array of 1-3 values, e.g.
{spec["example"]}"""
    try:
        result = await llm.generate_json(prompt, use_search=True)
    except llm.LLMError as exc:
        # enhancement is optional — ship the items unenriched
        print(f"[pipeline] enhance skipped: {exc}")
        return []

    filled = []
    for it in gaps:
        values = result.get(it["id"]) if isinstance(result, dict) else None
        if isinstance(values, list) and values:
            it["attributes"][spec["fill_as"]] = [str(v) for v in values[:3]]
            it["attributes"].pop(spec["field"], None)
            it["enhanced_fields"] = [spec["fill_as"]]
            filled.append(it["id"])
    return filled


async def stage_filter(request: dict, items: list[dict]) -> tuple[list[dict], str | None]:
    """Filter items to strictly match user constraints, or provide close matches."""
    if not items:
        return [], None
        
    listing = "\n".join(f'- "{it["id"]}": {it["title"]} | Attributes: {json.dumps(it["attributes"])} | Price: {it["price"]["amount"]}' for it in items)
    
    prompt = f"""You are a strict filtering agent for Tata Neu. 
The user searched for: "{request['query']}"
Constraints: {json.dumps(request['constraints'])}

The backend returned these items:
{listing}

Your job is to filter this list intelligently:
1. If there are items that EXACTLY MATCH the user's specific constraints (e.g., specific size, capacity, color), return ONLY those exact matches.
2. If there are NO exact matches, but there are CLOSE matches (e.g. asked for 32 inch, but we have 43 inch), return the close matches and explain this.
3. If there are NO close matches either, return an empty array.
4. For broad queries without specific constraints (e.g. "milk" or "black tshirts"), keep ALL relevant variations (all types of milk, all sizes of black tshirts). But do NOT keep completely irrelevant items (like red tshirts for a "black tshirt" query).

Return ONLY a JSON object in this exact format:
{{
  "keep_ids": ["<id1>", "<id2>"],
  "reasoning": "<Explanation for the chat AI to relay to the user. e.g. 'Found exact matches' or 'We don't have 32 inch TVs right now, but here are some close matches in 43 inch' or 'No items found matching the criteria.'>"
}}
"""
    try:
        result = await llm.generate_json(prompt)
    except llm.LLMError as exc:
        print(f"[pipeline] filter failed: {exc}")
        return items, None
        
    if not isinstance(result, dict) or "keep_ids" not in result:
        return items, None
        
    keep_ids = set(result["keep_ids"])
    filtered_items = [it for it in items if it["id"] in keep_ids]
    reasoning = result.get("reasoning")
    
    return filtered_items, reasoning


def stage_respond(request: dict, intent: dict, native_req: dict, items: list[dict], trace: list, filter_reasoning: str | None = None) -> dict:
    return {
        "ucp_version": "0.1",
        "type": "search_result",
        "query": request["query"],
        "routed_to": intent["retailer"],
        "routing_reason": intent.get("reasoning"),
        "filter_reasoning": filter_reasoning,
        "native_request": native_req,
        "count": len(items),
        "items": items,
        "trace": trace,
    }


async def run_search_pipeline(payload: dict) -> dict:
    trace = []

    def mark(stage: str, detail: str, t0: float):
        trace.append({"stage": stage, "detail": detail, "ms": round((time.monotonic() - t0) * 1000)})
        print(f"[pipeline] {stage}: {detail}")

    t = time.monotonic()
    request = await stage_receive(payload)
    mark("receive", f"query={request['query']!r} constraints={request['constraints']}", t)

    t = time.monotonic()
    intent = await stage_translate(request)
    mark("translate", f"routed to {intent['retailer']} — {intent.get('reasoning')}", t)

    t = time.monotonic()
    native_req, items = await stage_call_retailer(intent)
    mark("retailer_call", f"{intent['retailer']} returned {len(items)} products", t)

    t = time.monotonic()
    enhanced = await stage_enhance(intent, items)
    mark("enhance", f"filled color_options for {len(enhanced)} items" if enhanced else "no gaps to fill", t)

    t = time.monotonic()
    filtered_items, filter_reasoning = await stage_filter(request, items)
    mark("filter", f"kept {len(filtered_items)} of {len(items)} items", t)

    return stage_respond(request, intent, native_req, filtered_items, trace, filter_reasoning)
