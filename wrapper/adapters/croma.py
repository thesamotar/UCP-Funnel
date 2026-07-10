"""Croma adapter — speaks the mock's RESTful, camelCase dialect."""
from .base import RetailerAdapter, RetailerError


def _ok(data: dict) -> dict:
    if data.get("status") not in (200, 201):
        raise RetailerError(f"croma: {data.get('message', 'unknown error')}")
    return data


class CromaAdapter(RetailerAdapter):
    description = ("Croma — electronics and appliances: refrigerators, TVs, washing machines, "
                   "laptops, phones, audio, ACs")

    intent_fields = {
        "min_capacity_litres": "<number or null, only for fridges when the user gives a capacity like 200L+>",
    }

    enhance_spec = {
        "field": "color",
        "fill_as": "color_options",
        "ask": "the colors each model is sold in, in India",
        "example": '{"CRM-301202": ["Shiny Steel", "Ebony Sheen"]}',
    }

    async def search(self, intent: dict) -> tuple[dict, list[dict]]:
        params = {"text": intent["search_term"], "pageSize": 8}
        if intent.get("max_price") is not None:
            params["maxPrice"] = intent["max_price"]
        if intent.get("min_price") is not None:
            params["minPrice"] = intent["min_price"]
        if intent.get("category"):
            params["category"] = intent["category"]
        if intent.get("min_capacity_litres") is not None:
            params["minCapacityLitres"] = intent["min_capacity_litres"]
        async with self.client() as client:
            resp = await client.get("/croma/api/v2/products/search", params=params)
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
                "image": p.get("imageUrl"),
                "source": {"retailer": self.name, "native_id": p["code"]},
            })
        return params, items

    async def cart_create(self) -> str:
        async with self.client() as client:
            resp = await client.post("/croma/api/v2/cart")
            return _ok(resp.json())["cart"]["cartId"]

    async def cart_add(self, cart_id: str, native_id: str, qty: int) -> dict:
        async with self.client() as client:
            resp = await client.post(f"/croma/api/v2/cart/{cart_id}/entries",
                                     json={"productCode": native_id, "quantity": qty})
            return _ok(resp.json())["cart"]

    async def place_order(self, cart_id: str) -> dict:
        async with self.client() as client:
            resp = await client.post("/croma/api/v2/orders", json={"cartId": cart_id})
            order = _ok(resp.json())["order"]
            return {"order_id": order["orderId"], "amount": order["totalPrice"]["value"]}

    async def pay(self, order_id: str) -> dict:
        async with self.client() as client:
            resp = await client.post("/croma/api/v2/payments",
                                     json={"orderId": order_id, "paymentMode": "TATANEU_CARD"})
            payment = _ok(resp.json())["payment"]
            return {"payment_id": payment["paymentId"], "status": payment["transactionStatus"],
                    "method": payment["paymentMode"]}
