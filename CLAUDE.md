# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment Setup

Requires a `.env` file with:
```
YOUTUBE_API_KEY=...
MONGODB_URI=...
GEMINI_API_KEY=...
```

Install dependencies:
```
pip install -r requirements.txt
```

## Running the App

**CLI (original entry point):**
```
python main.py --video_id <ID> --fetch
python main.py --video_id <ID> --analyze
python main.py --video_id <ID> --analyze --provider claude
```

**HTTP API:**
```
uvicorn api:app --reload
# POST http://localhost:8000/analyze  {"video_url": "https://youtube.com/watch?v=..."}
```

## Architecture

The pipeline has two phases: **fetch → analyze**.

**Fetch** (`fetchers/`): Hits YouTube Data API v3 to pull video metadata, channel info, and all comments (including paginated replies). Stores everything flat in MongoDB via MongoEngine. `Video.comments_fetched` is the flag that gates the analyze phase.

**Analyze** (`analyzer.py` + `ai/`): Loads top-level comments from MongoDB, builds a prompt, calls the configured AI provider, parses the JSON response, and saves an `Analysis` document. The active prompt is `CURRENT_PROMPT_VERSION` in `helpers/prompts.py` — increment this when changing the prompt so old analyses remain comparable.

**AI providers** (`ai/gemini.py`, `ai/claude.py`, `ai/openai.py`): Each exposes a single `analyze(comments, prompt) -> (result_dict, model_name)` function. `config.py` maps provider names to modules. Gemini (`gemini-2.5-flash-lite`) is the only fully implemented provider; claude and openai raise `NotImplementedError`.

**Database** (`db/`): MongoEngine ODM. `connect_db()` / `disconnect_db()` must wrap any script that touches the DB. In the FastAPI app this is handled in the lifespan handler. Collections: `channels`, `videos`, `comments`, `analyses`.

**HTTP API** (`api.py`): FastAPI app. The single `POST /analyze` endpoint extracts a video ID from any YouTube URL format, runs fetch (skipped if already in DB) and analysis, then returns the `Analysis` fields as JSON. The DB connection is opened once at server startup via the `lifespan` context.

## Key Data Flow Detail

`fetch_comments` sets `Video.comments_fetched = True` only after all comments are stored. `run_analysis` only queries `Comment` documents where `is_reply=False`, ordered by `like_count` descending — replies are stored but never analyzed.

## Prompt Versioning

Prompts live in `helpers/prompts.py` as a dict keyed by version int. `CURRENT_PROMPT_VERSION = 5` is the active one. Each `Analysis` document stores `prompt_version` so results can be compared across prompt iterations without re-fetching.
