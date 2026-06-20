import os
from app.ai import gemini, claude, openai

PROVIDERS = {
    "gemini": gemini,
    "claude": claude,
    "openai": openai,
}

DEFAULT_PROVIDER = "gemini"
COMMENTS_STALE_AFTER_HOURS = 24

def credits_for_count(comment_count: int) -> int:
    return 1


# Stripe — set these in .env, then paste real Price IDs from Stripe dashboard
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

STRIPE_PRICES = {
    "pack_standard": os.getenv("STRIPE_PRICE_PACK_STANDARD", ""),   # $7.99 one-time, 10 credits
    "sub_starter":   os.getenv("STRIPE_PRICE_SUB_STARTER", ""),     # $9.99/mo, 15 credits
    "sub_pro":       os.getenv("STRIPE_PRICE_SUB_PRO", ""),         # $19.99/mo, 40 credits
}

STRIPE_CREDITS = {
    "pack_standard": 10,
    "sub_starter":   15,
    "sub_pro":       40,
}

# Shared secret between Next.js server and this backend.
# When set, every request except /payments/webhook must include:
# Authorization: Bearer <INTERNAL_API_SECRET>
# Leave unset in local dev to skip the check.
INTERNAL_API_SECRET = os.getenv("INTERNAL_API_SECRET", "")
