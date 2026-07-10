"""BigBasket order operations: place an order from a cart, look one up."""
import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from .store import CARTS, ORDERS, cart_summary, drop_cart, persist_order

router = APIRouter()


class OrderPlaceRequest(BaseModel):
    cart_id: str
    delivery_address: str = "Registered TataNeu address"
    slot: str = "next available"


@router.post("/bb/api/v1/order.place")
async def order_place(req: OrderPlaceRequest):
    cart = CARTS.get(req.cart_id)
    if not cart:
        return {"status": "error", "message": "cart not found"}
    if not cart["items"]:
        return {"status": "error", "message": "cart is empty"}
    order_id = f"BBORD-{uuid.uuid4().hex[:8].upper()}"
    summary = cart_summary(cart)
    ORDERS[order_id] = {
        "order_id": order_id,
        "items": cart["items"],
        "amount": summary["cart_value"],
        "delivery_address": req.delivery_address,
        "slot": req.slot,
        "order_status": "PLACED",
        "payment_status": "PENDING",
    }
    CARTS.pop(req.cart_id)
    await persist_order(ORDERS[order_id])
    await drop_cart(req.cart_id)
    return {"status": "success", "order": ORDERS[order_id]}


@router.get("/bb/api/v1/order/{order_id}")
def order_get(order_id: str):
    order = ORDERS.get(order_id)
    if not order:
        return {"status": "error", "message": "order not found"}
    return {"status": "success", "order": order}
