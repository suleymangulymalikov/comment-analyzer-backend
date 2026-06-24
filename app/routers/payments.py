import os
import logging
import stripe
from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel, field_validator
from urllib.parse import urlparse

from app.db.models import User, CreditTransaction
from app.config import STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRICES, STRIPE_CREDITS

router = APIRouter()
logger = logging.getLogger(__name__)

stripe.api_key = STRIPE_SECRET_KEY

_ALLOWED_REDIRECT_HOSTS = {
    h.strip()
    for h in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if h.strip()
}


def _validate_redirect_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Redirect URL must use http or https")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin not in _ALLOWED_REDIRECT_HOSTS:
        raise ValueError("Redirect URL host not allowed")
    return url


class CheckoutRequest(BaseModel):
    price_key: str
    success_url: str
    cancel_url: str

    @field_validator("success_url", "cancel_url")
    @classmethod
    def validate_redirect(cls, v: str) -> str:
        return _validate_redirect_url(v)


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

    session = stripe.checkout.Session.create(
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        mode="payment",
        success_url=req.success_url,
        cancel_url=req.cancel_url,
        metadata={"user_id": x_user_id, "price_key": req.price_key},
    )

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

    return {"status": "ok"}


def _handle_checkout_completed(session):
    price_key = session.get("metadata", {}).get("price_key")
    user_id = session.get("metadata", {}).get("user_id")

    if not price_key or not user_id:
        logger.warning("webhook_missing_metadata session_id=%s", session.get("id"))
        return

    credits = STRIPE_CREDITS.get(price_key, 0)
    if credits <= 0:
        return

    session_id = session.get("id")
    if session_id and CreditTransaction.objects(stripe_session_id=session_id).first():
        logger.info("webhook_duplicate session_id=%s user_id=%s", session_id, user_id)
        return

    User.objects(user_id=user_id).update_one(inc__credits=credits)
    CreditTransaction(
        user_id=user_id,
        amount=credits,
        type="purchase",
        description=f"Credit pack – {credits} credits",
        stripe_session_id=session_id,
    ).save()
    logger.info("webhook_credits_awarded session_id=%s user_id=%s credits=%d price_key=%s",
                session_id, user_id, credits, price_key)
