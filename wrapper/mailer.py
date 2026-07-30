"""Order-confirmation email, sent over plain SMTP after a paid checkout.

Any STARTTLS-capable SMTP server works; the expected setup is a Gmail app
password (smtp.gmail.com:587). Configured via .env: SMTP_HOST, SMTP_PORT,
SMTP_USER, SMTP_PASS, and optionally SMTP_FROM (defaults to SMTP_USER).
Sending happens in a thread (smtplib is blocking) under a wall-clock timeout.
Checkout never fails because of email — by the time we send, the money has
moved and the retailer orders are placed — but the outcome is reported in the
order's `confirmation_email` block rather than swallowed.
"""
import asyncio
import os
import smtplib
from email.message import EmailMessage

TIMEOUT_S = 15


class MailerError(Exception):
    pass


def enabled() -> bool:
    """Master on/off switch. Email stays off unless EMAIL_ENABLED is truthy,
    so a broken/unverified SMTP setup can't surface errors after checkout."""
    return os.getenv("EMAIL_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def configured() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_USER") and os.getenv("SMTP_PASS"))


def _inr(amount: float) -> str:
    return f"₹{amount:,.0f}" if amount == int(amount) else f"₹{amount:,.2f}"


def _build(to_email: str, order: dict) -> EmailMessage:
    total = order["total"]["amount"]
    payment = order.get("upi_payment") or {}
    lines = [
        (line["item"]["title"], line["quantity"],
         line["item"]["price"]["amount"] * line["quantity"])
        for line in order["items"]
    ]

    msg = EmailMessage()
    msg["Subject"] = f"Order {order['order_id']} confirmed — {_inr(total)}"
    msg["From"] = os.getenv("SMTP_FROM") or os.environ["SMTP_USER"]
    msg["To"] = to_email

    text = [f"Your Tata Neu order {order['order_id']} is confirmed.", ""]
    text += [f"  {qty} x {title} — {_inr(amt)}" for title, qty, amt in lines]
    text += [
        "",
        f"Total paid: {_inr(total)} (UPI, payment {payment.get('payment_id') or payment.get('payment_link_id', '')})",
        f"NeuCoins earned: {order['neu_coins_earned']}",
        f"Estimated delivery: {order['estimated_delivery']}",
    ]
    msg.set_content("\n".join(text))

    rows = "".join(
        f"<tr><td style='padding:6px 12px 6px 0'>{qty} × {title}</td>"
        f"<td style='padding:6px 0;text-align:right'>{_inr(amt)}</td></tr>"
        for title, qty, amt in lines
    )
    msg.add_alternative(f"""\
<div style="font-family:'Google Sans',Roboto,Arial,sans-serif;max-width:560px;margin:0 auto;color:#1f1f1f">
  <h2 style="font-weight:500">Order confirmed \U0001f389</h2>
  <p>Your Tata Neu order <b>{order['order_id']}</b> has been placed and paid.</p>
  <table style="width:100%;border-collapse:collapse;border-top:1px solid #e0e0e0;border-bottom:1px solid #e0e0e0">
    {rows}
    <tr><td style="padding:10px 12px 10px 0"><b>Total paid (UPI)</b></td>
        <td style="padding:10px 0;text-align:right"><b>{_inr(total)}</b></td></tr>
  </table>
  <p style="color:#5f6368;font-size:14px">
    Payment {payment.get('payment_id') or payment.get('payment_link_id', '')} ·
    {order['neu_coins_earned']} NeuCoins earned ·
    Estimated delivery {order['estimated_delivery']}
  </p>
</div>
""", subtype="html")
    return msg


def _send_blocking(msg: EmailMessage) -> None:
    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=TIMEOUT_S) as smtp:
        smtp.starttls()
        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        smtp.send_message(msg)


async def send_order_confirmation(to_email: str, order: dict) -> None:
    if not configured():
        raise MailerError("email is not configured — set SMTP_HOST/SMTP_USER/SMTP_PASS in .env")
    try:
        await asyncio.wait_for(asyncio.to_thread(_send_blocking, _build(to_email, order)), TIMEOUT_S + 5)
    except (smtplib.SMTPException, OSError, asyncio.TimeoutError) as exc:
        raise MailerError(f"SMTP send failed: {exc}") from exc
