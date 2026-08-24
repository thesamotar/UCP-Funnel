"""BigBasket cart operations: create, add, get (RPC style: POST verbs)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from .store import CARTS, DATA, cart_summary, persist_cart

router = APIRouter()


class CartAddRequest(BaseModel):
    cart_id: str
    sku_id: str
    qty: int = 1


class CartGetRequest(BaseModel):
    cart_id: str


@router.post("/bb/api/v1/cart.create")
async def cart_create():
    cart_id = f"BBCART-{uuid.uuid4().hex[:8].upper()}"
    CARTS[cart_id] = {"cart_id": cart_id, "items": []}
    await persist_cart(CARTS[cart_id])
    return {"status": "success", "cart_id": cart_id}


@router.post("/bb/api/v1/cart.add")
async def cart_add(req: CartAddRequest):
    cart = CARTS.get(req.cart_id)
    if not cart:
        return {"status": "error", "message": "cart not found"}
    product = next((p for p in DATA if p["sku_id"] == req.sku_id), None)
    if not product:
        return {"status": "error", "message": "SKU not found"}
    if product["availability"] != "A":
        return {"status": "error", "message": "SKU out of stock"}
    for line in cart["items"]:
        if line["sku_id"] == req.sku_id:
            line["qty"] += req.qty
            break
    else:
        cart["items"].append({
            "sku_id": req.sku_id, "desc": product["desc"],
            "unit_sp": product["sp"], "qty": req.qty,
        })
    await persist_cart(cart)
    return {"status": "success", "cart": cart_summary(cart)}


@router.post("/bb/api/v1/cart.get")
def cart_get(req: CartGetRequest):
    cart = CARTS.get(req.cart_id)
    if not cart:
        return {"status": "error", "message": "cart not found"}
    return {"status": "success", "cart": cart_summary(cart)}


@router.delete("/bigbasket/api/v2/cart/{cart_id}/entries/{product_code}")
async def remove_entry_v2(cart_id: str, product_code: str):
    cart = CARTS.get(cart_id)
    if not cart:
        return {"cart": None, "status": 404, "message": "cart not found"}
    
    # filter out productCode and sku_id to be safe across different mock schemas
    cart_items_key = "entries" if "entries" in cart else "items"
    cart[cart_items_key] = [
        e for e in cart[cart_items_key] 
        if e.get("productCode") != product_code and e.get("sku_id") != product_code
    ]
    
    await persist_cart(cart)
    # Different mocks use different view functions (cart_summary or cart_view)
    if "cart_view" in globals():
        view = globals()["cart_view"](cart)
    elif "cart_summary" in globals():
        view = globals()["cart_summary"](cart)
    else:
        view = cart
    return {"cart": view, "status": 200}
