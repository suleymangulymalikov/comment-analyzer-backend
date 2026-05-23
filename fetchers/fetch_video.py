from datetime import datetime
from db.models import Video, VideoStats
from fetchers.fetch_channel import fetch_channel


def fetch_video(video_id, youtube):
    """
    Fetches video data from YouTube API and upserts to MongoDB.
    Also upserts the channel this video belongs to.
    Returns (Video document, quota_used, channel_status, video_status).
    """

    response = youtube.videos().list(
        part="snippet,statistics,contentDetails,status",
        id=video_id
    ).execute()

    if not response.get("items"):
        raise ValueError(f"No video found for id: {video_id}")

    data = response["items"][0]
    snippet = data["snippet"]
    statistics = data["statistics"]
    content_details = data["contentDetails"]
    status = data["status"]

    # --- Upsert channel first ---
    channel_id = snippet["channelId"]
    _, channel_quota, channel_status = fetch_channel(channel_id, youtube)

    # --- Thumbnail: try maxres first, fall back to standard, then high ---
    thumbnails = snippet.get("thumbnails", {})
    thumbnail_url = (
        thumbnails.get("maxres", {}).get("url") or
        thumbnails.get("standard", {}).get("url") or
        thumbnails.get("high", {}).get("url")
    )

    video_data = {
        "channel_id": channel_id,
        "title": snippet["title"],
        "description": snippet.get("description"),
        "published_at": datetime.fromisoformat(
            snippet["publishedAt"].replace("Z", "+00:00")
        ),
        "thumbnail_url": thumbnail_url,
        "tags": snippet.get("tags", []),
        "language": snippet.get("defaultLanguage"),
        "duration": content_details.get("duration"),
        "made_for_kids": status.get("madeForKids", False),
        "stats": VideoStats(
            view_count=int(statistics.get("viewCount", 0)),
            like_count=int(statistics.get("likeCount", 0)),
            comment_count=int(statistics.get("commentCount", 0))
        ),
    }

    existing = Video.objects(video_id=video_id).first()

    if existing:
        for key, value in video_data.items():
            setattr(existing, key, value)
        existing.save()
        return existing, channel_quota + 1, channel_status, "updated"
    else:
        video = Video(video_id=video_id, **video_data)
        video.save()
        return video, channel_quota + 1, channel_status, "created"