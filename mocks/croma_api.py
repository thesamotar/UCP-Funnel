"""Mock Croma API — electronics retailer backend.

Deliberately uses Croma-ish conventions: RESTful resources, camelCase,
nested price objects, numeric status field.
Flow: POST /cart -> POST /cart/{id}/entries -> POST /orders -> POST /payments
Some products have specs.color = null on purpose — the wrapper's
enhance stage fills those gaps.
Run: uvicorn mocks.croma_api:app --port 9002
"""
import json
import re
import uuid
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Mock Croma API")

# in-memory commerce state
CARTS: dict[str, dict] = {}
ORDERS: dict[str, dict] = {}

DATA = json.loads((Path(__file__).parent / "croma_data.json").read_text())["products"]

CAPACITY_RE = re.compile(r"([\d.]+)\s*(l|kg|ton)", re.I)


def _capacity_litres(product: dict) -> float | None:
    cap = (product.get("specs") or {}).get("capacity") or ""
    m = CAPACITY_RE.match(cap.strip())
    return float(m.group(1)) if m and m.group(2).lower() == "l" else None


@app.get("/croma/api/v2/products/search")
def search(
    text: str,
    maxPrice: float | None = None,
    minPrice: float | None = None,
    category: str | None = None,
    minCapacityLitres: float | None = None,
    pageSize: int = 10,
):
    terms = [t for t in text.lower().split() if len(t) > 1]
    hits = []
    for p in DATA:
        haystack = f"{p['name']} {p['brandName']} {p['category']}".lower()
        score = sum(2 if t in p["name"].lower() else 1 for t in terms if t in haystack)
        if category and category.lower() in p["category"].lower():
            score += 3
        elif category and score == 0:
            continue
        if score == 0:
            continue
        price = p["price"]["sellingPrice"]
        if maxPrice is not None and price > maxPrice:
            continue
        if minPrice is not None and price < minPrice:
            continue
        if minCapacityLitres is not None:
            litres = _capacity_litres(p)
            if litres is None or litres < minCapacityLitres:
                continue
        hits.append((score, p))
    hits.sort(key=lambda x: -x[0])
    products = [p for _, p in hits[:pageSize]]
    return {"searchResult": {"products": products, "totalCount": len(products)}, "status": 200}


@app.get("/croma/api/v2/products/{code}")
def detail(code: str):
    for p in DATA:
        if p["code"] == code:
            return {"product": p, "status": 200}
    return {"product": None, "status": 404, "message": "not found"}


# --- cart / order / payment (Croma REST style) ------------------------------

class CartEntryRequest(BaseModel):
    productCode: str
    quantity: int = 1


class OrderRequest(BaseModel):
    cartId: str
    deliveryAddress: str = "Registered TataNeu address"


class PaymentRequest(BaseModel):
    orderId: str
    paymentMode: str = "TATANEU_CARD"


def _cart_view(cart: dict) -> dict:
    total = sum(e["unitPrice"] * e["quantity"] for e in cart["entries"])
    return {**cart, "totalItems": sum(e["quantity"] for e in cart["entries"]),
            "totalPrice": {"value": total, "currencyIso": "INR"}}


@app.post("/croma/api/v2/cart")
def create_cart():
    cart_id = f"CRMCART-{uuid.uuid4().hex[:8].upper()}"
    CARTS[cart_id] = {"cartId": cart_id, "entries": []}
    return {"cart": _cart_view(CARTS[cart_id]), "status": 201}


@app.post("/croma/api/v2/cart/{cart_id}/entries")
def add_entry(cart_id: str, req: CartEntryRequest):
    cart = CARTS.get(cart_id)
    if not cart:
        return {"cart": None, "status": 404, "message": "cart not found"}
    product = next((p for p in DATA if p["code"] == req.productCode), None)
    if not product:
        return {"cart": None, "status": 404, "message": "product not found"}
    if not product.get("inStock"):
        return {"cart": None, "status": 409, "message": "product out of stock"}
    for entry in cart["entries"]:
        if entry["productCode"] == req.productCode:
            entry["quantity"] += req.quantity
            break
    else:
        cart["entries"].append({
            "productCode": req.productCode, "name": product["name"],
            "unitPrice": product["price"]["sellingPrice"], "quantity": req.quantity,
        })
    return {"cart": _cart_view(cart), "status": 200}


@app.get("/croma/api/v2/cart/{cart_id}")
def get_cart(cart_id: str):
    cart = CARTS.get(cart_id)
    if not cart:
        return {"cart": None, "status": 404, "message": "cart not found"}
    return {"cart": _cart_view(cart), "status": 200}


@app.post("/croma/api/v2/orders")
def place_order(req: OrderRequest):
    cart = CARTS.get(req.cartId)
    if not cart:
        return {"order": None, "status": 404, "message": "cart not found"}
    if not cart["entries"]:
        return {"order": None, "status": 400, "message": "cart is empty"}
    order_id = f"CRMORD-{uuid.uuid4().hex[:8].upper()}"
    view = _cart_view(cart)
    ORDERS[order_id] = {
        "orderId": order_id,
        "entries": cart["entries"],
        "totalPrice": view["totalPrice"],
        "deliveryAddress": req.deliveryAddress,
        "orderStatus": "PAYMENT_PENDING",
    }
    CARTS.pop(req.cartId)
    return {"order": ORDERS[order_id], "status": 201}


@app.post("/croma/api/v2/payments")
def process_payment(req: PaymentRequest):
    order = ORDERS.get(req.orderId)
    if not order:
        return {"payment": None, "status": 404, "message": "order not found"}
    if order["orderStatus"] == "CONFIRMED":
        return {"payment": None, "status": 409, "message": "order already paid"}
    payment_id = f"CRMPAY-{uuid.uuid4().hex[:10].upper()}"
    order["orderStatus"] = "CONFIRMED"
    order["payment"] = {"paymentId": payment_id, "paymentMode": req.paymentMode,
                        "transactionStatus": "CHARGED", "amount": order["totalPrice"]}
    return {"payment": order["payment"], "status": 200}


@app.get("/croma/api/v2/orders/{order_id}")
def get_order(order_id: str):
    order = ORDERS.get(order_id)
    if not order:
        return {"order": None, "status": 404, "message": "not found"}
    return {"order": order, "status": 200}
