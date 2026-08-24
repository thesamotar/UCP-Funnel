"""AirIndiaAdapter adapter — speaks the mock's RESTful, camelCase dialect."""
from __future__ import annotations

from .base import RetailerAdapter, RetailerError

def _ok(data: dict) -> dict:
    if data.get("status") not in (200, 201):
        raise RetailerError(f"airindia: {data.get('message', 'unknown error')}")
    return data

class AirIndiaAdapter(RetailerAdapter):
    description = "Air India — flights, economy, business class, travel, bookings"

    intent_fields = {
        'origin': '<string, e.g. Delhi, Mumbai, Goa, Shimla, only if user specifies origin>',
        'destination': '<string, e.g. Delhi, Mumbai, Goa, Shimla, only if user specifies destination>',
        'class': '<string, e.g. Economy, Business, only if user specifies travel class>'
    }
    enhance_spec = {}

    async def search(self, intent: dict) -> tuple[dict, list[dict]]:
        params = {"text": intent["search_term"], "pageSize": 8}
        if intent.get("max_price") is not None:
            params["maxPrice"] = intent["max_price"]
        if intent.get("min_price") is not None:
            params["minPrice"] = intent["min_price"]
        if intent.get("category"):
            params["category"] = intent["category"]
        
        # Add custom intent fields dynamically
        for key in self.intent_fields:
            if intent.get(key) is not None:
                params[key] = intent[key]

        async with self.client() as client:
            resp = await client.get(f"/airindia/api/v2/products/search", params=params)
            resp.raise_for_status()
            data = resp.json()
            
        items = []
        for p in data.get("searchResult", {}).get("products", []):
            specs = {k: v for k, v in (p.get("specs") or {}).items()}
            # Incorporate generated top-level attributes
            if "origin" in p: specs["origin"] = p["origin"]
            if "destination" in p: specs["destination"] = p["destination"]
            if "class" in p: specs["class"] = p["class"]
            if "departureTime" in p: specs["departure_time"] = p["departureTime"]
            if "arrivalTime" in p: specs["arrival_time"] = p["arrivalTime"]
            
            price_val = p.get("price", 0)
            if isinstance(price_val, dict):
                amount = price_val.get("sellingPrice", 0)
                mrp = price_val.get("mrp", amount)
            else:
                amount = price_val
                mrp = price_val
                
            items.append({
                "id": p["code"],
                "title": p["name"],
                "brand": p["brand"],
                "price": {"amount": amount, "mrp": mrp, "currency": "INR"},
                "attributes": {"category": p["category"], **specs},
                "availability": "in_stock" if p.get("inStock") else "out_of_stock",
                "image": p.get("imageUrl"),
                "source": {"retailer": self.name, "native_id": p["code"]},
            })
        return params, items

    async def cart_create(self) -> str:
        async with self.client() as client:
            resp = await client.post(f"/airindia/api/v2/cart")
            return _ok(resp.json())["cart"]["cartId"]

    async def cart_add(self, cart_id: str, native_id: str, qty: int) -> dict:
        async with self.client() as client:
            resp = await client.post(f"/airindia/api/v2/cart/{cart_id}/entries",
                                     json={"productCode": native_id, "quantity": qty})
            return _ok(resp.json())["cart"]

    async def place_order(self, cart_id: str) -> dict:
        async with self.client() as client:
            resp = await client.post(f"/airindia/api/v2/orders", json={"cartId": cart_id})
            order = _ok(resp.json())["order"]
            return {"order_id": order["orderId"], "amount": order["totalPrice"]["value"]}

    async def pay(self, order_id: str) -> dict:
        async with self.client() as client:
            resp = await client.post(f"/airindia/api/v2/payments",
                                     json={"orderId": order_id, "paymentMode": "TATANEU_CARD"})
            payment = _ok(resp.json())["payment"]
            return {"payment_id": payment["paymentId"], "status": payment["transactionStatus"],
                    "method": payment["paymentMode"]}
