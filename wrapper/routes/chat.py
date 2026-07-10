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
        "name": "checkout",
        "description": "Place the order for everything in the Tata Neu cart. "
                       "Ask the user to confirm before calling this.",
        "properties": {},
        "required": [],
    },
]

SYSTEM_CONNECTED = """You are a helpful assistant with the Tata Neu connector enabled. You can shop across
Tata brands (BigBasket for groceries, Croma for electronics) via tools. For any product/shopping request, call
search_tata_catalog. Present results conversationally and concisely — the UI already renders product
cards, so summarize/recommend rather than listing every spec. Always use ₹ for prices. Refer to
products by their id (e.g. CRM-301201) when adding to cart. Confirm with the user before checkout."""


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
