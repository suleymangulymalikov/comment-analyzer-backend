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
    return 10


# Stripe — set these in .env, then paste real Price IDs from Stripe dashboard
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

STRIPE_PRICES = {
    "pack_starter":  os.getenv("STRIPE_PRICE_PACK_STARTER", ""),   # $9.99 one-time, 50 credits
    "pack_standard": os.getenv("STRIPE_PRICE_PACK_STANDARD", ""),  # $19.99 one-time, 120 credits
    "pack_pro":      os.getenv("STRIPE_PRICE_PACK_PRO", ""),       # $39.99 one-time, 300 credits
}

STRIPE_CREDITS = {
    "pack_starter":  50,
    "pack_standard": 120,
    "pack_pro":      300,
}

# Shared secret between Next.js server and this backend.
# When set, every request except /payments/webhook must include:
# Authorization: Bearer <INTERNAL_API_SECRET>
# Leave unset in local dev to skip the check.
INTERNAL_API_SECRET = os.getenv("INTERNAL_API_SECRET", "")
