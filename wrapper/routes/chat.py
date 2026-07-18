"""POST /api/chat — the LLM proxy behind the chat frontend.

One server-side key (ANTHROPIC_API_KEY / GEMINI_API_KEY) powers chat for every
signed-in user, so the browser never sees a key. The frontend sends its
neutral conversation history; the node adds the system prompt and UCP tool
declarations (they live here, not in the browser), makes one model call, and
returns {text, toolCalls}. Tool *execution* stays in the browser — the tools
hit this same node's UCP endpoints with the user's own JWT, which is what
keeps carts and orders per-user.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import llm
from ..auth import current_user

router = APIRouter()

TOOL_DEFS = [
    {
        "name": "search_tata_catalog",
        "description": "Search products across Tata retail brands (BigBasket groceries, Croma electronics). "
                       "The Tata node routes the query to the right retailer automatically. "
                       "Use for any shopping/product query.",
        "properties": {
            "query": {"type": "string",
                      "description": "Natural-language product query, keep the user's constraints in it, "
                                     "e.g. 'refrigerator 200L+ capacity under 30000'"},
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

SYSTEM_CONNECTED = """You are a helpful assistant with the Tata Neu connector enabled. You can shop across
Tata brands (BigBasket for groceries, Croma for electronics) via tools. For any product/shopping request, call
search_tata_catalog. Present results conversationally and concisely — the UI already renders product
cards, so summarize/recommend rather than listing every spec. Always use ₹ for prices. Refer to
products by their id (e.g. CRM-301201) when adding to cart. When the user says their order is complete
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
