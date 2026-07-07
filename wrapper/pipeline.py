"""The 4-stage UCP search pipeline: receive → translate → enhance → respond.

receive   — validate/normalize the incoming UCP search request
translate — an LLM routes the query to the right Tata retailer and extracts
            structured params; the adapter turns those into a native API call
enhance   — fields the retailer left blank (e.g. color options) are filled by
            Gemini (with Google Search grounding when available)
respond   — everything is normalized into one UCP-shaped result envelope

Each stage appends to a trace that is returned with the response so the demo
can show what happened under the hood.
"""
import json
import time

from . import llm
from .adapters import ADAPTERS

# --- deterministic fallbacks (used when no GEMINI_API_KEY is set) ---------

BIGBASKET_HINTS = {
    "milk", "bread", "egg", "eggs", "atta", "rice", "dal", "oil", "sugar", "salt",
    "tea", "coffee", "butter", "paneer", "curd", "biscuit", "snack", "chips",
    "banana", "onion", "tomato", "potato", "apple", "fruit", "vegetable",
    "grocery", "groceries", "detergent", "handwash", "dishwash", "noodles", "juice",
}
CROMA_HINTS = {
    "refrigerator", "fridge", "tv", "television", "laptop", "phone", "smartphone",
    "mobile", "washing", "machine", "ac", "conditioner", "headphone", "headphones",
    "earbuds", "speaker", "electronics", "appliance", "macbook", "samsung", "lg",
}

FALLBACK_COLORS = {
    "refrigerator": ["Shiny Steel", "Elegant Inox", "Ebony Black"],
    "television": ["Black"],
    "washing machine": ["White", "Silver"],
    "laptop": ["Silver", "Grey"],
    "audio": ["Black", "Blue"],
    "air conditioner": ["White"],
    "smartphone": ["Black", "Blue", "Silver"],
}


def _fallback_route(query: str, constraints: dict) -> dict:
    words = query.lower().split()
    bb = sum(1 for w in words if w.strip(".,") in BIGBASKET_HINTS)
    cr = sum(1 for w in words if w.strip(".,") in CROMA_HINTS)
    return {
        "retailer": "bigbasket" if bb > cr else "croma",
        "search_term": query,
        "max_price": constraints.get("max_price"),
        "min_price": constraints.get("min_price"),
        "category": None,
        "brand": None,
        "min_capacity_litres": None,
        "reasoning": "keyword fallback (no LLM key configured)",
    }


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
    intent = await llm.generate_json(prompt)
    if not isinstance(intent, dict) or intent.get("retailer") not in ADAPTERS:
        intent = _fallback_route(request["query"], request["constraints"])
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

    filled_via_llm = set()
    listing = "\n".join(f'- "{it["id"]}": {it["title"]}' for it in gaps)
    prompt = f"""These products from an Indian electronics retailer are missing their color options.
Look up (or infer from your knowledge of these real products) the colors each model is sold in, in India.

{listing}

Return ONLY a JSON object mapping each product id to an array of 1-3 color names, e.g.
{{"CRM-301202": ["Shiny Steel", "Ebony Sheen"]}}"""
    result = await llm.generate_json(prompt, use_search=True)
    if isinstance(result, dict):
        for it in gaps:
            colors = result.get(it["id"])
            if isinstance(colors, list) and colors:
                it["attributes"]["color_options"] = [str(c) for c in colors[:3]]
                filled_via_llm.add(it["id"])

    # deterministic fallback for anything the LLM didn't cover
    for it in gaps:
        if it["id"] not in filled_via_llm:
            cat = it["attributes"].get("category", "")
            it["attributes"]["color_options"] = FALLBACK_COLORS.get(cat, ["Black"])

    for it in gaps:
        it["attributes"].pop("color", None)
        it["enhanced_fields"] = ["color_options"]
    return [it["id"] for it in gaps]


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
