from ai import gemini, claude, openai

PROVIDERS = {
    "gemini": gemini,
    "claude": claude,
    "openai": openai
}

DEFAULT_PROVIDER = "gemini"