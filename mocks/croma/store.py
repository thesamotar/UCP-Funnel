"""Shared state, catalog data, and helpers for the mock Croma service.

The search / cart / order / payment routers all import from here so they
operate on the same in-memory carts and orders.
"""
import json
from pathlib import Path

DATA = json.loads((Path(__file__).parent / "data.json").read_text())["products"]

# in-memory commerce state, shared across the routers
CARTS: dict[str, dict] = {}
ORDERS: dict[str, dict] = {}


def cart_view(cart: dict) -> dict:
    total = sum(e["unitPrice"] * e["quantity"] for e in cart["entries"])
    return {**cart, "totalItems": sum(e["quantity"] for e in cart["entries"]),
            "totalPrice": {"value": total, "currencyIso": "INR"}}
