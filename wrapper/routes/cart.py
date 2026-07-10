"""UCP cart: add an item (POST /ucp/v1/cart/items) and view it (GET /ucp/v1/cart).

Carts are per authenticated user and persist in Supabase. Adding lazily opens
a native cart at the item's own retailer and adds the item there; the UCP cart
mirrors it, so one UCP cart can hold open carts at several retailers at once.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..adapters import REGISTRY, RetailerError
from ..auth import current_user
from ..state import cart_view, get_cart, resolve_item, save_cart

router = APIRouter()


class CartItemBody(BaseModel):
    item_id: str
    quantity: int = 1


@router.post("/ucp/v1/cart/items")
async def add_to_cart(body: CartItemBody, user_id: str = Depends(current_user)):
    item = await resolve_item(body.item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"unknown item_id {body.item_id!r} — search for it first")
    retailer = item["source"]["retailer"]
    adapter = REGISTRY.get(retailer)
    if not adapter:
        raise HTTPException(status_code=502, detail=f"retailer {retailer!r} is no longer attached to the node")
    if not adapter.supports_commerce:
        raise HTTPException(status_code=501, detail=f"{retailer} is search-only — it has no cart/checkout")
    cart = await get_cart(user_id)
    try:
        # lazily open a native cart at the retailer, then add natively
        if retailer not in cart["native_carts"]:
            cart["native_carts"][retailer] = await adapter.cart_create()
            print(f"[cart] opened native {retailer} cart {cart['native_carts'][retailer]} for {user_id[:8]}")
        await adapter.cart_add(cart["native_carts"][retailer], item["source"]["native_id"], body.quantity)
    except RetailerError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    # mirror into the UCP-level cart
    for line in cart["items"]:
        if line["item"]["id"] == body.item_id:
            line["quantity"] += body.quantity
            break
    else:
        cart["items"].append({"item": item, "quantity": body.quantity})
    await save_cart(user_id, cart)
    return cart_view(cart)


@router.get("/ucp/v1/cart")
async def view_cart(user_id: str = Depends(current_user)):
    return cart_view(await get_cart(user_id))
