"""Shared state, catalog data, and helpers for the mock BigBasket service.

BigBasket's "own database" is its trio of Supabase tables (bigbasket_products /
_carts / _orders). The catalog and any open carts/orders are loaded once at
startup into module-level structures the routers share; every cart/order
mutation is written through to Supabase so native state survives free-tier
cold starts.
"""
from datetime import datetime, timezone

from wrapper.db import db

DATA: list[dict] = []
CARTS: dict[str, dict] = {}
ORDERS: dict[str, dict] = {}


async def load() -> None:
    """Fill catalog + state from Supabase; called from the app lifespan."""
    client = await db()
    DATA.clear()
    for row in (await client.table("bigbasket_products").select("native,image_url").execute()).data:
        native = row["native"]
        if row.get("image_url"):
            native["img"] = row["image_url"]
        DATA.append(native)
    if not DATA:
        raise RuntimeError("bigbasket_products is empty — run `python -m db.seed`")
    CARTS.clear()
    for row in (await client.table("bigbasket_carts").select("id,payload").execute()).data:
        CARTS[row["id"]] = row["payload"]
    ORDERS.clear()
    for row in (await client.table("bigbasket_orders").select("id,payload").execute()).data:
        ORDERS[row["id"]] = row["payload"]
    print(f"[bigbasket] loaded {len(DATA)} products, {len(CARTS)} open carts, "
          f"{len(ORDERS)} orders from Supabase")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def persist_cart(cart: dict) -> None:
    await (await db()).table("bigbasket_carts").upsert(
        {"id": cart["cart_id"], "payload": cart, "updated_at": _now()}).execute()


async def drop_cart(cart_id: str) -> None:
    await (await db()).table("bigbasket_carts").delete().eq("id", cart_id).execute()


async def persist_order(order: dict) -> None:
    await (await db()).table("bigbasket_orders").upsert(
        {"id": order["order_id"], "payload": order, "updated_at": _now()}).execute()


def cart_summary(cart: dict) -> dict:
    total = sum(line["unit_sp"] * line["qty"] for line in cart["items"])
    return {**cart, "item_count": sum(line["qty"] for line in cart["items"]), "cart_value": total}
