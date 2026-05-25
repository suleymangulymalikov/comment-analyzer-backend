import os
import stripe
from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel

from app.db.models import User, CreditTransaction
from app.config import STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRICES, STRIPE_CREDITS

router = APIRouter()

stripe.api_key = STRIPE_SECRET_KEY


class CheckoutRequest(BaseModel):
    price_key: str
    success_url: str
    cancel_url: str


@router.post("/payments/checkout")
def create_checkout(req: CheckoutRequest, x_user_id: str | None = Header(default=None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing x-user-id header")

    if req.price_key not in STRIPE_PRICES:
        raise HTTPException(status_code=400, detail=f"Unknown price_key: {req.price_key}")

    price_id = STRIPE_PRICES[req.price_key]
    if not price_id:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    user = User.objects(user_id=x_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Create or retrieve Stripe customer
    if not user.stripe_customer_id:
        customer = stripe.Customer.create(email=user.email, metadata={"user_id": x_user_id})
        User.objects(user_id=x_user_id).update_one(set__stripe_customer_id=customer.id)
        customer_id = customer.id
    else:
        customer_id = user.stripe_customer_id

    is_subscription = req.price_key.startswith("sub_")
    mode = "subscription" if is_subscription else "payment"

    session_params = {
        "customer": customer_id,
        "line_items": [{"price": price_id, "quantity": 1}],
        "mode": mode,
        "success_url": req.success_url,
        "cancel_url": req.cancel_url,
        "metadata": {"user_id": x_user_id, "price_key": req.price_key},
    }

    if is_subscription:
        session_params["subscription_data"] = {
            "metadata": {"user_id": x_user_id, "price_key": req.price_key}
        }

    session = stripe.checkout.Session.create(**session_params)

    return {"checkout_url": session.url}


@router.post("/payments/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        _handle_checkout_completed(session)

    elif event["type"] == "invoice.payment_succeeded":
        invoice = event["data"]["object"]
        _handle_invoice_paid(invoice)

    return {"status": "ok"}


def _handle_checkout_completed(session):
    price_key = session.get("metadata", {}).get("price_key")
    user_id = session.get("metadata", {}).get("user_id")

    # Only handle one-time pack purchases here; subscriptions are handled via invoice
    if not price_key or not user_id or price_key.startswith("sub_"):
        return

    credits = STRIPE_CREDITS.get(price_key, 0)
    if credits <= 0:
        return

    User.objects(user_id=user_id).update_one(inc__credits=credits)
    CreditTransaction(
        user_id=user_id,
        amount=credits,
        type="purchase",
        description=f"Credit pack – {credits} credits",
        stripe_session_id=session.get("id"),
    ).save()


def _handle_invoice_paid(invoice):
    subscription_id = invoice.get("subscription")
    if not subscription_id:
        return

    subscription = stripe.Subscription.retrieve(subscription_id)
    metadata = subscription.get("metadata", {})
    price_key = metadata.get("price_key")
    user_id = metadata.get("user_id")

    if not price_key or not user_id:
        return

    credits = STRIPE_CREDITS.get(price_key, 0)
    if credits <= 0:
        return

    User.objects(user_id=user_id).update_one(inc__credits=credits)
    CreditTransaction(
        user_id=user_id,
        amount=credits,
        type="subscription",
        description=f"Subscription renewal – {credits} credits",
        stripe_session_id=invoice.get("id"),
    ).save()
