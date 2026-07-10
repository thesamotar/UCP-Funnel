"""Per-user UCP state, persisted in Supabase.

Carts and orders are keyed by the authenticated user's id (user_carts /
user_orders tables). The catalog cache — every item any search has returned,
so cart ops can resolve ids without re-querying retailers — is global and
survives restarts (catalog_cache table).
"""
from datetime import datetime, timezone

from .db import db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- per-user cart -----------------------------------------------------------

async def get_cart(user_id: str) -> dict:
    resp = await (await db()).table("user_carts") \
        .select("items,native_carts").eq("user_id", user_id).limit(1).execute()
    if resp.data:
        return {"items": resp.data[0]["items"], "native_carts": resp.data[0]["native_carts"]}
    return {"items": [], "native_carts": {}}


async def save_cart(user_id: str, cart: dict) -> None:
    await (await db()).table("user_carts").upsert({
        "user_id": user_id, "items": cart["items"],
        "native_carts": cart["native_carts"], "updated_at": _now(),
    }).execute()


def cart_view(cart: dict) -> dict:
    total = sum(line["item"]["price"]["amount"] * line["quantity"] for line in cart["items"])
    return {
        "ucp_version": "0.1",
        "type": "cart",
        "items": cart["items"],
        "native_carts": cart["native_carts"],
        "total": {"amount": total, "currency": "INR"},
    }


# --- global catalog cache ------------------------------------------------------

async def cache_items(items: list[dict]) -> None:
    rows = [{"item_id": it["id"], "item": it, "updated_at": _now()} for it in items]
    if rows:
        await (await db()).table("catalog_cache").upsert(rows).execute()


async def resolve_item(item_id: str) -> dict | None:
    resp = await (await db()).table("catalog_cache") \
        .select("item").eq("item_id", item_id).limit(1).execute()
    return resp.data[0]["item"] if resp.data else None


# --- per-user orders -----------------------------------------------------------

async def add_order(user_id: str, order: dict) -> None:
    await (await db()).table("user_orders").insert({
        "id": order["order_id"], "user_id": user_id, "payload": order,
    }).execute()


async def list_orders(user_id: str) -> list[dict]:
    resp = await (await db()).table("user_orders") \
        .select("payload").eq("user_id", user_id).order("created_at", desc=True).execute()
    return [row["payload"] for row in resp.data or []]
