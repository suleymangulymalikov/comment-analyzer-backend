import os
import argparse
from datetime import datetime, timezone
from googleapiclient.discovery import build
from dotenv import load_dotenv

from db.connection import connect_db, disconnect_db
from db.models import Video
from fetchers.fetch_video import fetch_video
from fetchers.fetch_comments import fetch_comments
from analyzer import run_analysis
from helpers.html_generator import generate_html
from helpers.pdf_generator import generate_pdf
from config import DEFAULT_PROVIDER

load_dotenv()

QUOTA_LOG_FILE = "logs/quota_log.txt"


def log_quota(video_id, video_title, quota_channel, quota_video, quota_comments):
    total = quota_channel + quota_video + quota_comments
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    line = (
        f"{timestamp} | "
        f"video_id={video_id} | "
        f'title="{video_title[:50]}" | '
        f"channel={quota_channel} | "
        f"video={quota_video} | "
        f"comments={quota_comments} | "
        f"total={total}\n"
    )
    os.makedirs("logs", exist_ok=True)
    with open(QUOTA_LOG_FILE, "a") as f:
        f.write(line)
    return total


def do_fetch(video_id, youtube):
    existing = Video.objects(video_id=video_id).first()
    if existing and existing.comments_fetched:
        print(f"Already fetched: {existing.title}")
        print("Skipping fetch. Use --report to run analysis.")
        return None

    print("\n--- Fetching video & channel ---")
    video, video_quota, channel_status, video_status = fetch_video(video_id, youtube)
    quota_channel = 1
    quota_video = video_quota - quota_channel
    print(f"  ✓ Channel {channel_status}: {video.channel_id}")
    print(f"  ✓ Video {video_status}: {video.title[:60]}")

    print("\n--- Fetching comments ---")
    quota_comments = fetch_comments(video_id, video.channel_id, youtube)

    total = log_quota(video_id, video.title, quota_channel, quota_video, quota_comments)
    print(f"\n  ✓ Fetch complete. Quota used: {total} units (logged to {QUOTA_LOG_FILE})")
    return video


def do_analyze(video_id, provider):
    video = Video.objects(video_id=video_id).first()
    if not video:
        print(f"Video not found in DB: {video_id}")
        print("Run with --fetch first.")
        return False

    if not video.comments_fetched:
        print(f"Comments not yet fetched for: {video.title}")
        print("Run with --fetch first.")
        return False

    print(f"\n--- Running analysis ({provider}) ---")
    analysis = run_analysis(video_id, video.channel_id, provider=provider)
    print(f"  ✓ Analysis complete (id: {analysis.id})")
    return True


def do_generate_html(video_id):
    print(f"\n--- Generating HTML report ---")
    html_path = generate_html(video_id)
    return html_path


def do_generate_pdf(html_path):
    print(f"\n--- Generating PDF report ---")
    pdf_path = generate_pdf(html_path)
    return pdf_path


def run(video_id, mode, provider):
    connect_db()

    try:
        if mode == "fetch":
            youtube = build("youtube", "v3", developerKey=os.getenv("YOUTUBE_API_KEY"))
            do_fetch(video_id, youtube)

        elif mode == "analyze":
            do_analyze(video_id, provider)

        elif mode == "generate_html":
            do_generate_html(video_id)

        elif mode == "generate_pdf":
            # Generate HTML first then convert to PDF
            html_path = do_generate_html(video_id)
            do_generate_pdf(html_path)

        elif mode == "report":
            # Analyze + generate HTML + PDF
            success = do_analyze(video_id, provider)
            if success:
                html_path = do_generate_html(video_id)
                do_generate_pdf(html_path)

        elif mode == "run_all":
            # Fetch + analyze + generate HTML + PDF
            youtube = build("youtube", "v3", developerKey=os.getenv("YOUTUBE_API_KEY"))
            video = do_fetch(video_id, youtube)
            if video:
                success = do_analyze(video_id, provider)
                if success:
                    # do_generate_html(video_id)
                    html_path = do_generate_html(video_id)
                    do_generate_pdf(html_path)

    finally:
        disconnect_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="YouTube Comment Analyzer",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--video_id", required=True, help="YouTube video ID")

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--fetch",         action="store_true", help="Fetch channel, video, and comments from YouTube API")
    mode_group.add_argument("--analyze",       action="store_true", help="Run AI analysis on stored comments")
    mode_group.add_argument("--generate_html", action="store_true", help="Generate HTML report from existing analysis")
    mode_group.add_argument("--generate_pdf",  action="store_true", help="Generate HTML + PDF report from existing analysis")
    mode_group.add_argument("--report",        action="store_true", help="Run AI analysis + generate HTML + PDF")
    mode_group.add_argument("--run_all",       action="store_true", help="Fetch + analyze + generate HTML + PDF")

    parser.add_argument(
        "--provider",
        default=DEFAULT_PROVIDER,
        choices=["gemini", "claude", "openai"],
        help=f"AI provider to use (default: {DEFAULT_PROVIDER})"
    )

    args = parser.parse_args()

    if args.fetch:             mode = "fetch"
    elif args.analyze:         mode = "analyze"
    elif args.generate_html:   mode = "generate_html"
    elif args.generate_pdf:    mode = "generate_pdf"
    elif args.report:          mode = "report"
    else:                      mode = "run_all"

    run(args.video_id, mode, args.provider)