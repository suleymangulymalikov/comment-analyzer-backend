from datetime import datetime, timezone
from db.models import Comment, Analysis
from helpers.prompts import PROMPTS, CURRENT_PROMPT_VERSION
from config import PROVIDERS, DEFAULT_PROVIDER


def run_analysis(video_id, channel_id, provider=DEFAULT_PROVIDER):
    """
    Pulls top-level comments from MongoDB, sends to AI, saves Analysis document.
    Returns the Analysis document.
    """

    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: '{provider}'. Choose from: {list(PROVIDERS.keys())}")

    comments_qs = Comment.objects(
        video_id=video_id,
        is_reply=False
    ).order_by("-like_count")

    if not comments_qs:
        raise ValueError(f"No comments found for video_id: {video_id}")

    comments = [
        {"text": c.text, "likes": c.like_count}
        for c in comments_qs
    ]

    prompt = PROMPTS[CURRENT_PROMPT_VERSION]

    print(f"  Analyzing {len(comments)} comments with {provider} (prompt v{CURRENT_PROMPT_VERSION})...")

    result, model = PROVIDERS[provider].analyze(comments, prompt)

    analysis = Analysis(
        video_id=video_id,
        channel_id=channel_id,
        provider=provider,
        model=model,
        prompt_version=CURRENT_PROMPT_VERSION,
        summary=result.get("summary"),
        stats=result.get("stats", {}),
        insights=result.get("insights", {}),
        created_at=datetime.now(timezone.utc)
    )
    analysis.save()

    print(f"  ✓ Analysis saved (provider={provider}, model={model}, prompt_version={CURRENT_PROMPT_VERSION})")
    return analysis