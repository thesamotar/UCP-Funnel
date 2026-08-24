"""POST /ucp/v1/checkout — place one native order + payment per retailer that
has items in the caller's cart, then return a single consolidated confirmation.
Checkout requires a payment_link_id whose link Razorpay reports as `paid`
for the full cart amount — the UPI step happens first via
/ucp/v1/payment/initiate. No fallback: without Razorpay keys checkout fails
loudly (503), matching the node's no-fallback rule.
GET /ucp/v1/orders — the caller's past confirmations, newest first."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import mailer
from ..adapters import REGISTRY, RetailerError
from ..auth import current_claims, current_user
from ..razorpay import RazorpayError, configured, get_payment_link
from ..state import add_order, cart_view, get_cart, list_orders, save_cart

router = APIRouter()


class CheckoutBody(BaseModel):
    payment_link_id: str | None = None


async def _verify_paid(payment_link_id: str | None, total_inr: float) -> dict:
    """Confirm with Razorpay that the link is paid for the full cart amount,
    returning a upi_payment block for the confirmation."""
    if not configured():
        raise HTTPException(status_code=503,
                            detail="Payments are not configured on this node — "
                                   "set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET (test keys) in .env")
    if not payment_link_id:
        raise HTTPException(status_code=402, detail="payment required — call /ucp/v1/payment/initiate first")
    try:
        link = await get_payment_link(payment_link_id)
    except RazorpayError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    if link["status"] != "paid":
        raise HTTPException(status_code=402, detail=f"payment link {payment_link_id} is {link['status']}, not paid")
    if link["amount"] != int(round(total_inr * 100)):
        raise HTTPException(status_code=409,
                            detail="paid amount does not match the current cart total — "
                                   "the cart changed after the payment link was created")
    payments = link.get("payments") or []
    return {
        "provider": "razorpay",
        "payment_link_id": link["id"],
        "payment_id": payments[0]["payment_id"] if payments else None,
        "method": "UPI",
        "amount": link["amount"] / 100,
        "status": "paid",
    }


async def _email_confirmation(email: str | None, order: dict) -> dict:
    """Best-effort confirmation email — the money has already moved, so email
    problems are reported in the order rather than failing the checkout."""
    if not mailer.enabled():
        print("[checkout] confirmation email disabled — set EMAIL_ENABLED=true in .env to turn on")
        return {"status": "skipped", "detail": "email is disabled on this node"}
    if not email:
        return {"status": "skipped", "detail": "signed-in user has no email address"}
    if not mailer.configured():
        print("[checkout] confirmation email skipped — SMTP_* not set in .env")
        return {"status": "skipped", "detail": "email is not configured on this node"}
    try:
        await mailer.send_order_confirmation(email, order)
    except mailer.MailerError as exc:
        print(f"[checkout] confirmation email to {email} FAILED: {exc}")
        return {"to": email, "status": "failed", "detail": str(exc)}
    print(f"[checkout] confirmation email sent to {email}")
    return {"to": email, "status": "sent"}


@router.post("/ucp/v1/checkout")
async def checkout(body: CheckoutBody | None = None, claims: dict = Depends(current_claims)):
    user_id = claims["sub"]
    cart = await get_cart(user_id)
    if not cart["items"]:
        raise HTTPException(status_code=400, detail="cart is empty")
    view = cart_view(cart)
    upi_payment = await _verify_paid(body.payment_link_id if body else None, view["total"]["amount"])
    # place one native order + payment per retailer that has items
    active_retailers = {line["item"]["source"]["retailer"] for line in cart["items"]}
    retailer_orders = []
    for retailer, native_cart_id in cart["native_carts"].items():
        if retailer not in active_retailers:
            continue
        adapter = REGISTRY.get(retailer)
        if not adapter:
            raise HTTPException(status_code=502, detail=f"retailer {retailer!r} is no longer attached to the node")
        try:
            placed = await adapter.place_order(native_cart_id)
            payment = await adapter.pay(placed["order_id"])
        except RetailerError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        print(f"[checkout] {retailer} order {placed['order_id']} paid via {payment['payment_id']}")
        retailer_orders.append({"retailer": retailer, **placed, "payment": payment})
    order = {
        "ucp_version": "0.1",
        "type": "order_confirmation",
        "order_id": f"TATA-{uuid.uuid4().hex[:8].upper()}",
        "upi_payment": upi_payment,
        "retailer_orders": retailer_orders,
        "items": view["items"],
        "total": view["total"],
        "neu_coins_earned": int(view["total"]["amount"] * 0.05),
        "estimated_delivery": "2-4 days",
    }
    order["confirmation_email"] = await _email_confirmation(claims.get("email"), order)
    await add_order(user_id, order)
    cart["is_completed"] = True
    cart["is_active"] = False
    await save_cart(user_id, cart)
    return order


@router.get("/ucp/v1/orders")
async def past_orders(user_id: str = Depends(current_user)):
    return {"ucp_version": "0.1", "type": "order_list", "orders": await list_orders(user_id)}
