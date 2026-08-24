"""Per-user UCP state, persisted in Supabase.

Carts and orders are keyed by the authenticated user's id (user_carts /
user_orders tables). The catalog cache — every item any search has returned,
so cart ops can resolve ids without re-querying retailers — is global and
survives restarts (catalog_cache table).
"""
from __future__ import annotations

from datetime import datetime, timezone

from .db import db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- per-user cart -----------------------------------------------------------

async def get_cart(user_id: str, cart_id: str = None) -> dict:
    if cart_id:
        resp = await (await db()).table("user_carts") \
            .select("id,name,is_active,is_completed,items,native_carts").eq("id", cart_id).eq("user_id", user_id).limit(1).execute()
    else:
        resp = await (await db()).table("user_carts") \
            .select("id,name,is_active,is_completed,items,native_carts").eq("user_id", user_id).eq("is_active", True).limit(1).execute()
    
    if resp.data:
        return resp.data[0]
        
    # If no active cart, create a default Main Cart
    new_cart = {
        "user_id": user_id,
        "name": "Main Cart",
        "is_active": True,
        "is_completed": False,
        "items": [],
        "native_carts": {}
    }
    resp = await (await db()).table("user_carts").insert(new_cart).execute()
    return resp.data[0]

async def list_carts(user_id: str, include_completed: bool = False) -> list[dict]:
    query = (await db()).table("user_carts").select("id,name,is_active,is_completed,items,native_carts").eq("user_id", user_id)
    if not include_completed:
        query = query.eq("is_completed", False)
    resp = await query.order("updated_at", desc=True).execute()
    return resp.data or []

async def create_cart(user_id: str, name: str) -> dict:
    # Set others inactive
    await (await db()).table("user_carts").update({"is_active": False}).eq("user_id", user_id).execute()
    new_cart = {
        "user_id": user_id,
        "name": name,
        "is_active": True,
        "is_completed": False,
        "items": [],
        "native_carts": {}
    }
    resp = await (await db()).table("user_carts").insert(new_cart).execute()
    return resp.data[0]

async def set_active_cart(user_id: str, cart_id: str) -> dict:
    await (await db()).table("user_carts").update({"is_active": False}).eq("user_id", user_id).execute()
    resp = await (await db()).table("user_carts").update({"is_active": True}).eq("id", cart_id).eq("user_id", user_id).execute()
    return resp.data[0] if resp.data else None

async def delete_cart(user_id: str, cart_id: str) -> None:
    await (await db()).table("user_carts").delete().eq("id", cart_id).eq("user_id", user_id).execute()


async def save_cart(user_id: str, cart: dict) -> None:
    await (await db()).table("user_carts").update({
        "items": cart["items"],
        "native_carts": cart["native_carts"], 
        "is_active": cart.get("is_active", True),
        "is_completed": cart.get("is_completed", False),
        "updated_at": _now(),
    }).eq("id", cart["id"]).eq("user_id", user_id).execute()


def cart_view(cart: dict) -> dict:
    total = sum(line["item"]["price"]["amount"] * line["quantity"] for line in cart.get("items", []))
    return {
        "ucp_version": "0.1",
        "type": "cart",
        "id": cart.get("id"),
        "name": cart.get("name"),
        "is_active": cart.get("is_active"),
        "is_completed": cart.get("is_completed"),
        "items": cart.get("items", []),
        "native_carts": cart.get("native_carts", {}),
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
