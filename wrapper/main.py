"""Tata Neu UCP node — the wrapper API between LLM shopping agents and
Tata retailer backends. Exposes UCP-shaped search / cart / checkout and
serves the demo frontend at /.

Run: uvicorn wrapper.main:app --port 8000
"""
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import llm
from .pipeline import run_search_pipeline

app = FastAPI(title="Tata Neu UCP Node")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# demo-grade in-memory state: one cart, plus an index of every item any
# search has returned so cart ops can resolve ids without re-querying retailers
CART: dict = {"items": []}
CATALOG_CACHE: dict[str, dict] = {}
ORDERS: list[dict] = []


class SearchBody(BaseModel):
    query: str
    constraints: dict = {}


class CartItemBody(BaseModel):
    item_id: str
    quantity: int = 1


@app.get("/api/config")
def config():
    # localhost demo convenience: hand the browser the same keys the wrapper uses
    return {
        "gemini_key": os.environ.get("GEMINI_API_KEY", ""),
        "anthropic_key": os.environ.get("ANTHROPIC_API_KEY", ""),
        "gemini_model": llm.GEMINI_MODEL,
        "anthropic_model": llm.ANTHROPIC_MODEL,
    }


@app.post("/ucp/v1/search")
async def ucp_search(body: SearchBody):
    try:
        result = await run_search_pipeline(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    for item in result["items"]:
        CATALOG_CACHE[item["id"]] = item
    return result


@app.post("/ucp/v1/cart/items")
def add_to_cart(body: CartItemBody):
    item = CATALOG_CACHE.get(body.item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"unknown item_id {body.item_id!r} — search for it first")
    for line in CART["items"]:
        if line["item"]["id"] == body.item_id:
            line["quantity"] += body.quantity
            break
    else:
        CART["items"].append({"item": item, "quantity": body.quantity})
    return get_cart()


@app.get("/ucp/v1/cart")
def get_cart():
    total = sum(l["item"]["price"]["amount"] * l["quantity"] for l in CART["items"])
    return {
        "ucp_version": "0.1",
        "type": "cart",
        "items": CART["items"],
        "total": {"amount": total, "currency": "INR"},
    }


@app.post("/ucp/v1/checkout")
def checkout():
    if not CART["items"]:
        raise HTTPException(status_code=400, detail="cart is empty")
    cart = get_cart()
    order = {
        "ucp_version": "0.1",
        "type": "order_confirmation",
        "order_id": f"TATA-{uuid.uuid4().hex[:8].upper()}",
        "items": cart["items"],
        "total": cart["total"],
        "payment": {"method": "TataNeu HDFC Card (mock)", "status": "authorized"},
        "neu_coins_earned": int(cart["total"]["amount"] * 0.05),
        "estimated_delivery": "2-4 days",
    }
    ORDERS.append(order)
    CART["items"] = []
    return order


# serve the demo frontend at / (mounted last so API routes win)
app.mount("/", StaticFiles(directory=Path(__file__).parent.parent / "frontend", html=True), name="frontend")
