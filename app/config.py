from app.ai import gemini, claude, openai

PROVIDERS = {
    "gemini": gemini,
    "claude": claude,
    "openai": openai,
}

DEFAULT_PROVIDER = "gemini"
COMMENTS_STALE_AFTER_HOURS = 24
