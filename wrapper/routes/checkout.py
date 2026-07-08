"""POST /ucp/v1/checkout — place one native order + payment per retailer that
has items, then return a single consolidated confirmation."""
import uuid

from fastapi import APIRouter, HTTPException

from ..adapters import ADAPTERS, RetailerError
from ..state import CART, ORDERS, cart_view

router = APIRouter()


@router.post("/ucp/v1/checkout")
async def checkout():
    if not CART["items"]:
        raise HTTPException(status_code=400, detail="cart is empty")
    cart = cart_view()
    # place one native order + payment per retailer that has items
    retailer_orders = []
    for retailer, native_cart_id in CART["native_carts"].items():
        adapter = ADAPTERS[retailer]
        try:
            placed = await adapter["place_order"](native_cart_id)
            payment = await adapter["pay"](placed["order_id"])
        except RetailerError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        print(f"[checkout] {retailer} order {placed['order_id']} paid via {payment['payment_id']}")
        retailer_orders.append({"retailer": retailer, **placed, "payment": payment})
    order = {
        "ucp_version": "0.1",
        "type": "order_confirmation",
        "order_id": f"TATA-{uuid.uuid4().hex[:8].upper()}",
        "retailer_orders": retailer_orders,
        "items": cart["items"],
        "total": cart["total"],
        "neu_coins_earned": int(cart["total"]["amount"] * 0.05),
        "estimated_delivery": "2-4 days",
    }
    ORDERS.append(order)
    CART["items"] = []
    CART["native_carts"] = {}
    return order
