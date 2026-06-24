from mongoengine import (
    Document, EmbeddedDocument,
    StringField, IntField, BooleanField,
    DateTimeField, ListField, EmbeddedDocumentField
)
from datetime import datetime, timezone

from mongoengine.fields import DictField


def now():
    return datetime.now(timezone.utc)


class ChannelStats(EmbeddedDocument):
    subscriber_count = IntField(default=0)
    video_count = IntField(default=0)
    view_count = IntField(default=0)


class VideoStats(EmbeddedDocument):
    view_count = IntField(default=0)
    like_count = IntField(default=0)
    comment_count = IntField(default=0)


class User(Document):
    user_id = StringField(required=True, unique=True)
    email = StringField(required=True)
    credits = IntField(default=0)
    stripe_customer_id = StringField()

    created_at = DateTimeField(default=now)

    meta = {
        "collection": "users",
        "indexes": ["user_id", "email"]
    }


class Channel(Document):
    channel_id = StringField(required=True, unique=True)
    name = StringField(required=True)
    custom_url = StringField()
    description = StringField()
    country = StringField()
    profile_image_url = StringField()
    banner_url = StringField()
    uploads_playlist_id = StringField()

    stats = EmbeddedDocumentField(ChannelStats, default=ChannelStats)

    channel_created_at = DateTimeField()
    created_at = DateTimeField(default=now)
    updated_at = DateTimeField(default=now)

    meta = {
        "collection": "channels",
        "indexes": ["channel_id", "custom_url"]
    }

    def save(self, *args, **kwargs):
        self.updated_at = now()
        return super().save(*args, **kwargs)


class Video(Document):
    video_id = StringField(required=True, unique=True)
    channel_id = StringField(required=True)

    title = StringField(required=True)
    description = StringField()
    published_at = DateTimeField()
    thumbnail_url = StringField()
    tags = ListField(StringField())
    language = StringField()
    duration = StringField()
    made_for_kids = BooleanField(default=False)

    stats = EmbeddedDocumentField(VideoStats, default=VideoStats)

    comments_fetched = BooleanField(default=False)
    comments_fetched_at = DateTimeField()
    comments_stored_count = IntField(default=0)

    created_at = DateTimeField(default=now)
    updated_at = DateTimeField(default=now)

    meta = {
        "collection": "videos",
        "indexes": ["video_id", "channel_id", "published_at", "tags"]
    }

    def save(self, *args, **kwargs):
        self.updated_at = now()
        return super().save(*args, **kwargs)


class Comment(Document):
    comment_id = StringField(required=True, unique=True)
    video_id = StringField(required=True)
    channel_id = StringField(required=True)

    text = StringField(required=True)
    author = StringField()
    author_channel_id = StringField()

    like_count = IntField(default=0)
    published_at = DateTimeField()

    is_reply = BooleanField(default=False)
    parent_comment_id = StringField()
    reply_count = IntField(default=0)

    created_at = DateTimeField(default=now)

    meta = {
        "collection": "comments",
        "indexes": [
            "comment_id", "video_id", "channel_id",
            "parent_comment_id", "is_reply", "like_count", "published_at"
        ]
    }


class CreditTransaction(Document):
    user_id = StringField(required=True)
    amount = IntField(required=True)        # positive = added, negative = spent
    type = StringField(required=True)       # "purchase" | "analysis" | "subscription"
    description = StringField()
    stripe_session_id = StringField()
    created_at = DateTimeField(default=now)

    meta = {
        "collection": "credit_transactions",
        "indexes": [
            "user_id",
            "created_at",
            {"fields": ["stripe_session_id"], "unique": True, "sparse": True},
        ]
    }


class Analysis(Document):
    video_id = StringField(required=True)
    channel_id = StringField(required=True)
    user_id = StringField()

    provider = StringField(required=True)
    model = StringField(required=True)
    prompt_version = IntField(default=1)

    summary = StringField()
    stats = DictField()
    insights = DictField()

    created_at = DateTimeField(default=now)

    meta = {
        "collection": "analyses",
        "indexes": ["video_id", "channel_id", "user_id", "prompt_version"]
    }
