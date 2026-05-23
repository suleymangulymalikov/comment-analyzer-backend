from datetime import datetime
from db.models import Channel, ChannelStats

def fetch_channel(channel_id, youtube):
    """
    Fetches channel data from YouTube API and upserts to MongoDB.
    Returns the Channel document.
    """

    response = youtube.channels().list(
        part="snippet,statistics,brandingSettings,contentDetails",
        id=channel_id
    ).execute()

    if not response.get("items"):
        raise ValueError(f"Channel with ID {channel_id} not found")
    
    data = response["items"][0]
    snippet = data["snippet"]
    statistics = data["statistics"]
    content_details = data["contentDetails"]
    branding = data.get("brandingSettings", {})

    # Map API response to Channel document
    channel_data = {
        "name": snippet["title"],
        "custom_url": snippet.get("customUrl"),
        "description": snippet.get("description"),
        "country": snippet.get("country"),
        "profile_image_url": snippet.get("thumbnails", {}).get("high", {}).get("url"),
        "banner_url": branding.get("image", {}).get("bannerExternalUrl"),
        "uploads_playlist_id": content_details["relatedPlaylists"].get("uploads"),
        "stats": ChannelStats(
            subscriber_count=int(statistics.get("subscriberCount", 0)),
            video_count=int(statistics.get("videoCount", 0)),
            view_count=int(statistics.get("viewCount", 0))
        ),
        "channel_created_at": datetime.fromisoformat(
            snippet["publishedAt"].replace("Z", "+00:00")
        ),
    }

    # Upsert to MongoDB
    existing = Channel.objects(channel_id=channel_id).first()

    if existing:
        for key, value in channel_data.items():
            setattr(existing, key, value)
        existing.save()
        return existing, 1, "updated"
    else:
        channel = Channel(channel_id=channel_id, **channel_data)
        channel.save()
        return channel, 1, "created"