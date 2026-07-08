"""Croma cart operations: create, add entry, get (REST style)."""
import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from .store import CARTS, DATA, cart_view

router = APIRouter()


class CartEntryRequest(BaseModel):
    productCode: str
    quantity: int = 1


@router.post("/croma/api/v2/cart")
def create_cart():
    cart_id = f"CRMCART-{uuid.uuid4().hex[:8].upper()}"
    CARTS[cart_id] = {"cartId": cart_id, "entries": []}
    return {"cart": cart_view(CARTS[cart_id]), "status": 201}


@router.post("/croma/api/v2/cart/{cart_id}/entries")
def add_entry(cart_id: str, req: CartEntryRequest):
    cart = CARTS.get(cart_id)
    if not cart:
        return {"cart": None, "status": 404, "message": "cart not found"}
    product = next((p for p in DATA if p["code"] == req.productCode), None)
    if not product:
        return {"cart": None, "status": 404, "message": "product not found"}
    if not product.get("inStock"):
        return {"cart": None, "status": 409, "message": "product out of stock"}
    for entry in cart["entries"]:
        if entry["productCode"] == req.productCode:
            entry["quantity"] += req.quantity
            break
    else:
        cart["entries"].append({
            "productCode": req.productCode, "name": product["name"],
            "unitPrice": product["price"]["sellingPrice"], "quantity": req.quantity,
        })
    return {"cart": cart_view(cart), "status": 200}


@router.get("/croma/api/v2/cart/{cart_id}")
def get_cart(cart_id: str):
    cart = CARTS.get(cart_id)
    if not cart:
        return {"cart": None, "status": 404, "message": "cart not found"}
    return {"cart": cart_view(cart), "status": 200}
