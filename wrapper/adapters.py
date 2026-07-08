"""Retailer adapters: translate a routed UCP search intent into each
retailer's native API call, and normalize native responses into UCP items.

Adding a Tata retailer to the node = adding one adapter entry here.
"""
import os

import httpx

BIGBASKET_URL = os.environ.get("BIGBASKET_URL", "http://127.0.0.1:9001")
CROMA_URL = os.environ.get("CROMA_URL", "http://127.0.0.1:9002")


async def bigbasket_search(intent: dict) -> tuple[dict, list[dict]]:
    """POST to BigBasket's search, return (native_request_sent, ucp_items)."""
    native_req = {
        "search_term": intent["search_term"],
        "filters": {
            "price_max": intent.get("max_price"),
            "price_min": intent.get("min_price"),
            "brand": intent.get("brand"),
            "category": intent.get("category"),
        },
        "page_size": 8,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{BIGBASKET_URL}/bb/api/v1/product.search", json=native_req)
        resp.raise_for_status()
        data = resp.json()
    items = []
    for p in data.get("products", []):
        items.append({
            "id": p["sku_id"],
            "title": p["desc"],
            "brand": p["brand"],
            "price": {"amount": p["sp"], "mrp": p["mrp"], "currency": "INR"},
            "attributes": {"pack_size": p["pack_size"], "category": p["cat"]},
            "availability": "in_stock" if p["availability"] == "A" else "out_of_stock",
            "image": p["img"],
            "source": {"retailer": "bigbasket", "native_id": p["sku_id"]},
        })
    return native_req, items


async def croma_search(intent: dict) -> tuple[dict, list[dict]]:
    """GET Croma's search, return (native_request_sent, ucp_items)."""
    params = {"text": intent["search_term"], "pageSize": 8}
    if intent.get("max_price") is not None:
        params["maxPrice"] = intent["max_price"]
    if intent.get("min_price") is not None:
        params["minPrice"] = intent["min_price"]
    if intent.get("category"):
        params["category"] = intent["category"]
    if intent.get("min_capacity_litres") is not None:
        params["minCapacityLitres"] = intent["min_capacity_litres"]
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{CROMA_URL}/croma/api/v2/products/search", params=params)
        resp.raise_for_status()
        data = resp.json()
    items = []
    for p in data.get("searchResult", {}).get("products", []):
        specs = {k: v for k, v in (p.get("specs") or {}).items()}
        items.append({
            "id": p["code"],
            "title": p["name"],
            "brand": p["brandName"],
            "price": {"amount": p["price"]["sellingPrice"], "mrp": p["price"]["mrp"], "currency": "INR"},
            "attributes": {"category": p["category"], **specs},
            "availability": "in_stock" if p.get("inStock") else "out_of_stock",
            "image": p["imageUrl"],
            "source": {"retailer": "croma", "native_id": p["code"]},
        })
    return params, items


# --- cart / order / payment adapters ----------------------------------------
# Each retailer exposes a different native flow; these normalize it to:
#   cart_create() -> native cart id
#   cart_add(cart_id, native_id, qty) -> native cart snapshot
#   place_order(cart_id) -> {"order_id", "amount"}
#   pay(order_id) -> {"payment_id", "status", "method"}

class RetailerError(Exception):
    pass


def _bb_ok(data: dict) -> dict:
    if data.get("status") != "success":
        raise RetailerError(f"bigbasket: {data.get('message', 'unknown error')}")
    return data


def _croma_ok(data: dict) -> dict:
    if data.get("status") not in (200, 201):
        raise RetailerError(f"croma: {data.get('message', 'unknown error')}")
    return data


async def bigbasket_cart_create() -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{BIGBASKET_URL}/bb/api/v1/cart.create")
        return _bb_ok(resp.json())["cart_id"]


async def bigbasket_cart_add(cart_id: str, native_id: str, qty: int) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{BIGBASKET_URL}/bb/api/v1/cart.add",
                                 json={"cart_id": cart_id, "sku_id": native_id, "qty": qty})
        return _bb_ok(resp.json())["cart"]


async def bigbasket_place_order(cart_id: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{BIGBASKET_URL}/bb/api/v1/order.place", json={"cart_id": cart_id})
        order = _bb_ok(resp.json())["order"]
        return {"order_id": order["order_id"], "amount": order["amount"]}


async def bigbasket_pay(order_id: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{BIGBASKET_URL}/bb/api/v1/payment.process",
                                 json={"order_id": order_id, "method": "tataneu_upi"})
        payment = _bb_ok(resp.json())["payment"]
        return {"payment_id": payment["txn_id"], "status": payment["payment_status"],
                "method": payment["method"]}


async def croma_cart_create() -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{CROMA_URL}/croma/api/v2/cart")
        return _croma_ok(resp.json())["cart"]["cartId"]


async def croma_cart_add(cart_id: str, native_id: str, qty: int) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{CROMA_URL}/croma/api/v2/cart/{cart_id}/entries",
                                 json={"productCode": native_id, "quantity": qty})
        return _croma_ok(resp.json())["cart"]


async def croma_place_order(cart_id: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{CROMA_URL}/croma/api/v2/orders", json={"cartId": cart_id})
        order = _croma_ok(resp.json())["order"]
        return {"order_id": order["orderId"], "amount": order["totalPrice"]["value"]}


async def croma_pay(order_id: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{CROMA_URL}/croma/api/v2/payments",
                                 json={"orderId": order_id, "paymentMode": "TATANEU_CARD"})
        payment = _croma_ok(resp.json())["payment"]
        return {"payment_id": payment["paymentId"], "status": payment["transactionStatus"],
                "method": payment["paymentMode"]}


ADAPTERS = {
    "bigbasket": {
        "search": bigbasket_search,
        "cart_create": bigbasket_cart_create,
        "cart_add": bigbasket_cart_add,
        "place_order": bigbasket_place_order,
        "pay": bigbasket_pay,
        "description": "BigBasket — groceries, fresh produce, dairy, staples, snacks, household supplies",
    },
    "croma": {
        "search": croma_search,
        "cart_create": croma_cart_create,
        "cart_add": croma_cart_add,
        "place_order": croma_place_order,
        "pay": croma_pay,
        "description": "Croma — electronics and appliances: refrigerators, TVs, washing machines, laptops, phones, audio, ACs",
    },
}
