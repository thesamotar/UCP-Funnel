"""POST /api/chat — the LLM proxy behind the chat frontend.

One server-side key (ANTHROPIC_API_KEY / GEMINI_API_KEY) powers chat for every
signed-in user, so the browser never sees a key. The frontend sends its
neutral conversation history; the node adds the system prompt and UCP tool
declarations (they live here, not in the browser), makes one model call, and
returns {text, toolCalls}. Tool *execution* stays in the browser — the tools
hit this same node's UCP endpoints with the user's own JWT, which is what
keeps carts and orders per-user.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import llm
from ..auth import current_user

router = APIRouter()

TOOL_DEFS = [
    {
        "name": "search_tata_catalog",
        "description": "Search products across Tata retail brands (BigBasket, Croma, Zudio, Tata CLiQ, Tata 1mg, Titan). "
                       "The Tata node routes the query to the right retailer automatically. "
                       "Use for any shopping/product query.",
        "properties": {
            "query": {"type": "string",
                      "description": "Natural-language product query, keep the user's constraints in it, "
                                     "e.g. 'refrigerator 200L+ capacity under 30000' or 'Zudio black t-shirt M'"},
            "max_price": {"type": "number", "description": "Maximum price in INR, if the user stated one"},
            "min_price": {"type": "number", "description": "Minimum price in INR, if stated"},
        },
        "required": ["query"],
    },
    {
        "name": "add_to_cart",
        "description": "Add a product to the Tata Neu cart. item_id must come from a previous "
                       "search_tata_catalog result.",
        "properties": {
            "item_id": {"type": "string", "description": "Product id from search results, e.g. 'CRM-301201'"},
            "quantity": {"type": "number", "description": "Quantity, default 1"},
        },
        "required": ["item_id"],
    },
    {
        "name": "view_cart",
        "description": "View the current Tata Neu cart contents and total.",
        "properties": {},
        "required": [],
    },
    {
        "name": "initiate_payment",
        "description": "Call when the user indicates their order is complete and they are ready to pay "
                       "(e.g. 'that's all', 'I'm done, let me pay', 'place the order'). Generates a UPI "
                       "payment QR code for the current cart total; the order is placed automatically "
                       "once the payment succeeds. Ask the user to confirm before calling this.",
        "properties": {},
        "required": [],
    },
]

SYSTEM_CONNECTED = """You are a highly intelligent, proactive planner and shopping assistant with the Tata Neu connector enabled. You can shop across
Tata brands (BigBasket, Croma, Zudio, Tata CLiQ, Tata 1mg, Titan, IHCL, Air India) via tools. 

When a user mentions a high-level goal, like a trip (e.g. to Goa) or a party, do NOT just wait for them to ask for specific items. Instead:
1. Break down their goal into logical needs (e.g. for travel: flights -> hotels -> apparel -> essentials/sunscreen. For a party: snacks -> drinks -> decor).
2. Sequentially ask them about each need and offer to search for it using your tools.
3. Proactively call the `search_tata_catalog` tool to present curated options for that specific step. Wait for their choice, add it to their cart, and then move to the next logical step in the plan.
4. Keep the conversation engaging and highly intelligent, guiding the user to seamlessly plan everything A-Z.

For any product/shopping request, call `search_tata_catalog`. Present results conversationally and concisely — the UI already renders product
cards, so summarize/recommend rather than listing every spec. Always use ₹ for prices. Refer to
products by their id (e.g. CRM-301201 or ZUD-001) when adding to cart.

IMPORTANT: When you call search_tata_catalog, the result may include a `filter_reasoning` field if the backend had to filter the list (e.g., if it couldn't find an exact match and provided close matches, or if it found exact matches). You MUST read this reasoning and relay it positively to the user (e.g., "I couldn't find an exact match for a 32-inch TV, but here are some great 43-inch options!"). If no items were returned, tell the user politely that nothing was found.

When the user says their order is complete
and they want to pay, confirm the cart total, then call initiate_payment — a UPI QR appears in the chat;
tell the user to scan it with any UPI app (or open the payment link) and that the order will be placed
automatically once the payment goes through. Do not claim the order is placed until you are told the
payment succeeded."""


class ChatBody(BaseModel):
    history: list[dict]
    connector: bool = False


@router.post("/api/chat")
async def chat(body: ChatBody, user_id: str = Depends(current_user)):
    if not body.history:
        raise HTTPException(status_code=422, detail="history is empty")
    try:
        return await llm.chat(
            body.history,
            system=SYSTEM_CONNECTED if body.connector else None,
            tools=TOOL_DEFS if body.connector else None,
        )
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
