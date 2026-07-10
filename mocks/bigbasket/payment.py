"""BigBasket payment: charge a placed order and confirm it."""
import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from .store import ORDERS, persist_order

router = APIRouter()


class PaymentRequest(BaseModel):
    order_id: str
    method: str = "tataneu_upi"


@router.post("/bb/api/v1/payment.process")
async def payment_process(req: PaymentRequest):
    order = ORDERS.get(req.order_id)
    if not order:
        return {"status": "error", "message": "order not found"}
    if order["payment_status"] == "SUCCESS":
        return {"status": "error", "message": "order already paid"}
    txn_id = f"BBTXN-{uuid.uuid4().hex[:10].upper()}"
    order["payment_status"] = "SUCCESS"
    order["order_status"] = "CONFIRMED"
    order["payment"] = {"txn_id": txn_id, "method": req.method, "amount": order["amount"]}
    await persist_order(order)
    return {"status": "success", "payment": {"txn_id": txn_id, "payment_status": "SUCCESS",
                                             "amount": order["amount"], "method": req.method}}
