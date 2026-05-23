from mongoengine import (
    Document, EmbeddedDocument,
    StringField, IntField, BooleanField,
    DateTimeField, ListField, EmbeddedDocumentField
)
from datetime import datetime, timezone

from mongoengine.fields import DictField


def now():
    return datetime.now(timezone.utc)


# --- Embedded Stats ---

class ChannelStats(EmbeddedDocument):
    subscriber_count = IntField(default=0)
    video_count = IntField(default=0)
    view_count = IntField(default=0)


class VideoStats(EmbeddedDocument):
    view_count = IntField(default=0)
    like_count = IntField(default=0)
    comment_count = IntField(default=0)


# --- Collections ---

class Channel(Document):
    channel_id = StringField(required=True, unique=True)  # from id
    name = StringField(required=True)                     # from snippet.title
    custom_url = StringField()                            # from snippet.customUrl e.g. @calltoleap
    description = StringField()                           # from snippet.description
    country = StringField()                               # from snippet.country
    profile_image_url = StringField()                     # from snippet.thumbnails.high.url
    banner_url = StringField()                            # from brandingSettings.image.bannerExternalUrl
    uploads_playlist_id = StringField()                   # from contentDetails.relatedPlaylists.uploads

    stats = EmbeddedDocumentField(ChannelStats, default=ChannelStats)

    channel_created_at = DateTimeField()   # from snippet.publishedAt
    created_at = DateTimeField(default=now)
    updated_at = DateTimeField(default=now)

    meta = {
        "collection": "channels",
        "indexes": [
            "channel_id",   # lookup by YouTube ID
            "custom_url"    # lookup by handle e.g. @calltoleap
        ]
    }

    def save(self, *args, **kwargs):
        self.updated_at = now()
        return super().save(*args, **kwargs)


class Video(Document):
    video_id = StringField(required=True, unique=True)  # from id
    channel_id = StringField(required=True)             # from snippet.channelId

    title = StringField(required=True)                  # from snippet.title
    description = StringField()                         # from snippet.description
    published_at = DateTimeField()                      # from snippet.publishedAt
    thumbnail_url = StringField()                       # from snippet.thumbnails.maxres.url
    tags = ListField(StringField())                     # from snippet.tags
    language = StringField()                            # from snippet.defaultLanguage
    duration = StringField()                            # from contentDetails.duration e.g. PT16M35S
    made_for_kids = BooleanField(default=False)         # from status.madeForKids

    stats = EmbeddedDocumentField(VideoStats, default=VideoStats)

    comments_fetched = BooleanField(default=False)      # set by us
    comments_fetched_at = DateTimeField()               # set by us when comments are fetched
    comments_stored_count = IntField(default=0)         # set by us

    created_at = DateTimeField(default=now)
    updated_at = DateTimeField(default=now)

    meta = {
        "collection": "videos",
        "indexes": [
            "video_id",     # lookup by YouTube video ID
            "channel_id",   # get all videos for a channel
            "published_at", # sort by most recent
            "tags"          # filter by topic
        ]
    }

    def save(self, *args, **kwargs):
        self.updated_at = now()
        return super().save(*args, **kwargs)


class Comment(Document):
    comment_id = StringField(required=True, unique=True)  # from id
    video_id = StringField(required=True)                 # from snippet.videoId
    channel_id = StringField(required=True)               # from snippet.channelId

    text = StringField(required=True)                     # from snippet.textOriginal
    author = StringField()                                # from snippet.authorDisplayName
    author_channel_id = StringField()                     # from snippet.authorChannelId.value

    like_count = IntField(default=0)                      # from snippet.likeCount
    published_at = DateTimeField()                        # from snippet.publishedAt

    is_reply = BooleanField(default=False)                # derived: True if parent_comment_id exists
    parent_comment_id = StringField()                     # from snippet.parentId, null for top-level
    reply_count = IntField(default=0)                     # from commentThreads.snippet.totalReplyCount

    created_at = DateTimeField(default=now)

    meta = {
        "collection": "comments",
        "indexes": [
            "comment_id",         # lookup by comment ID
            "video_id",           # get all comments for a video
            "channel_id",         # get all comments for a channel
            "parent_comment_id",  # get all replies for a top-level comment
            "is_reply",           # filter top-level vs replies
            "like_count",         # sort by most liked
            "published_at"        # sort by most recent
        ]
    }


class Analysis(Document):
    video_id = StringField(required=True)    # which video this analysis is for
    channel_id = StringField(required=True)  # denormalized for easy channel-wide queries
 
    provider = StringField(required=True)    # e.g. "gemini", "claude", "openai"
    model = StringField(required=True)       # e.g. "gemini-2.0-flash-lite"
    prompt_version = IntField(default=1)     # increment when prompt changes
 
    summary = StringField()                  # 2-3 sentence overview
    stats = DictField()                      # total_comments_analyzed, top_liked, sentiment
    insights = DictField()                   # complaints, confusion_points, etc.
 
    created_at = DateTimeField(default=now)
 
    meta = {
        "collection": "analyses",
        "indexes": [
            "video_id",       # get all analyses for a video
            "channel_id",     # get all analyses for a channel
            "prompt_version"  # filter by prompt version
        ]
    }