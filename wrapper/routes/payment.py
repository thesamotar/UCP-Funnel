"""UPI payment step between "my order is complete" and checkout.

POST /ucp/v1/payment/initiate — create a Razorpay (test-mode) payment link
for the caller's current cart total and return it with a scannable UPI QR
(the QR encodes the link's short_url; scanning it on a phone opens Razorpay's
checkout where test-mode UPI can be completed via the simulated flow).
GET /ucp/v1/payment/{plink_id} — current status, polled by the frontend
until Razorpay reports `paid`, after which the frontend calls checkout.
"""
import uuid

import segno
from fastapi import APIRouter, Depends, HTTPException

from ..auth import current_user
from ..razorpay import RazorpayError, configured, create_payment_link, get_payment_link
from ..state import cart_view, get_cart

router = APIRouter()


@router.post("/ucp/v1/payment/initiate")
async def initiate_payment(user_id: str = Depends(current_user)):
    if not configured():
        raise HTTPException(status_code=503,
                            detail="Payments are not configured on this node — "
                                   "set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET (test keys) in .env")
    cart = await get_cart(user_id)
    if not cart["items"]:
        raise HTTPException(status_code=400, detail="cart is empty")
    view = cart_view(cart)
    total = view["total"]["amount"]
    n_items = sum(line["quantity"] for line in cart["items"])
    try:
        link = await create_payment_link(
            amount_inr=total,
            reference_id=f"TN-{uuid.uuid4().hex[:10].upper()}",
            description=f"Tata Neu order — {n_items} item{'s' if n_items != 1 else ''}",
        )
    except RazorpayError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    print(f"[payment] {link['id']} created for ₹{total} ({link['short_url']})")
    return {
        "ucp_version": "0.1",
        "type": "payment_request",
        "payment_link_id": link["id"],
        "short_url": link["short_url"],
        "qr_data_uri": segno.make(link["short_url"], error="m").png_data_uri(scale=6, border=2),
        "amount": total,
        "currency": "INR",
        "status": link["status"],  # "created" until paid
    }


@router.get("/ucp/v1/payment/{plink_id}")
async def payment_status(plink_id: str, user_id: str = Depends(current_user)):
    try:
        link = await get_payment_link(plink_id)
    except RazorpayError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {
        "payment_link_id": link["id"],
        "status": link["status"],
        "amount": link["amount"] / 100,
        "amount_paid": link.get("amount_paid", 0) / 100,
    }
