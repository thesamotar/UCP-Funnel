"""Mock BigBasket API — grocery retailer backend.

Deliberately uses BigBasket-ish conventions: POST-everything RPC style
(`cart.create`, `order.place`), snake_case, `sp`/`mrp` pricing,
availability flags "A"/"O", status envelopes.
Flow: cart.create -> cart.add -> order.place -> payment.process
Run: uvicorn mocks.bigbasket_api:app --port 9001
"""
import json
import uuid
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Mock BigBasket API")

DATA = json.loads((Path(__file__).parent / "bigbasket_data.json").read_text())["products"]

# in-memory commerce state
CARTS: dict[str, dict] = {}
ORDERS: dict[str, dict] = {}


class SearchFilters(BaseModel):
    price_max: float | None = None
    price_min: float | None = None
    brand: str | None = None
    category: str | None = None


class SearchRequest(BaseModel):
    search_term: str
    filters: SearchFilters = SearchFilters()
    page_size: int = 10


def _matches(product: dict, req: SearchRequest) -> int:
    """Score a product against the search term; 0 = no match."""
    terms = [t for t in req.search_term.lower().split() if len(t) > 1]
    haystack = f"{product['desc']} {product['brand']} {product['cat']}".lower()
    score = sum(2 if t in product["desc"].lower() else 1 for t in terms if t in haystack)
    f = req.filters
    if f.price_max is not None and product["sp"] > f.price_max:
        return 0
    if f.price_min is not None and product["sp"] < f.price_min:
        return 0
    if f.brand and f.brand.lower() not in product["brand"].lower():
        return 0
    if f.category and f.category.lower() not in product["cat"].lower():
        return 0
    return score


@app.post("/bb/api/v1/product.search")
def product_search(req: SearchRequest):
    scored = [(_matches(p, req), p) for p in DATA]
    hits = [p for s, p in sorted(scored, key=lambda x: -x[0]) if s > 0]
    return {
        "status": "success",
        "tab_info": {"search_term": req.search_term, "total_count": len(hits)},
        "products": hits[: req.page_size],
    }


@app.get("/bb/api/v1/product/{sku_id}")
def product_detail(sku_id: str):
    for p in DATA:
        if p["sku_id"] == sku_id:
            return {"status": "success", "product": p}
    return {"status": "error", "message": "SKU not found"}


# --- cart / order / payment (BigBasket RPC style: POST verbs) ---------------

class CartAddRequest(BaseModel):
    cart_id: str
    sku_id: str
    qty: int = 1


class CartGetRequest(BaseModel):
    cart_id: str


class OrderPlaceRequest(BaseModel):
    cart_id: str
    delivery_address: str = "Registered TataNeu address"
    slot: str = "next available"


class PaymentRequest(BaseModel):
    order_id: str
    method: str = "tataneu_upi"


def _cart_summary(cart: dict) -> dict:
    total = sum(l["unit_sp"] * l["qty"] for l in cart["items"])
    return {**cart, "item_count": sum(l["qty"] for l in cart["items"]), "cart_value": total}


@app.post("/bb/api/v1/cart.create")
def cart_create():
    cart_id = f"BBCART-{uuid.uuid4().hex[:8].upper()}"
    CARTS[cart_id] = {"cart_id": cart_id, "items": []}
    return {"status": "success", "cart_id": cart_id}


@app.post("/bb/api/v1/cart.add")
def cart_add(req: CartAddRequest):
    cart = CARTS.get(req.cart_id)
    if not cart:
        return {"status": "error", "message": "cart not found"}
    product = next((p for p in DATA if p["sku_id"] == req.sku_id), None)
    if not product:
        return {"status": "error", "message": "SKU not found"}
    if product["availability"] != "A":
        return {"status": "error", "message": "SKU out of stock"}
    for line in cart["items"]:
        if line["sku_id"] == req.sku_id:
            line["qty"] += req.qty
            break
    else:
        cart["items"].append({
            "sku_id": req.sku_id, "desc": product["desc"],
            "unit_sp": product["sp"], "qty": req.qty,
        })
    return {"status": "success", "cart": _cart_summary(cart)}


@app.post("/bb/api/v1/cart.get")
def cart_get(req: CartGetRequest):
    cart = CARTS.get(req.cart_id)
    if not cart:
        return {"status": "error", "message": "cart not found"}
    return {"status": "success", "cart": _cart_summary(cart)}


@app.post("/bb/api/v1/order.place")
def order_place(req: OrderPlaceRequest):
    cart = CARTS.get(req.cart_id)
    if not cart:
        return {"status": "error", "message": "cart not found"}
    if not cart["items"]:
        return {"status": "error", "message": "cart is empty"}
    order_id = f"BBORD-{uuid.uuid4().hex[:8].upper()}"
    summary = _cart_summary(cart)
    ORDERS[order_id] = {
        "order_id": order_id,
        "items": cart["items"],
        "amount": summary["cart_value"],
        "delivery_address": req.delivery_address,
        "slot": req.slot,
        "order_status": "PLACED",
        "payment_status": "PENDING",
    }
    CARTS.pop(req.cart_id)
    return {"status": "success", "order": ORDERS[order_id]}


@app.post("/bb/api/v1/payment.process")
def payment_process(req: PaymentRequest):
    order = ORDERS.get(req.order_id)
    if not order:
        return {"status": "error", "message": "order not found"}
    if order["payment_status"] == "SUCCESS":
        return {"status": "error", "message": "order already paid"}
    txn_id = f"BBTXN-{uuid.uuid4().hex[:10].upper()}"
    order["payment_status"] = "SUCCESS"
    order["order_status"] = "CONFIRMED"
    order["payment"] = {"txn_id": txn_id, "method": req.method, "amount": order["amount"]}
    return {"status": "success", "payment": {"txn_id": txn_id, "payment_status": "SUCCESS",
                                             "amount": order["amount"], "method": req.method}}


@app.get("/bb/api/v1/order/{order_id}")
def order_get(order_id: str):
    order = ORDERS.get(order_id)
    if not order:
        return {"status": "error", "message": "order not found"}
    return {"status": "success", "order": order}
