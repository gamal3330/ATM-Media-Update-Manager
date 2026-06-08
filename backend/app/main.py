import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .auth import ensure_admin_user
from .config import settings
from .database import SessionLocal, init_db
from .routers import agent, agent_packages, atms, auth, cash, downloads, logs, notifications, packages, users
from .services.notification_service import monitor_notification_delivery_retries, monitor_whatsapp_gateway


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    db = SessionLocal()
    try:
        ensure_admin_user(db)
    finally:
        db.close()
    whatsapp_monitor_task = asyncio.create_task(monitor_whatsapp_gateway(SessionLocal))
    notification_retry_task = asyncio.create_task(monitor_notification_delivery_retries(SessionLocal))
    try:
        yield
    finally:
        for task in (whatsapp_monitor_task, notification_retry_task):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(atms.router)
app.include_router(packages.router)
app.include_router(agent_packages.router)
app.include_router(agent.router)
app.include_router(downloads.router)
app.include_router(logs.router)
app.include_router(users.router)
app.include_router(cash.router)
app.include_router(notifications.router)

frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
