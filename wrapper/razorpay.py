"""Razorpay Payment Links client (test mode).

The node creates one payment link per checkout attempt for the exact cart
total; the frontend renders it as a UPI QR and polls until Razorpay reports
`paid`. Auth is HTTP basic with the key pair from .env (rzp_test_… keys —
never commit live keys). No webhooks: status is polled via GET, which works
locally without a public URL.
"""
import asyncio
import base64
import os

import httpx

API_BASE = "https://api.razorpay.com/v1"
TIMEOUT_S = 15


class RazorpayError(Exception):
    pass


def configured() -> bool:
    return bool(os.getenv("RAZORPAY_KEY_ID") and os.getenv("RAZORPAY_KEY_SECRET"))


def _auth_header() -> dict:
    pair = f"{os.getenv('RAZORPAY_KEY_ID')}:{os.getenv('RAZORPAY_KEY_SECRET')}"
    return {"Authorization": "Basic " + base64.b64encode(pair.encode()).decode()}


async def _request(method: str, path: str, json: dict | None = None) -> dict:
    if not configured():
        raise RazorpayError("Razorpay is not configured — set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in .env")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            resp = await client.request(method, API_BASE + path, json=json, headers=_auth_header())
    except (httpx.HTTPError, asyncio.TimeoutError) as exc:
        raise RazorpayError(f"Razorpay unreachable: {exc}") from exc
    body = resp.json() if resp.content else {}
    if resp.status_code >= 400:
        detail = (body.get("error") or {}).get("description") or resp.text
        raise RazorpayError(f"Razorpay {resp.status_code}: {detail}")
    return body


async def create_payment_link(amount_inr: float, reference_id: str, description: str) -> dict:
    """Create a payment link for the given INR amount. Returns the raw link
    object ({id, short_url, status, amount, …}); amount is sent in paise."""
    return await _request("POST", "/payment_links", json={
        "amount": int(round(amount_inr * 100)),
        "currency": "INR",
        "reference_id": reference_id,
        "description": description,
        "notify": {"sms": False, "email": False},
        "notes": {"source": "tata-neu-ucp-node"},
    })


async def get_payment_link(plink_id: str) -> dict:
    """Fetch a payment link. status: created | partially_paid | paid | cancelled | expired."""
    return await _request("GET", f"/payment_links/{plink_id}")
