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

**`app/fetchers/`**: Hits YouTube Data API v3 to pull video metadata, channel info, and all comments including replies. For threads where `totalReplyCount > len(inline_replies)`, it makes additional paginated `comments().list` calls to fetch all replies. Stores everything flat in MongoDB via MongoEngine. Comments re-fetch if `comments_fetched_at` is older than 24 hours (`COMMENTS_STALE_AFTER_HOURS` in `app/config.py`).

**`app/services/analyzer.py`**: Loads ALL comments (top-level and replies) from MongoDB ordered by `like_count` descending, builds a prompt, calls the configured AI provider, parses the JSON response, and saves an `Analysis` document per user. The active prompt is `CURRENT_PROMPT_VERSION` in `app/prompts/__init__.py` — increment this when changing the prompt so old analyses remain comparable.

**`app/ai/`** (`gemini.py`, `claude.py`, `openai.py`): Each exposes a single `analyze(comments, prompt) -> (result_dict, model_name)` function. `app/config.py` maps provider names to modules. Gemini (`gemini-3.1-flash-lite`) is the only fully implemented provider; claude and openai raise `NotImplementedError`.

**`app/db/`**: MongoEngine ODM. `connect_db()` / `disconnect_db()` must wrap any script that touches the DB. In the FastAPI app this is handled in the lifespan handler. Collections: `users`, `channels`, `videos`, `comments`, `analyses`, `credit_transactions`.

**`app/routers/`**: FastAPI routers split by concern:
- `users.py` — `POST /users` (create-or-find user by `user_id` + `email`)
- `analyze.py` — `POST /analyze` (fetch + analyze, requires `x-user-id` header)
- `analyses.py` — `GET /analyses`, `GET /analyses/{id}` (history, requires `x-user-id` header)
- `credits.py` — `GET /credits` (balance + last 10 transactions, requires `x-user-id` header)
- `payments.py` — `POST /payments/checkout` (create Stripe session), `POST /payments/webhook` (Stripe events)
- `admin.py` — `POST /admin/credits` (manually add credits, protected by `x-admin-key` header)

## Credit System

Every user starts with 0 credits. Credits are spent when an analysis runs. Cost is based on the video's comment count (from `video.stats.comment_count`, available after `fetch_video` before the expensive `fetch_comments`):

| Comments | Credits |
|---|---|
| 0 – 500 | 1 |
| 501 – 2,000 | 2 |
| 2,001 – 10,000 | 3 |
| 10,001+ | 5 |

The credit check happens between `fetch_video` and `fetch_comments` so no YouTube API quota is burned if the user has insufficient credits. `credits_for_count()` lives in `app/config.py`.

Cached analyses (same video/user/provider/prompt_version) do NOT cost credits — only new analyses deduct.

## Pricing

| Option | Price | Credits |
|---|---|---|
| Standard Pack (one-time) | $7.99 | 10 |
| Starter (monthly) | $9.99/mo | 15/mo |
| Pro (monthly) | $19.99/mo | 40/mo |
| Business | Custom / contact us | Manual via admin endpoint |

## Stripe Webhook Flow

- `checkout.session.completed` → adds credits for one-time pack purchases
- `invoice.payment_succeeded` → adds monthly credits for subscription renewals

Subscription metadata (`user_id`, `price_key`) must be on the Stripe Subscription object (set via `subscription_data.metadata` in the checkout session creation) so the invoice webhook can identify the user.

## Key Data Flow Detail

`fetch_comments` sets `Video.comments_fetched = True` only after all comments are stored. `run_analysis` queries ALL `Comment` documents for the video (top-level and replies), ordered by `like_count` descending. Results are cached per `(video_id, user_id, provider, prompt_version)` — pass `force=true` in the request body to bypass the cache.

## Prompt Versioning

Prompts live in `app/prompts/__init__.py` as a dict keyed by version int. `CURRENT_PROMPT_VERSION = 5` is the active one. Each `Analysis` document stores `prompt_version` so results can be compared across prompt iterations without re-fetching.

---

## Next Steps Before Going Live

### 1. Stripe Dashboard Setup
- Create 3 products in [Stripe Dashboard](https://dashboard.stripe.com/products):
  - **Standard Pack** — one-time, $7.99
  - **Starter** — recurring monthly, $9.99
  - **Pro** — recurring monthly, $19.99
- Copy the Price IDs into `.env` (`STRIPE_PRICE_PACK_STANDARD`, etc.)
- Add a webhook endpoint pointing to `https://yourdomain.com/payments/webhook`
- Subscribe to events: `checkout.session.completed`, `invoice.payment_succeeded`
- Copy the webhook signing secret into `.env` as `STRIPE_WEBHOOK_SECRET`

### 2. Test Stripe Locally
```
stripe listen --forward-to localhost:8000/payments/webhook
```
Complete a test checkout and verify credits are added to the user in MongoDB.

### 3. Deploy the Backend
Choose a hosting platform (Railway, Render, Fly.io, etc.) and set all `.env` variables as environment secrets.

### 4. Frontend Integration
- Call `POST /payments/checkout` with `price_key` + `success_url` + `cancel_url` to get a `checkout_url`, then redirect the user to it
- Show credit balance from `GET /credits`
- Handle `402` responses from `POST /analyze` (redirect to pricing page)
- Add a "Contact us" button for the Business tier (no backend needed)
