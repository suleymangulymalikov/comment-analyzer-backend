"""
Generates a clean light-theme HTML report from an Analysis document.
"""
import os
import re
from db.models import Analysis, Video, Channel


def slugify(text, max_words=4):
    """Convert text to a clean filename-safe slug using first N words."""
    words = re.sub(r'[^\w\s]', '', text.lower()).split()[:max_words]
    return "_".join(words)


def generate_html(video_id, output_path=None):
    """
    Fetches the latest analysis for a video and generates an HTML report.
    Auto-generates a readable filename if output_path not provided.
    Returns the output path.
    """

    analysis = Analysis.objects(video_id=video_id).order_by("-created_at").first()
    if not analysis:
        raise ValueError(f"No analysis found for video_id: {video_id}")

    video = Video.objects(video_id=video_id).first()
    channel = Channel.objects(channel_id=analysis.channel_id).first()

    video_title = video.title if video else video_id
    channel_name = channel.name if channel else "Unknown Channel"
    real_comment_count = video.stats.comment_count if video and video.stats else 0

    # --- Auto-generate readable filename ---
    if not output_path:
        os.makedirs("reports", exist_ok=True)
        date_str = analysis.created_at.strftime("%Y-%m-%d")
        channel_slug = slugify(channel_name, max_words=2)
        title_slug = slugify(video_title, max_words=4)
        output_path = f"reports/{channel_slug}_{title_slug}_{date_str}.html"

    stats = analysis.stats or {}
    insights = analysis.insights or {}
    sentiment = stats.get("sentiment_breakdown", {})
    top_liked = stats.get("top_liked_comments", [])

    complaints = insights.get("complaints", [])
    confusion = insights.get("confusion_points", [])
    requests = insights.get("content_requests", [])
    struggles = insights.get("audience_struggles", [])
    gaps = insights.get("content_gaps", [])
    ideas = insights.get("video_ideas", [])

    pos = sentiment.get("positive", 0)
    neu = sentiment.get("neutral", 0)
    neg = sentiment.get("negative", 0)

    def insight_cards(items):
        if not items:
            return "<p class='empty'>No findings for this category.</p>"
        html = ""
        for item in items:
            html += f"""
            <div class="card">
                <div class="card-title">{item.get('title', '')}</div>
                <p class="card-desc">{item.get('description', '')}</p>
            </div>"""
        return html

    def idea_cards(items):
        if not items:
            return "<p class='empty'>No ideas found.</p>"
        html = ""
        for i, item in enumerate(items, 1):
            html += f"""
            <div class="idea-card">
                <div class="idea-number">{i:02d}</div>
                <div class="idea-content">
                    <div class="idea-title">{item.get('title', '')}</div>
                    <div class="idea-reason">{item.get('reason', '')}</div>
                </div>
            </div>"""
        return html

    def top_comments_html(items):
        if not items:
            return "<p class='empty'>No data.</p>"
        html = ""
        for item in items:
            html += f"""
            <div class="comment-item">
                <span class="comment-likes">♥ {item.get('likes', 0)}</span>
                <span class="comment-text">{item.get('text', '')}</span>
            </div>"""
        return html

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Comment Analysis — {channel_name}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=DM+Sans:wght@300;400;500;600&display=swap');

  :root {{
    --bg: #f7f5f0;
    --surface: #ffffff;
    --border: #e2ddd6;
    --accent: #b5873a;
    --accent-light: #f5ecd8;
    --text: #1a1814;
    --text-muted: #7a7570;
    --red: #c0392b;
    --green: #27714a;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'DM Sans', sans-serif;
    font-weight: 300;
    line-height: 1.6;
  }}

  .header {{
    background: var(--text);
    padding: 48px 64px;
    position: relative;
    overflow: hidden;
  }}

  .header::before {{
    content: '';
    position: absolute;
    top: -60px; right: -60px;
    width: 250px; height: 250px;
    background: radial-gradient(circle, rgba(181,135,58,0.15) 0%, transparent 70%);
    border-radius: 50%;
  }}

  .header-label {{
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: var(--accent);
    margin-bottom: 16px;
  }}

  .header-channel {{
    font-family: 'Playfair Display', serif;
    font-size: 38px;
    color: #ffffff;
    margin-bottom: 8px;
    line-height: 1.2;
  }}

  .header-video {{
    font-size: 15px;
    color: rgba(255,255,255,0.5);
    max-width: 700px;
    margin-bottom: 36px;
  }}

  .header-meta {{
    display: flex;
    gap: 40px;
    align-items: center;
  }}

  .meta-item {{
    display: flex;
    flex-direction: column;
    gap: 4px;
  }}

  .meta-label {{
    font-size: 11px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: rgba(255,255,255,0.4);
  }}

  .meta-value {{
    font-size: 28px;
    font-weight: 600;
    color: var(--accent);
  }}

  .meta-divider {{
    width: 1px;
    height: 40px;
    background: rgba(255,255,255,0.1);
  }}

  .main {{
    max-width: 900px;
    margin: 0 auto;
    padding: 48px 64px;
  }}

  .summary-block {{
    background: var(--surface);
    border-left: 3px solid var(--accent);
    padding: 24px 28px;
    margin-bottom: 48px;
    border-radius: 0 8px 8px 0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }}

  .summary-block p {{
    font-size: 15px;
    line-height: 1.8;
    color: var(--text);
  }}

  .sentiment-bar {{
    display: flex;
    height: 8px;
    border-radius: 4px;
    overflow: hidden;
    margin: 16px 0;
    gap: 2px;
  }}

  .sentiment-pos {{ background: var(--green); flex: {pos}; }}
  .sentiment-neu {{ background: #c8c4bd; flex: {neu}; }}
  .sentiment-neg {{ background: var(--red); flex: {neg}; }}

  .sentiment-legend {{
    display: flex;
    gap: 24px;
  }}

  .legend-item {{
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--text-muted);
  }}

  .legend-dot {{
    width: 8px; height: 8px;
    border-radius: 50%;
  }}

  .section {{
    margin-bottom: 48px;
  }}

  .section-header {{
    display: flex;
    align-items: baseline;
    gap: 12px;
    margin-bottom: 20px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--border);
  }}

  .section-title {{
    font-family: 'Playfair Display', serif;
    font-size: 22px;
    color: var(--text);
  }}

  .section-count {{
    font-size: 12px;
    color: var(--text-muted);
    letter-spacing: 1px;
    text-transform: uppercase;
  }}

  .card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 18px 20px;
    margin-bottom: 10px;
    transition: border-color 0.2s, box-shadow 0.2s;
  }}

  .card:hover {{
    border-color: var(--accent);
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  }}

  .card-title {{
    font-weight: 600;
    font-size: 14px;
    color: var(--text);
    margin-bottom: 8px;
  }}

  .card-desc {{
    font-size: 13px;
    color: var(--text-muted);
    line-height: 1.6;
  }}

  .idea-card {{
    display: flex;
    gap: 20px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 10px;
    transition: border-color 0.2s, box-shadow 0.2s;
  }}

  .idea-card:hover {{
    border-color: var(--accent);
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  }}

  .idea-number {{
    font-family: 'Playfair Display', serif;
    font-size: 32px;
    color: var(--border);
    line-height: 1;
    flex-shrink: 0;
    min-width: 36px;
  }}

  .idea-title {{
    font-weight: 600;
    font-size: 15px;
    color: var(--text);
    margin-bottom: 8px;
  }}

  .idea-reason {{
    font-size: 13px;
    color: var(--text-muted);
    line-height: 1.6;
  }}

  .comment-item {{
    display: flex;
    gap: 14px;
    padding: 14px 0;
    border-bottom: 1px solid var(--border);
    align-items: flex-start;
  }}

  .comment-item:last-child {{ border-bottom: none; }}

  .comment-likes {{
    font-size: 12px;
    font-weight: 600;
    color: var(--accent);
    white-space: nowrap;
    min-width: 60px;
    padding-top: 2px;
  }}

  .comment-text {{
    font-size: 13px;
    color: var(--text-muted);
    line-height: 1.6;
  }}

  .section-label {{
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--accent);
    margin-bottom: 6px;
  }}

  .empty {{
    font-size: 13px;
    color: var(--text-muted);
    font-style: italic;
    padding: 12px 0;
  }}
</style>
</head>
<body>

<div class="header">
  <div class="header-label">YouTube Comment Analysis</div>
  <div class="header-channel">{channel_name}</div>
  <div class="header-video">{video_title}</div>
  <div class="header-meta">
    <div class="meta-item">
      <span class="meta-label">Comments on Video</span>
      <span class="meta-value">~{real_comment_count:,}</span>
    </div>
    <div class="meta-divider"></div>
    <div class="meta-item">
      <span class="meta-label">Sentiment</span>
      <span class="meta-value" style="font-size:18px; color: #5cb88a">{pos}% Positive</span>
    </div>
    <div class="meta-divider"></div>
    <div class="meta-item">
      <span class="meta-label">Video Ideas Generated</span>
      <span class="meta-value">{len(ideas)}</span>
    </div>
  </div>
</div>

<div class="main">

  <div class="section">
    <div class="section-label">Overview</div>
    <div class="summary-block">
      <p>{analysis.summary}</p>
    </div>
  </div>

  <div class="section">
    <div class="section-header">
      <span class="section-title">Sentiment Breakdown</span>
      <span class="section-count">~{real_comment_count:,} comments</span>
    </div>
    <div class="sentiment-bar">
      <div class="sentiment-pos"></div>
      <div class="sentiment-neu"></div>
      <div class="sentiment-neg"></div>
    </div>
    <div class="sentiment-legend">
      <div class="legend-item">
        <div class="legend-dot" style="background: var(--green)"></div>
        Positive {pos}%
      </div>
      <div class="legend-item">
        <div class="legend-dot" style="background: #c8c4bd"></div>
        Neutral {neu}%
      </div>
      <div class="legend-item">
        <div class="legend-dot" style="background: var(--red)"></div>
        Negative {neg}%
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-header">
      <span class="section-title">Top Liked Comments</span>
      <span class="section-count">Top {len(top_liked)}</span>
    </div>
    {top_comments_html(top_liked)}
  </div>

  <div class="section">
    <div class="section-header">
      <span class="section-title">Complaints</span>
      <span class="section-count">{len(complaints)} found</span>
    </div>
    {insight_cards(complaints)}
  </div>

  <div class="section">
    <div class="section-header">
      <span class="section-title">Confusion Points</span>
      <span class="section-count">{len(confusion)} found</span>
    </div>
    {insight_cards(confusion)}
  </div>

  <div class="section">
    <div class="section-header">
      <span class="section-title">Content Requests</span>
      <span class="section-count">{len(requests)} found</span>
    </div>
    {insight_cards(requests)}
  </div>

  <div class="section">
    <div class="section-header">
      <span class="section-title">Audience Struggles</span>
      <span class="section-count">{len(struggles)} found</span>
    </div>
    {insight_cards(struggles)}
  </div>

  <div class="section">
    <div class="section-header">
      <span class="section-title">Content Gaps</span>
      <span class="section-count">{len(gaps)} found</span>
    </div>
    {insight_cards(gaps)}
  </div>

  <div class="section">
    <div class="section-header">
      <span class="section-title">Video Ideas</span>
      <span class="section-count">{len(ideas)} ideas</span>
    </div>
    {idea_cards(ideas)}
  </div>

</div>

</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  ✓ HTML report saved to {output_path}")

    return output_path