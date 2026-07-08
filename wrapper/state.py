"""Shared in-memory state and helpers for the UCP node's route modules.

Demo-grade: one UCP cart mirroring one native cart per retailer, an index of
every item any search has returned (so cart ops can resolve ids without
re-querying retailers), and a list of placed orders. The route modules import
these objects by reference and only ever mutate their contents, so they all
see the same state.
"""

CART: dict = {"items": [], "native_carts": {}}  # native_carts: retailer -> native cart id
CATALOG_CACHE: dict[str, dict] = {}
ORDERS: list[dict] = []


def cart_view() -> dict:
    total = sum(line["item"]["price"]["amount"] * line["quantity"] for line in CART["items"])
    return {
        "ucp_version": "0.1",
        "type": "cart",
        "items": CART["items"],
        "native_carts": CART["native_carts"],
        "total": {"amount": total, "currency": "INR"},
    }
