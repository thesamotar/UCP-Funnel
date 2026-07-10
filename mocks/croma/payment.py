"""Croma payment: charge a placed order and confirm it."""
import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from .store import ORDERS, persist_order

router = APIRouter()


class PaymentRequest(BaseModel):
    orderId: str
    paymentMode: str = "TATANEU_CARD"


@router.post("/croma/api/v2/payments")
async def process_payment(req: PaymentRequest):
    order = ORDERS.get(req.orderId)
    if not order:
        return {"payment": None, "status": 404, "message": "order not found"}
    if order["orderStatus"] == "CONFIRMED":
        return {"payment": None, "status": 409, "message": "order already paid"}
    payment_id = f"CRMPAY-{uuid.uuid4().hex[:10].upper()}"
    order["orderStatus"] = "CONFIRMED"
    order["payment"] = {"paymentId": payment_id, "paymentMode": req.paymentMode,
                        "transactionStatus": "CHARGED", "amount": order["totalPrice"]}
    await persist_order(order)
    return {"payment": order["payment"], "status": 200}
