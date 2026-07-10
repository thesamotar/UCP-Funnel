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
import json
import time

from . import llm
from .adapters import ADAPTERS


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
    retailer_menu = "\n".join(f"- {name}: {a['description']}" for name, a in ADAPTERS.items())
    prompt = f"""You are the routing brain of the Tata Neu commerce node. A shopping query must be
routed to exactly one Tata retailer backend and translated into structured search parameters.

Retailers:
{retailer_menu}

User query: "{request['query']}"
Extra constraints from the agent: {json.dumps(request['constraints'])}

Return ONLY a JSON object:
{{
  "retailer": "bigbasket" | "croma",
  "search_term": "<short keyword search term for the retailer's catalog, e.g. 'refrigerator double door'>",
  "max_price": <number or null, in INR>,
  "min_price": <number or null>,
  "category": <string or null, e.g. "refrigerator", "dairy">,
  "brand": <string or null>,
  "min_capacity_litres": <number or null, only for fridges when the user gives a capacity like 200L+>,
  "reasoning": "<one short sentence>"
}}"""
    try:
        intent = await llm.generate_json(prompt)
    except llm.LLMError as exc:
        raise PipelineError(f"query routing failed: {exc}") from exc
    if not isinstance(intent, dict) or intent.get("retailer") not in ADAPTERS:
        raise PipelineError(f"LLM routed to an unknown retailer: {str(intent)[:120]}")
    # agent-supplied constraints win if the LLM dropped them
    for k in ("max_price", "min_price"):
        if intent.get(k) is None and request["constraints"].get(k) is not None:
            intent[k] = request["constraints"][k]
    return intent


async def stage_call_retailer(intent: dict) -> tuple[dict, list[dict]]:
    adapter = ADAPTERS[intent["retailer"]]
    return await adapter["search"](intent)


async def stage_enhance(intent: dict, items: list[dict]) -> list[str]:
    """Fill blank attributes in-place; returns list of enhanced item ids."""
    # only Croma models carry a color field; groceries have no gap to fill
    gaps = [
        it for it in items
        if it["source"]["retailer"] == "croma" and not it["attributes"].get("color")
    ]
    if not gaps:
        return []

    listing = "\n".join(f'- "{it["id"]}": {it["title"]}' for it in gaps)
    prompt = f"""These products from an Indian electronics retailer are missing their color options.
Look up (or infer from your knowledge of these real products) the colors each model is sold in, in India.

{listing}

Return ONLY a JSON object mapping each product id to an array of 1-3 color names, e.g.
{{"CRM-301202": ["Shiny Steel", "Ebony Sheen"]}}"""
    try:
        result = await llm.generate_json(prompt, use_search=True)
    except llm.LLMError as exc:
        # enhancement is optional — ship the items unenriched
        print(f"[pipeline] enhance skipped: {exc}")
        return []

    filled = []
    for it in gaps:
        colors = result.get(it["id"]) if isinstance(result, dict) else None
        if isinstance(colors, list) and colors:
            it["attributes"]["color_options"] = [str(c) for c in colors[:3]]
            it["attributes"].pop("color", None)
            it["enhanced_fields"] = ["color_options"]
            filled.append(it["id"])
    return filled


def stage_respond(request: dict, intent: dict, native_req: dict, items: list[dict], trace: list) -> dict:
    return {
        "ucp_version": "0.1",
        "type": "search_result",
        "query": request["query"],
        "routed_to": intent["retailer"],
        "routing_reason": intent.get("reasoning"),
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

    return stage_respond(request, intent, native_req, items, trace)
