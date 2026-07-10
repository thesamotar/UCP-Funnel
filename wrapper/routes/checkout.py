"""POST /ucp/v1/checkout — place one native order + payment per retailer that
has items in the caller's cart, then return a single consolidated confirmation.
GET /ucp/v1/orders — the caller's past confirmations, newest first."""
import uuid

from fastapi import APIRouter, Depends, HTTPException

from ..adapters import REGISTRY, RetailerError
from ..auth import current_user
from ..state import add_order, cart_view, get_cart, list_orders, save_cart

router = APIRouter()


@router.post("/ucp/v1/checkout")
async def checkout(user_id: str = Depends(current_user)):
    cart = await get_cart(user_id)
    if not cart["items"]:
        raise HTTPException(status_code=400, detail="cart is empty")
    view = cart_view(cart)
    # place one native order + payment per retailer that has items
    retailer_orders = []
    for retailer, native_cart_id in cart["native_carts"].items():
        adapter = REGISTRY.get(retailer)
        if not adapter:
            raise HTTPException(status_code=502, detail=f"retailer {retailer!r} is no longer attached to the node")
        try:
            placed = await adapter.place_order(native_cart_id)
            payment = await adapter.pay(placed["order_id"])
        except RetailerError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        print(f"[checkout] {retailer} order {placed['order_id']} paid via {payment['payment_id']}")
        retailer_orders.append({"retailer": retailer, **placed, "payment": payment})
    order = {
        "ucp_version": "0.1",
        "type": "order_confirmation",
        "order_id": f"TATA-{uuid.uuid4().hex[:8].upper()}",
        "retailer_orders": retailer_orders,
        "items": view["items"],
        "total": view["total"],
        "neu_coins_earned": int(view["total"]["amount"] * 0.05),
        "estimated_delivery": "2-4 days",
    }
    await add_order(user_id, order)
    await save_cart(user_id, {"items": [], "native_carts": {}})
    return order


@router.get("/ucp/v1/orders")
async def past_orders(user_id: str = Depends(current_user)):
    return {"ucp_version": "0.1", "type": "order_list", "orders": await list_orders(user_id)}
