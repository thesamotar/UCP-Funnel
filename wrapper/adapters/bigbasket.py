"""BigBasket adapter — speaks the mock's RPC-style, snake_case dialect."""
from .base import RetailerAdapter, RetailerError


def _ok(data: dict) -> dict:
    if data.get("status") != "success":
        raise RetailerError(f"bigbasket: {data.get('message', 'unknown error')}")
    return data


class BigBasketAdapter(RetailerAdapter):
    description = "BigBasket — groceries, fresh produce, dairy, staples, snacks, household supplies"

    async def search(self, intent: dict) -> tuple[dict, list[dict]]:
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
        async with self.client() as client:
            resp = await client.post("/bb/api/v1/product.search", json=native_req)
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
                "image": p.get("img"),
                "source": {"retailer": self.name, "native_id": p["sku_id"]},
            })
        return native_req, items

    async def cart_create(self) -> str:
        async with self.client() as client:
            resp = await client.post("/bb/api/v1/cart.create")
            return _ok(resp.json())["cart_id"]

    async def cart_add(self, cart_id: str, native_id: str, qty: int) -> dict:
        async with self.client() as client:
            resp = await client.post("/bb/api/v1/cart.add",
                                     json={"cart_id": cart_id, "sku_id": native_id, "qty": qty})
            return _ok(resp.json())["cart"]

    async def place_order(self, cart_id: str) -> dict:
        async with self.client() as client:
            resp = await client.post("/bb/api/v1/order.place", json={"cart_id": cart_id})
            order = _ok(resp.json())["order"]
            return {"order_id": order["order_id"], "amount": order["amount"]}

    async def pay(self, order_id: str) -> dict:
        async with self.client() as client:
            resp = await client.post("/bb/api/v1/payment.process",
                                     json={"order_id": order_id, "method": "tataneu_upi"})
            payment = _ok(resp.json())["payment"]
            return {"payment_id": payment["txn_id"], "status": payment["payment_status"],
                    "method": payment["method"]}
