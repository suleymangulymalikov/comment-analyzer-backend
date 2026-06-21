# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment Setup

Requires a `.env` file with:
```
YOUTUBE_API_KEY=...
MONGODB_URI=...
GEMINI_API_KEY=...

# Stripe (required for payments)
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Stripe Price IDs — copy from Stripe dashboard after creating products
STRIPE_PRICE_PACK_STANDARD=price_...   # $7.99 one-time, 10 credits
STRIPE_PRICE_SUB_STARTER=price_...     # $9.99/month, 15 credits
STRIPE_PRICE_SUB_PRO=price_...         # $19.99/month, 40 credits

# Admin endpoint protection
ADMIN_SECRET=some_secret_key

# Shared secret with Next.js backend — every request except /payments/webhook
# must include: Authorization: Bearer <INTERNAL_API_SECRET>
# Leave unset in local dev to skip the check.
INTERNAL_API_SECRET=<generate with: openssl rand -hex 32>
```

Use the `.venv` virtual environment — all dependencies are installed there:
```
.venv\Scripts\pip install -r requirements.txt
```

## Running the App

**HTTP API:**
```
.venv\Scripts\uvicorn app.main:app --reload
```

**CLI:**
```
.venv\Scripts\python cli.py --video_id <ID> --fetch
.venv\Scripts\python cli.py --video_id <ID> --analyze
.venv\Scripts\python cli.py --video_id <ID> --run_all --provider gemini
```

## Architecture

All application code lives under `app/`. The pipeline has two phases: **fetch → analyze**.

**`app/fetchers/`**: Hits YouTube Data API v3 to pull video metadata, channel info, and up to **300 comments** (by relevance order) including replies. Capped at `MAX_COMMENTS = 300` in `fetchers/comments.py`. For threads where `totalReplyCount > len(inline_replies)`, it makes additional paginated `comments().list` calls to fetch replies (still subject to the 300 cap). Stores everything flat in MongoDB via MongoEngine. Comments re-fetch if `comments_fetched_at` is older than 24 hours (`COMMENTS_STALE_AFTER_HOURS` in `app/config.py`). After fetching, `Video.comments_stored_count` is updated with the exact count stored.

**`app/services/analyzer.py`**: Loads all stored comments for the video from MongoDB ordered by `like_count` descending, builds a prompt, calls the configured AI provider, **validates the response with Pydantic** (`AnalysisResult` model), and saves an `Analysis` document per user. The active prompt is `CURRENT_PROMPT_VERSION` in `app/prompts/__init__.py` — increment this when changing the prompt so old analyses remain comparable.

**`app/ai/`** (`gemini.py`, `claude.py`, `openai.py`): Each exposes a single `analyze(comments, prompt) -> (result_dict, model_name)` function. `app/config.py` maps provider names to modules. Gemini (`gemini-3.1-flash-lite`) is the only fully implemented provider; claude and openai raise `NotImplementedError`. Gemini uses a typed `RESPONSE_SCHEMA` with `response_mime_type="application/json"` to enforce structured output from the model.

**`app/db/`**: MongoEngine ODM. `connect_db()` / `disconnect_db()` must wrap any script that touches the DB. In the FastAPI app this is handled in the lifespan handler. Collections: `users`, `channels`, `videos`, `comments`, `analyses`, `credit_transactions`.

**`app/routers/`**: FastAPI routers split by concern:
- `users.py` — `POST /users` (create-or-find user by `user_id` + `email`)
- `analyze.py` — `POST /analyze` (pre-checks sync, heavy work async; returns `{"job_id": "..."}` immediately); `GET /analyze/status/{job_id}` (poll for result)
- `analyses.py` — `GET /analyses?limit=20&skip=0`, `GET /analyses/{id}` (history, requires `x-user-id` header; limit capped at 50)
- `credits.py` — `GET /credits` (balance + last 10 transactions, requires `x-user-id` header)
- `payments.py` — `POST /payments/checkout` (create Stripe session), `POST /payments/webhook` (Stripe events)

## Credit System

Every user starts with 0 credits. Credits are spent when an analysis runs. Cost is **flat 1 credit per analysis** regardless of comment count — `credits_for_count()` in `app/config.py` always returns `1`.

The credit check happens between `fetch_video` and `fetch_comments` (using `video.stats.comment_count` on fresh fetches, or `video.comments_stored_count` on cache hits) so no YouTube API quota is burned if the user has insufficient credits.

Cached analyses (same video/user/provider/prompt_version) do NOT cost credits — only new analyses deduct.

## Pricing

| Option | Price | Credits |
|---|---|---|
| Standard Pack (one-time) | $7.99 | 10 |
| Business | Custom / contact us | Manual via admin endpoint |

## Stripe Webhook Flow

- `checkout.session.completed` → adds credits (`pack_standard` only; all purchases are one-time)

Only `checkout.session.completed` is handled. Subscription products (`sub_starter`, `sub_pro`) and `invoice.payment_succeeded` have been removed.

## Backend Security

All requests (except `POST /payments/webhook`) must include:
```
Authorization: Bearer <INTERNAL_API_SECRET>
```
This is enforced by `InternalAuthMiddleware` in `app/main.py` using `hmac.compare_digest()` (timing-safe). If the header is missing or wrong the backend returns `403`. The check is skipped when `INTERNAL_API_SECRET` is not set, so local dev works without it.

`/payments/webhook` is exempt because Stripe calls it directly — it is protected instead by Stripe's own signature verification (`STRIPE_WEBHOOK_SECRET`).

The Next.js server must add this header to every fetch call to the backend. `INTERNAL_API_SECRET` must be a non-`NEXT_PUBLIC_` env var so it is never sent to the browser.

**CORS** is restricted to `GET`, `POST`, `OPTIONS` methods and only the three headers the API actually uses (`Authorization`, `Content-Type`, `x-user-id`). Allowed origins are driven by `ALLOWED_ORIGINS`.

**`success_url` / `cancel_url`** in `POST /payments/checkout` are validated against the `ALLOWED_ORIGINS` whitelist to prevent open-redirect abuse.

## Key Data Flow Detail

`fetch_comments` sets `Video.comments_fetched = True` and `Video.comments_stored_count` only after all comments are stored (capped at 300). `run_analysis` queries all stored `Comment` documents for the video, ordered by `like_count` descending, then validates the AI response with Pydantic before saving. Results are cached per `(video_id, user_id, provider, prompt_version)` — pass `force=true` in the request body to bypass the cache.

**Async job flow (`analyze.py`):**
`POST /analyze` runs pre-checks synchronously (auth, video ID parsing, `fetch_video` for metadata, credit check), then spawns a `threading.Thread` for the slow work (comment fetch + AI analysis) and returns `{"job_id": "<uuid>"}` immediately. Job state is kept in the module-level `_jobs` dict (`{status, result, error, user_id}`; status values: `pending | running | done | failed`). A `threading.Semaphore(3)` caps concurrent jobs — returns 503 if all slots are taken. The semaphore is always released in the thread's `finally` block. `GET /analyze/status/{job_id}` returns the current state and **deletes the job from `_jobs`** on `done`/`failed` to prevent unbounded memory growth.

## Prompt Versioning

Prompts live in `app/prompts/__init__.py` as a dict keyed by version int. `CURRENT_PROMPT_VERSION = 5` is the active one. Each `Analysis` document stores `prompt_version` so results can be compared across prompt iterations without re-fetching.

## Deployment

**Platform:** Railway — `https://web-production-47395.up.railway.app`
Auto-deploys on every push to `main`.

**Railway env vars set:**
- `YOUTUBE_API_KEY`, `MONGODB_URI`, `GEMINI_API_KEY`
- `INTERNAL_API_SECRET`, `ADMIN_SECRET`
- `ALLOWED_ORIGINS=https://comment-analyzer-frontend-murex.vercel.app`

**MongoDB Atlas:** Network Access set to `0.0.0.0/0` (allow all IPs) — required because Railway has dynamic IPs.

---

## TODO — Must complete before launch

### 1. Stripe setup (NOT done yet)
- [ ] Create 3 products in [Stripe Dashboard](https://dashboard.stripe.com/products):
  - **Standard Pack** — one-time, $7.99
  - **Starter** — recurring monthly, $9.99/mo
  - **Pro** — recurring monthly, $19.99/mo
- [ ] Copy the 3 Price IDs into Railway env vars: `STRIPE_PRICE_PACK_STANDARD`, `STRIPE_PRICE_SUB_STARTER`, `STRIPE_PRICE_SUB_PRO`
- [ ] Add webhook in Stripe dashboard → `https://web-production-47395.up.railway.app/payments/webhook`
- [ ] Subscribe to: `checkout.session.completed`, `invoice.payment_succeeded`
- [ ] Copy webhook signing secret into Railway env var: `STRIPE_WEBHOOK_SECRET`
- [ ] Copy Stripe secret key into Railway env var: `STRIPE_SECRET_KEY`
- [ ] Test with `stripe listen --forward-to localhost:8000/payments/webhook` before going live

### 2. Frontend integration (NOT done yet)
- [ ] Add `BACKEND_URL` and `INTERNAL_API_SECRET` to Next.js env vars
- [ ] Add `Authorization: Bearer ${process.env.INTERNAL_API_SECRET}` to every server-side fetch to backend
- [ ] Build pricing page (call `POST /payments/checkout`, redirect to `checkout_url`)
- [ ] Show credit balance from `GET /credits`
- [ ] Handle `402` from `POST /analyze` → redirect to pricing page
- [ ] Add "Contact us" button for Business tier

### 3. Performance & reliability (before scaling)
- [ ] **Frontend timeout** — Vercel free tier times out at 10s. Add `export const maxDuration = 60` to the Next.js `/api/analyze` route (requires Vercel Pro), or restructure to async (submit → poll)
- [ ] **Add structured logging to backend** — currently only print statements. Add request ID, user ID, video ID, duration, comment count to every log line so failures are easy to trace
- [ ] **Concurrency under load** — multiple users hitting `/analyze` simultaneously each burn YouTube API quota in parallel. If quota runs out (10,000 units/day free), all fetches fail. Monitor quota usage in Google Cloud Console and consider adding a per-user rate limit
- [ ] **Railway single instance** — currently 1 replica. Under real load (10+ concurrent users) consider scaling up or adding a queue so heavy analysis jobs don't block each other

### 4. When ready for real users
- [ ] Switch Stripe from test mode to live mode (new keys)
- [ ] Update `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` in Railway with live keys
- [ ] Upgrade Railway to Hobby plan ($5/month) to prevent cold starts
