from datetime import datetime, timezone
from app.db.models import Comment, Video


def now():
    return datetime.now(timezone.utc)


def parse_dt(dt_str):
    return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))


def save_comment(comment_id, video_id, channel_id, text, author,
                 author_channel_id, like_count, published_at,
                 is_reply, parent_comment_id, reply_count):
    if Comment.objects(comment_id=comment_id).first():
        return False

    Comment(
        comment_id=comment_id,
        video_id=video_id,
        channel_id=channel_id,
        text=text,
        author=author,
        author_channel_id=author_channel_id,
        like_count=like_count,
        published_at=published_at,
        is_reply=is_reply,
        parent_comment_id=parent_comment_id,
        reply_count=reply_count,
        created_at=now()
    ).save()

    return True


def fetch_comments(video_id, channel_id, youtube):
    total_saved = 0
    total_skipped = 0
    quota_used = 0
    next_page_token = None

    while True:
        response = youtube.commentThreads().list(
            part="snippet,replies",
            videoId=video_id,
            maxResults=100,
            pageToken=next_page_token
        ).execute()
        quota_used += 1

        for item in response["items"]:
            thread_snippet = item["snippet"]
            top = thread_snippet["topLevelComment"]
            top_snippet = top["snippet"]
            comment_id = top["id"]
            reply_count = thread_snippet["totalReplyCount"]

            saved = save_comment(
                comment_id=comment_id,
                video_id=video_id,
                channel_id=channel_id,
                text=top_snippet["textOriginal"],
                author=top_snippet["authorDisplayName"],
                author_channel_id=top_snippet["authorChannelId"]["value"],
                like_count=top_snippet["likeCount"],
                published_at=parse_dt(top_snippet["publishedAt"]),
                is_reply=False,
                parent_comment_id=None,
                reply_count=reply_count
            )
            if saved:
                total_saved += 1
            else:
                total_skipped += 1

            inline_replies = item.get("replies", {}).get("comments", [])

            if reply_count == 0 or reply_count <= len(inline_replies):
                for reply in inline_replies:
                    reply_snippet = reply["snippet"]
                    saved = save_comment(
                        comment_id=reply["id"],
                        video_id=video_id,
                        channel_id=channel_id,
                        text=reply_snippet["textOriginal"],
                        author=reply_snippet["authorDisplayName"],
                        author_channel_id=reply_snippet["authorChannelId"]["value"],
                        like_count=reply_snippet["likeCount"],
                        published_at=parse_dt(reply_snippet["publishedAt"]),
                        is_reply=True,
                        parent_comment_id=comment_id,
                        reply_count=0
                    )
                    if saved:
                        total_saved += 1
                    else:
                        total_skipped += 1
            else:
                reply_token = None

                while True:
                    reply_response = youtube.comments().list(
                        part="snippet",
                        parentId=comment_id,
                        maxResults=100,
                        pageToken=reply_token
                    ).execute()
                    quota_used += 1

                    for reply in reply_response["items"]:
                        reply_snippet = reply["snippet"]
                        saved = save_comment(
                            comment_id=reply["id"],
                            video_id=video_id,
                            channel_id=channel_id,
                            text=reply_snippet["textOriginal"],
                            author=reply_snippet["authorDisplayName"],
                            author_channel_id=reply_snippet["authorChannelId"]["value"],
                            like_count=reply_snippet["likeCount"],
                            published_at=parse_dt(reply_snippet["publishedAt"]),
                            is_reply=True,
                            parent_comment_id=comment_id,
                            reply_count=0
                        )
                        if saved:
                            total_saved += 1
                        else:
                            total_skipped += 1

                    reply_token = reply_response.get("nextPageToken")
                    if not reply_token:
                        break

        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

    video = Video.objects(video_id=video_id).first()
    if video:
        video.comments_fetched = True
        video.comments_fetched_at = now()
        video.comments_stored_count = total_saved
        video.save()

    print(f"Comments saved: {total_saved}")
    print(f"Comments skipped (already in DB): {total_skipped}")
    print(f"Quota used: {quota_used}")

    return quota_used
