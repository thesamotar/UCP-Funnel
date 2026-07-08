"""Shared state, catalog data, and helpers for the mock BigBasket service.

The search / cart / order / payment routers all import from here so they
operate on the same in-memory carts and orders.
"""
import json
from pathlib import Path

DATA = json.loads((Path(__file__).parent / "data.json").read_text())["products"]

# in-memory commerce state, shared across the routers
CARTS: dict[str, dict] = {}
ORDERS: dict[str, dict] = {}


def cart_summary(cart: dict) -> dict:
    total = sum(line["unit_sp"] * line["qty"] for line in cart["items"])
    return {**cart, "item_count": sum(line["qty"] for line in cart["items"]), "cart_value": total}
