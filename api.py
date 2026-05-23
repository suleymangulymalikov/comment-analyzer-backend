import os
from contextlib import asynccontextmanager
from urllib.parse import urlparse, parse_qs

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from googleapiclient.discovery import build
from dotenv import load_dotenv

from db.connection import connect_db
from db.models import Video
from fetchers.fetch_video import fetch_video
from fetchers.fetch_comments import fetch_comments
from analyzer import run_analysis
from config import DEFAULT_PROVIDER

load_dotenv()


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    connect_db()
    yield


app = FastAPI(lifespan=lifespan)


class AnalyzeRequest(BaseModel):
    video_url: str
    provider: str = DEFAULT_PROVIDER


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    try:
        video_id = extract_video_id(req.video_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    youtube = build("youtube", "v3", developerKey=os.getenv("YOUTUBE_API_KEY"))

    existing = Video.objects(video_id=video_id).first()
    if not existing or not existing.comments_fetched:
        try:
            video, _, _, _ = fetch_video(video_id, youtube)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        fetch_comments(video_id, video.channel_id, youtube)

    video = Video.objects(video_id=video_id).first()

    try:
        analysis = run_analysis(video_id, video.channel_id, provider=req.provider)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {
        "video_id": video_id,
        "title": video.title,
        "provider": analysis.provider,
        "model": analysis.model,
        "summary": analysis.summary,
        "stats": analysis.stats,
        "insights": analysis.insights,
    }
