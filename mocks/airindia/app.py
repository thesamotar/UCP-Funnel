"""Mock Airindia API — electronics retailer backend.

Deliberately uses Airindia-ish conventions: RESTful resources, camelCase,
nested price objects, numeric status field.
Flow: POST /cart -> POST /cart/{id}/entries -> POST /orders -> POST /payments
Some products have specs.color = null on purpose — the wrapper's
enhance stage fills those gaps.

Routes are split by operation into sibling modules (search, cart, order,
payment); this module just assembles them into one app.
Run: uvicorn mocks.airindia.app:app --port 9002
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import cart, order, payment, search, store


@asynccontextmanager
async def lifespan(app: FastAPI):
    # catalog + surviving carts/orders come from Airindia's own Supabase tables
    await store.load()
    yield


app = FastAPI(title="Mock Airindia API", lifespan=lifespan)
app.include_router(search.router)
app.include_router(cart.router)
app.include_router(order.router)
app.include_router(payment.router)
