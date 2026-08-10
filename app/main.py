import re
from contextlib import asynccontextmanager, suppress
from typing import AsyncGenerator
from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import run_migrations
from app.api.v1 import auth
from app.api.v1 import transcription
from app.api.v1 import setting
from app.api.v1 import user_data
from app.api.v1 import contact
from app.core.middleware import CountryRestrictionMiddleware

from app.models import user
from app.models import meeting
from app.models import email_verification_token
from app.models import password_reset_token
from app.api.v1 import payments
from app.api.v1 import meetings
from app.api.v1 import admin_management
from app.api.v1 import admin_dashboard
from app.api.v1 import pricing
from app.core.scheduler import run_scheduler
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    env = (settings.APP_ENV or "development").lower()
    if env in ("development", "dev", "local"):
        try:
            await asyncio.to_thread(run_migrations)
        except Exception as exc:
            print(f"CRITICAL: Application startup aborted due to migration error: {exc}")
            raise exc
    else:
        print(f"INFO:     Environment '{settings.APP_ENV}' detected. Skipping automatic startup migrations.")

    scheduler_task = asyncio.create_task(run_scheduler())
    print("INFO:     BriefRoom Backend API startup complete. Server is ready for requests.")
    try:
        yield
    finally:
        scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler_task


app = FastAPI(
    title="BriefRoom API",
    version="1.0.0",
    description="AI Meeting Assistant API",
    lifespan=lifespan,
)

@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok", "message": "BriefRoom backend is running"}

allowed_origins = {
    settings.FRONTEND_URL,
    "https://brief-room-web-with-closed-source-m-xi.vercel.app",
    "https://brief-room-web-with-closed-source-my-app-ai86-ojeyvjz7b.vercel.app",
    "https://brief-room-web-with-closed-s-git-e5cbff-adnansaeed-85s-projects.vercel.app",
    "https://adnansaeed-briefroom.hf.space",
    "http://localhost:3000",
    "https://localhost:3000",
}

app.add_middleware(CountryRestrictionMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(allowed_origins),
    allow_origin_regex=r"https://.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

@app.options("/{rest_of_path:path}")
async def preflight_handler(request: Request, rest_of_path: str) -> Response:
    origin = request.headers.get("origin", "")
    is_allowed_origin = bool(origin) and (origin in allowed_origins or re.match(r"https://.*\.vercel\.app$", origin))

    headers = {
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": request.headers.get("access-control-request-headers", "*"),
        "Access-Control-Allow-Credentials": "true",
    }

    if is_allowed_origin:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Vary"] = "Origin, Access-Control-Request-Headers"
    else:
        headers["Access-Control-Allow-Origin"] = "*"

    return Response(status_code=200, headers=headers)

import os
from fastapi.staticfiles import StaticFiles

from app.api.v1 import blogs

uploads_dir = os.path.join(os.getcwd(), "uploads")
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(transcription.router, prefix="/api/v1/transcription", tags=["transcription"])
app.include_router(setting.router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(admin_management.router, prefix="/api/v1/admin", tags=["admin-management"])
app.include_router(admin_dashboard.router, prefix="/api/v1/admin", tags=["admin-dashboard"])
app.include_router(pricing.public_router, prefix="/api/v1/pricing", tags=["pricing"])
app.include_router(pricing.admin_router, prefix="/api/v1/admin/pricings", tags=["admin-pricing"])
app.include_router(user_data.router, prefix="/api/v1/user-data", tags=["user-data"])
app.include_router(contact.router, prefix="/api/v1", tags=["contact"])
app.include_router(payments.router, prefix="/api/v1/payments", tags=["payments"])
app.include_router(meetings.router, prefix="/api/v1/meetings", tags=["meetings"])
app.include_router(blogs.router, prefix="/api/v1", tags=["blogs"])


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "version": "1.0.0"}
