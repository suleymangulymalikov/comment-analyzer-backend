import os
import logging
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, parse_qs

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, field_validator
from googleapiclient.discovery import build

from app.db.models import Video, Analysis, User, CreditTransaction
from app.fetchers.video import fetch_video
from app.fetchers.comments import fetch_comments
from app.services.analyzer import run_analysis
from app.config import DEFAULT_PROVIDER, COMMENTS_STALE_AFTER_HOURS, credits_for_count
from app.prompts import CURRENT_PROMPT_VERSION

router = APIRouter()
logger = logging.getLogger(__name__)

_jobs: dict[str, dict] = {}
# keys are job IDs; values: {status, result, error, user_id}
# status: "pending" | "running" | "done" | "failed"

_semaphore = threading.Semaphore(3)


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

    @field_validator("provider")
    @classmethod
    def provider_must_be_known(cls, v: str) -> str:
        from app.config import PROVIDERS
        if v not in PROVIDERS:
            raise ValueError(f"Unknown provider '{v}'. Must be one of: {list(PROVIDERS)}")
        return v


@router.post("/analyze")
def analyze(req: AnalyzeRequest, x_user_id: str | None = Header(default=None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing x-user-id header")

    user = User.objects(user_id=x_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        video_id = extract_video_id(req.video_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not _semaphore.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="Server is busy, try again in a moment")

    thread_started = False
    try:
        youtube = build("youtube", "v3", developerKey=os.getenv("YOUTUBE_API_KEY"))

        existing = Video.objects(video_id=video_id).first()
        stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=COMMENTS_STALE_AFTER_HOURS)
        if existing and existing.comments_fetched_at is not None:
            fetched_at = existing.comments_fetched_at
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        else:
            fetched_at = None
        comments_stale = (
            not existing
            or not existing.comments_fetched
            or fetched_at is None
            or fetched_at < stale_cutoff
        )

        if comments_stale:
            try:
                video, _, _, _ = fetch_video(video_id, youtube)
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e))

            comment_count = video.stats.comment_count if video.stats else 0
        else:
            video = existing
            comment_count = video.comments_stored_count or (video.stats.comment_count if video.stats else 0)

        credits_needed = credits_for_count(comment_count)
        if user.credits < credits_needed:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "insufficient_credits",
                    "required": credits_needed,
                    "balance": user.credits,
                },
            )

        job_id = str(uuid.uuid4())
        _jobs[job_id] = {"status": "pending", "result": None, "error": None, "user_id": x_user_id}

        def run_job():
            t0 = time.monotonic()
            try:
                _jobs[job_id]["status"] = "running"
                logger.info("job_start job_id=%s user_id=%s video_id=%s provider=%s",
                            job_id, x_user_id, video_id, req.provider)

                if comments_stale:
                    fetch_comments(video_id, video.channel_id, youtube)

                current_video = Video.objects(video_id=video_id).first()

                if not req.force:
                    cached = Analysis.objects(
                        video_id=video_id,
                        user_id=x_user_id,
                        provider=req.provider,
                        prompt_version=CURRENT_PROMPT_VERSION,
                    ).order_by("-created_at").first()
                else:
                    cached = None

                if cached:
                    analysis = cached
                    logger.info("job_cached job_id=%s video_id=%s analysis_id=%s",
                                job_id, video_id, str(cached.id))
                else:
                    analysis = run_analysis(video_id, current_video.channel_id, provider=req.provider, user_id=x_user_id)
                    User.objects(user_id=x_user_id).update_one(dec__credits=credits_needed)
                    CreditTransaction(
                        user_id=x_user_id,
                        amount=-credits_needed,
                        type="analysis",
                        description=f"Analyzed: {current_video.title}",
                    ).save()

                refreshed_user = User.objects(user_id=x_user_id).first()

                logger.info("job_done job_id=%s user_id=%s video_id=%s duration_s=%.1f credits_spent=%d",
                            job_id, x_user_id, video_id, time.monotonic() - t0,
                            0 if cached else credits_needed)
                _jobs[job_id]["status"] = "done"
                _jobs[job_id]["result"] = {
                    "id": str(analysis.id),
                    "video_id": video_id,
                    "video_title": current_video.title,
                    "video_thumbnail_url": current_video.thumbnail_url,
                    "provider": analysis.provider,
                    "model": analysis.model,
                    "prompt_version": analysis.prompt_version,
                    "summary": analysis.summary,
                    "stats": analysis.stats,
                    "insights": analysis.insights,
                    "created_at": analysis.created_at,
                    "credits_remaining": refreshed_user.credits,
                }
            except Exception as e:
                logger.error("job_failed job_id=%s user_id=%s video_id=%s error=%s",
                             job_id, x_user_id, video_id, e)
                _jobs[job_id]["status"] = "failed"
                _jobs[job_id]["error"] = str(e)
            finally:
                _semaphore.release()

        threading.Thread(target=run_job, daemon=True).start()
        thread_started = True

    finally:
        if not thread_started:
            _semaphore.release()

    return {"job_id": job_id}


@router.get("/analyze/status/{job_id}")
def analyze_status(job_id: str, x_user_id: str | None = Header(default=None)):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["user_id"] != x_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    status = job["status"]

    if status == "done":
        result = job["result"]
        del _jobs[job_id]
        return {"status": "done", "result": result}

    if status == "failed":
        error = job["error"]
        del _jobs[job_id]
        return {"status": "error", "error": error}

    return {"status": status}
