import os
import json
import logging
import re
from google import genai
from google.genai import types
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

MODEL = "gemini-3.1-flash-lite"

_INSIGHT_ITEM = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "title":       types.Schema(type=types.Type.STRING),
        "description": types.Schema(type=types.Type.STRING),
    },
    required=["title", "description"],
)

RESPONSE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    required=["summary", "stats", "insights"],
    properties={
        "summary": types.Schema(type=types.Type.STRING),
        "stats": types.Schema(
            type=types.Type.OBJECT,
            required=["total_comments_analyzed", "top_liked_comments", "sentiment_breakdown"],
            properties={
                "total_comments_analyzed": types.Schema(type=types.Type.INTEGER),
                "top_liked_comments": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(
                        type=types.Type.OBJECT,
                        required=["text", "likes"],
                        properties={
                            "text":  types.Schema(type=types.Type.STRING),
                            "likes": types.Schema(type=types.Type.INTEGER),
                        },
                    ),
                ),
                "sentiment_breakdown": types.Schema(
                    type=types.Type.OBJECT,
                    required=["positive", "neutral", "negative"],
                    properties={
                        "positive": types.Schema(type=types.Type.INTEGER),
                        "neutral":  types.Schema(type=types.Type.INTEGER),
                        "negative": types.Schema(type=types.Type.INTEGER),
                    },
                ),
            },
        ),
        "insights": types.Schema(
            type=types.Type.OBJECT,
            required=["complaints", "confusion_points", "content_requests",
                      "audience_struggles", "content_gaps", "video_ideas"],
            properties={
                "complaints":        types.Schema(type=types.Type.ARRAY, items=_INSIGHT_ITEM),
                "confusion_points":  types.Schema(type=types.Type.ARRAY, items=_INSIGHT_ITEM),
                "content_requests":  types.Schema(type=types.Type.ARRAY, items=_INSIGHT_ITEM),
                "audience_struggles": types.Schema(type=types.Type.ARRAY, items=_INSIGHT_ITEM),
                "content_gaps":      types.Schema(type=types.Type.ARRAY, items=_INSIGHT_ITEM),
                "video_ideas": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(
                        type=types.Type.OBJECT,
                        required=["title", "reason"],
                        properties={
                            "title":  types.Schema(type=types.Type.STRING),
                            "reason": types.Schema(type=types.Type.STRING),
                        },
                    ),
                ),
            },
        ),
    },
)


def clean_json_response(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()
    text = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', text)
    return text


def analyze(comments, prompt):
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    full_prompt = f"{prompt}\n\nComments:\n{json.dumps(comments, ensure_ascii=False)}"

    response = client.models.generate_content(
        model=MODEL,
        contents=full_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
            temperature=0.4
        )
    )

    cleaned = clean_json_response(response.text)

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error("gemini_json_parse_error error=%s raw_response=%.500s", e, response.text)
        raise

    return result, MODEL
