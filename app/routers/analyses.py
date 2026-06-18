from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Header, Query

from app.db.models import Analysis, Video

router = APIRouter()

_MAX_PAGE_SIZE = 50


@router.get("/analyses")
def list_analyses(
    x_user_id: str | None = Header(default=None),
    limit: int = Query(default=20, ge=1, le=_MAX_PAGE_SIZE),
    skip: int = Query(default=0, ge=0),
):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing x-user-id header")

    analyses = Analysis.objects(user_id=x_user_id).order_by("-created_at").skip(skip).limit(limit)

    video_ids = {a.video_id for a in analyses}
    videos = {v.video_id: v for v in Video.objects(video_id__in=list(video_ids))}

    return [
        {
            "id": str(a.id),
            "video_id": a.video_id,
            "video_title": videos[a.video_id].title if a.video_id in videos else None,
            "video_thumbnail_url": videos[a.video_id].thumbnail_url if a.video_id in videos else None,
            "provider": a.provider,
            "model": a.model,
            "prompt_version": a.prompt_version,
            "summary": a.summary,
            "created_at": a.created_at,
        }
        for a in analyses
    ]


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: str, x_user_id: str | None = Header(default=None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing x-user-id header")

    try:
        oid = ObjectId(analysis_id)
    except (InvalidId, Exception):
        raise HTTPException(status_code=404, detail="Analysis not found")

    analysis = Analysis.objects(id=oid, user_id=x_user_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    video = Video.objects(video_id=analysis.video_id).first()

    return {
        "id": str(analysis.id),
        "video_id": analysis.video_id,
        "video_title": video.title if video else None,
        "video_thumbnail_url": video.thumbnail_url if video else None,
        "provider": analysis.provider,
        "model": analysis.model,
        "prompt_version": analysis.prompt_version,
        "summary": analysis.summary,
        "stats": analysis.stats,
        "insights": analysis.insights,
        "created_at": analysis.created_at,
    }
