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

**HTTP API:**
```
uvicorn app.main:app --reload
```

**CLI:**
```
python cli.py --video_id <ID> --fetch
python cli.py --video_id <ID> --analyze
python cli.py --video_id <ID> --run_all --provider gemini
```

## Architecture

All application code lives under `app/`. The pipeline has two phases: **fetch → analyze**.

**`app/fetchers/`**: Hits YouTube Data API v3 to pull video metadata, channel info, and all comments including replies. For threads where `totalReplyCount > len(inline_replies)`, it makes additional paginated `comments().list` calls to fetch all replies. Stores everything flat in MongoDB via MongoEngine. Comments re-fetch if `comments_fetched_at` is older than 24 hours (`COMMENTS_STALE_AFTER_HOURS` in `app/config.py`).

**`app/services/analyzer.py`**: Loads ALL comments (top-level and replies) from MongoDB ordered by `like_count` descending, builds a prompt, calls the configured AI provider, parses the JSON response, and saves an `Analysis` document per user. The active prompt is `CURRENT_PROMPT_VERSION` in `app/prompts/__init__.py` — increment this when changing the prompt so old analyses remain comparable.

**`app/ai/`** (`gemini.py`, `claude.py`, `openai.py`): Each exposes a single `analyze(comments, prompt) -> (result_dict, model_name)` function. `app/config.py` maps provider names to modules. Gemini (`gemini-3.1-flash-lite`) is the only fully implemented provider; claude and openai raise `NotImplementedError`.

**`app/db/`**: MongoEngine ODM. `connect_db()` / `disconnect_db()` must wrap any script that touches the DB. In the FastAPI app this is handled in the lifespan handler. Collections: `users`, `channels`, `videos`, `comments`, `analyses`.

**`app/routers/`**: FastAPI routers split by concern:
- `users.py` — `POST /users` (create-or-find user by `user_id` + `email`)
- `analyze.py` — `POST /analyze` (fetch + analyze, requires `x-user-id` header)
- `analyses.py` — `GET /analyses`, `GET /analyses/{id}` (history, requires `x-user-id` header)

## Key Data Flow Detail

`fetch_comments` sets `Video.comments_fetched = True` only after all comments are stored. `run_analysis` queries ALL `Comment` documents for the video (top-level and replies), ordered by `like_count` descending. Results are cached per `(video_id, user_id, provider, prompt_version)` — pass `force=true` in the request body to bypass the cache.

## Prompt Versioning

Prompts live in `app/prompts/__init__.py` as a dict keyed by version int. `CURRENT_PROMPT_VERSION = 5` is the active one. Each `Analysis` document stores `prompt_version` so results can be compared across prompt iterations without re-fetching.
