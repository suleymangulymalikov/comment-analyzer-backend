import os
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, parse_qs

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from googleapiclient.discovery import build

from app.db.models import Video, Analysis
from app.fetchers.video import fetch_video
from app.fetchers.comments import fetch_comments
from app.services.analyzer import run_analysis
from app.config import DEFAULT_PROVIDER, COMMENTS_STALE_AFTER_HOURS
from app.prompts import CURRENT_PROMPT_VERSION

router = APIRouter()


def extract_video_id(url: str) -> str:
    parsed = urlparse(url)

    if parsed.hostname == "youtu.be":
        vid = parsed.path.lstrip("/").split("/")[0]
        if vid:
            return vid

    if parsed.hostname in ("www.youtube.com", "youtube.com", "m.youtube.com"):
        qs = parse_qs(parsed.query)
        if "v" in qs:
            return qs["v"][0]
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "shorts":
            return parts[1]

    raise ValueError(f"Cannot extract video ID from: {url}")


class AnalyzeRequest(BaseModel):
    video_url: str
    provider: str = DEFAULT_PROVIDER
    force: bool = False


@router.post("/analyze")
def analyze(req: AnalyzeRequest, x_user_id: str | None = Header(default=None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing x-user-id header")

    try:
        video_id = extract_video_id(req.video_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    youtube = build("youtube", "v3", developerKey=os.getenv("YOUTUBE_API_KEY"))

    existing = Video.objects(video_id=video_id).first()
    stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=COMMENTS_STALE_AFTER_HOURS)
    comments_stale = (
        not existing
        or not existing.comments_fetched
        or existing.comments_fetched_at is None
        or existing.comments_fetched_at.replace(tzinfo=timezone.utc) < stale_cutoff
    )
    if comments_stale:
        try:
            video, _, _, _ = fetch_video(video_id, youtube)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        fetch_comments(video_id, video.channel_id, youtube)

    video = Video.objects(video_id=video_id).first()

    if not req.force:
        analysis = Analysis.objects(
            video_id=video_id,
            user_id=x_user_id,
            provider=req.provider,
            prompt_version=CURRENT_PROMPT_VERSION,
        ).order_by("-created_at").first()
    else:
        analysis = None

    if not analysis:
        try:
            analysis = run_analysis(video_id, video.channel_id, provider=req.provider, user_id=x_user_id)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    return {
        "id": str(analysis.id),
        "video_id": video_id,
        "video_title": video.title,
        "video_thumbnail_url": video.thumbnail_url,
        "provider": analysis.provider,
        "model": analysis.model,
        "prompt_version": analysis.prompt_version,
        "summary": analysis.summary,
        "stats": analysis.stats,
        "insights": analysis.insights,
        "created_at": analysis.created_at,
    }
