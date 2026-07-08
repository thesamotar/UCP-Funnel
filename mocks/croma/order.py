"""Croma order operations: place an order from a cart, look one up."""
import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from .store import CARTS, ORDERS, cart_view

router = APIRouter()


class OrderRequest(BaseModel):
    cartId: str
    deliveryAddress: str = "Registered TataNeu address"


@router.post("/croma/api/v2/orders")
def place_order(req: OrderRequest):
    cart = CARTS.get(req.cartId)
    if not cart:
        return {"order": None, "status": 404, "message": "cart not found"}
    if not cart["entries"]:
        return {"order": None, "status": 400, "message": "cart is empty"}
    order_id = f"CRMORD-{uuid.uuid4().hex[:8].upper()}"
    view = cart_view(cart)
    ORDERS[order_id] = {
        "orderId": order_id,
        "entries": cart["entries"],
        "totalPrice": view["totalPrice"],
        "deliveryAddress": req.deliveryAddress,
        "orderStatus": "PAYMENT_PENDING",
    }
    CARTS.pop(req.cartId)
    return {"order": ORDERS[order_id], "status": 201}


@router.get("/croma/api/v2/orders/{order_id}")
def get_order(order_id: str):
    order = ORDERS.get(order_id)
    if not order:
        return {"order": None, "status": 404, "message": "not found"}
    return {"order": order, "status": 200}
