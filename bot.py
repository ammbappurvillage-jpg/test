"""FastAPI webhook entrypoint and web dashboard for Render deployment."""
from __future__ import annotations

import hmac
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from telegram import BotCommand, Update

from config import settings
from handlers import build_application

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# OTTGuild / Mraprguild branding
BOT_BRAND_NAME = "OTTGuild"
TMDB_BRAND_NAME = "Mraprguild"
WELCOME_IMAGE_URL = "https://i.ibb.co/Xk89sYpS/Mraprguild-Secure-Cinematic-Entertainment.png"

# Use absolute paths so startup does not depend on Render's working directory.
if not STATIC_DIR.is_dir():
    raise RuntimeError(f"Static assets directory was not found: {STATIC_DIR}")
if not TEMPLATES_DIR.is_dir():
    raise RuntimeError(f"Templates directory was not found: {TEMPLATES_DIR}")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

application = None
STARTED_AT = time.monotonic()
STARTED_AT_UTC = datetime.now(timezone.utc)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialize Telegram/TMDB clients and register the Render webhook."""
    global application

    settings.validate(require_webhook=True)
    bot_application = build_application()
    application = bot_application
    tmdb_client = bot_application.bot_data["tmdb"]
    initialized = False
    started = False

    try:
        await tmdb_client.start()
        await bot_application.initialize()
        initialized = True
        await bot_application.start()
        started = True

        await bot_application.bot.set_my_commands(
            [
                BotCommand("start", "Start the movie bot"),
                BotCommand("search", "Search movies by name"),
                BotCommand("movie", "Get movie details by name or TMDB ID"),
                BotCommand("popular", "Popular movies"),
                BotCommand("trending", "Trending movies this week"),
                BotCommand("now_playing", "Movies now playing"),
                BotCommand("top_rated", "Top-rated movies"),
                BotCommand("upcoming", "Upcoming movies"),
                BotCommand("help", "Show bot help"),
            ]
        )

        public_url = settings.webhook_url or os.getenv("RENDER_EXTERNAL_URL", "").strip()
        webhook_url = public_url.rstrip("/") + "/telegram/webhook"
        await bot_application.bot.set_webhook(
            url=webhook_url,
            secret_token=settings.webhook_secret or None,
            allowed_updates=Update.ALL_TYPES,
        )
        logger.info("Telegram webhook configured: %s", webhook_url)
        yield
    finally:
        # Keep Telegram's webhook registered during graceful restarts. Deleting it
        # here can race with a replacement Render instance during a rolling deploy.
        if started:
            try:
                await bot_application.stop()
            except Exception:
                logger.exception("Could not stop Telegram application cleanly")
        if initialized:
            try:
                await bot_application.shutdown()
            except Exception:
                logger.exception("Could not shut down Telegram application cleanly")
        try:
            await tmdb_client.close()
        except Exception:
            logger.exception("Could not close TMDB client cleanly")
        application = None


app = FastAPI(
    title=f"{BOT_BRAND_NAME} | {TMDB_BRAND_NAME} Telegram Bot",
    description=f"{BOT_BRAND_NAME} movie bot powered by {TMDB_BRAND_NAME} (TMDB).",
    version="1.0.1",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )


@app.get("/api/dashboard-status")
async def dashboard_status() -> dict[str, object]:
    """Public, read-only dashboard data. Never exposes API keys or status secrets."""
    telegram_ok = False
    bot_username = None
    if application is not None:
        try:
            me = await application.bot.get_me()
            telegram_ok = True
            bot_username = me.username
        except Exception:
            logger.exception("Dashboard Telegram status check failed")

    return {
        "service": f"{BOT_BRAND_NAME} | {TMDB_BRAND_NAME} Telegram Bot",
        "status": "running" if application is not None and telegram_ok else "degraded",
        "telegram": "connected" if telegram_ok else "unavailable",
        "tmdb_configured": settings.tmdb_configured,
        "uptime_seconds": max(0, int(time.monotonic() - STARTED_AT)),
        "started_at": STARTED_AT_UTC.isoformat(),
        "bot_username": bot_username,
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "ottguild-mraprguild-tmdb-telegram-bot"}


@app.get("/api/status")
async def public_status(request: Request) -> dict[str, object]:
    """Authenticated status endpoint for the companion WordPress plugin."""
    expected = os.getenv("STATUS_API_KEY", "").strip()
    supplied = request.headers.get("x-mraprguild-status-key", "")
    if not expected or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=403, detail="Invalid status API key.")

    telegram_ok = False
    bot_username = None
    if application is not None:
        try:
            me = await application.bot.get_me()
            telegram_ok = True
            bot_username = me.username
        except Exception:
            logger.exception("Telegram status check failed")

    return {
        "service": f"{BOT_BRAND_NAME} | {TMDB_BRAND_NAME} Telegram Bot",
        "status": "running" if application is not None and telegram_ok else "degraded",
        "telegram": "connected" if telegram_ok else "unavailable",
        "tmdb_configured": settings.tmdb_configured,
        "uptime_seconds": max(0, int(time.monotonic() - STARTED_AT)),
        "started_at": STARTED_AT_UTC.isoformat(),
        "bot_username": bot_username,
        "website": "https://ottguild.online/movies/",
    }


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    if application is None:
        raise HTTPException(status_code=503, detail="Bot is starting. Try again shortly.")

    if settings.webhook_secret:
        supplied = x_telegram_bot_api_secret_token or ""
        if not hmac.compare_digest(supplied, settings.webhook_secret):
            raise HTTPException(status_code=403, detail="Invalid webhook secret.")

    try:
        payload = await request.json()
        update = Update.de_json(payload, application.bot)
        if update is None:
            raise ValueError("Empty Telegram update payload")
        await application.process_update(update)
    except (ValueError, TypeError) as exc:
        logger.warning("Invalid Telegram webhook payload: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid Telegram update payload.") from exc
    except Exception as exc:
        logger.exception("Could not process Telegram update")
        raise HTTPException(status_code=500, detail="Could not process update.") from exc

    return {"ok": True}
