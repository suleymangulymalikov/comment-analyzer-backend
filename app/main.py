import os
import hmac
import logging
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from dotenv import load_dotenv

from app.db.connection import connect_db
from app.routers import users, analyze, analyses, payments, credits
from app.config import INTERNAL_API_SECRET

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    connect_db()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "x-user-id"],
)


class InternalAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/payments/webhook":
            return await call_next(request)

        if INTERNAL_API_SECRET:
            auth = request.headers.get("Authorization", "")
            expected = f"Bearer {INTERNAL_API_SECRET}"
            # Timing-safe comparison to prevent secret enumeration via timing attacks
            if not hmac.compare_digest(auth.encode(), expected.encode()):
                return JSONResponse({"detail": "Forbidden"}, status_code=403)

        return await call_next(request)


app.add_middleware(InternalAuthMiddleware)

app.include_router(users.router)
app.include_router(analyze.router)
app.include_router(analyses.router)
app.include_router(payments.router)
app.include_router(credits.router)
