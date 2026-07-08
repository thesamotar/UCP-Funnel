"""Mock BigBasket API — grocery retailer backend.

Deliberately uses BigBasket-ish conventions: POST-everything RPC style
(`cart.create`, `order.place`), snake_case, `sp`/`mrp` pricing,
availability flags "A"/"O", status envelopes.
Flow: cart.create -> cart.add -> order.place -> payment.process

Routes are split by operation into sibling modules (search, cart, order,
payment); this module just assembles them into one app.
Run: uvicorn mocks.bigbasket.app:app --port 9001
"""
from fastapi import FastAPI

from . import cart, order, payment, search

app = FastAPI(title="Mock BigBasket API")
app.include_router(search.router)
app.include_router(cart.router)
app.include_router(order.router)
app.include_router(payment.router)
