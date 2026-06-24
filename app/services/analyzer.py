import logging
import time
from datetime import datetime, timezone
from typing import List
from pydantic import BaseModel, ValidationError
from app.db.models import Comment, Analysis
from app.prompts import PROMPTS, CURRENT_PROMPT_VERSION
from app.config import PROVIDERS, DEFAULT_PROVIDER

logger = logging.getLogger(__name__)


class _LikedComment(BaseModel):
    text: str
    likes: int


class _Sentiment(BaseModel):
    positive: int
    neutral: int
    negative: int


class _Stats(BaseModel):
    total_comments_analyzed: int
    top_liked_comments: List[_LikedComment]
    sentiment_breakdown: _Sentiment


class _InsightItem(BaseModel):
    title: str
    description: str


class _VideoIdea(BaseModel):
    title: str
    reason: str


class _Insights(BaseModel):
    complaints: List[_InsightItem]
    confusion_points: List[_InsightItem]
    content_requests: List[_InsightItem]
    audience_struggles: List[_InsightItem]
    content_gaps: List[_InsightItem]
    video_ideas: List[_VideoIdea]


class AnalysisResult(BaseModel):
    summary: str
    stats: _Stats
    insights: _Insights


def run_analysis(video_id, channel_id, provider=DEFAULT_PROVIDER, user_id=None):
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: '{provider}'. Choose from: {list(PROVIDERS.keys())}")

    comments_qs = Comment.objects(
        video_id=video_id,
    ).order_by("-like_count")

    if not comments_qs:
        raise ValueError(f"No comments found for video_id: {video_id}")

    comments = [
        {"text": c.text, "likes": c.like_count}
        for c in comments_qs
    ]

    prompt = PROMPTS[CURRENT_PROMPT_VERSION]

    logger.info("analysis_start video_id=%s user_id=%s provider=%s prompt_v=%d comments=%d",
                video_id, user_id, provider, CURRENT_PROMPT_VERSION, len(comments))

    t0 = time.monotonic()
    result, model = PROVIDERS[provider].analyze(comments, prompt)
    duration = time.monotonic() - t0

    try:
        AnalysisResult.model_validate(result)
    except ValidationError as e:
        raise ValueError(f"AI response failed validation: {e}") from e

    analysis = Analysis(
        video_id=video_id,
        channel_id=channel_id,
        user_id=user_id,
        provider=provider,
        model=model,
        prompt_version=CURRENT_PROMPT_VERSION,
        summary=result.get("summary"),
        stats=result.get("stats", {}),
        insights=result.get("insights", {}),
        created_at=datetime.now(timezone.utc)
    )
    analysis.save()

    logger.info("analysis_done video_id=%s user_id=%s provider=%s model=%s duration_s=%.1f",
                video_id, user_id, provider, model, duration)
    return analysis
