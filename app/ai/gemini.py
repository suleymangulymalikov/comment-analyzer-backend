import os
import json
import re
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

MODEL = "gemini-3.1-flash-lite"


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
            temperature=0.4
        )
    )

    cleaned = clean_json_response(response.text)

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}")
        print(f"  Raw response (first 500 chars): {response.text[:500]}")
        raise

    return result, MODEL
