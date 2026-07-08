"""UCP cart: add an item (POST /ucp/v1/cart/items) and view it (GET /ucp/v1/cart).

Adding lazily opens a native cart at the item's own retailer and adds the item
there; the UCP cart mirrors it, so one UCP cart can hold open carts at several
retailers at once.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..adapters import ADAPTERS, RetailerError
from ..state import CART, CATALOG_CACHE, cart_view

router = APIRouter()


class CartItemBody(BaseModel):
    item_id: str
    quantity: int = 1


@router.post("/ucp/v1/cart/items")
async def add_to_cart(body: CartItemBody):
    item = CATALOG_CACHE.get(body.item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"unknown item_id {body.item_id!r} — search for it first")
    retailer = item["source"]["retailer"]
    adapter = ADAPTERS[retailer]
    try:
        # lazily open a native cart at the retailer, then add natively
        if retailer not in CART["native_carts"]:
            CART["native_carts"][retailer] = await adapter["cart_create"]()
            print(f"[cart] opened native {retailer} cart {CART['native_carts'][retailer]}")
        await adapter["cart_add"](CART["native_carts"][retailer], item["source"]["native_id"], body.quantity)
    except RetailerError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    # mirror into the UCP-level cart
    for line in CART["items"]:
        if line["item"]["id"] == body.item_id:
            line["quantity"] += body.quantity
            break
    else:
        CART["items"].append({"item": item, "quantity": body.quantity})
    return cart_view()


@router.get("/ucp/v1/cart")
def get_cart():
    return cart_view()
