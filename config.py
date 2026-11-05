"""Environment-backed configuration for the Mraprguild TMDB Telegram bot."""
from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "").strip()
    tmdb_read_access_token: str = os.getenv("TMDB_READ_ACCESS_TOKEN", "").strip()
    tmdb_api_key: str = os.getenv("TMDB_API_KEY", "").strip()
    tmdb_language: str = os.getenv("TMDB_LANGUAGE", "en-US").strip() or "en-US"
    movie_site_url_template: str = os.getenv(
        "MOVIE_SITE_URL_TEMPLATE",
        "https://ottguild.online/movies/?s={query}",
    ).strip()
    webhook_secret: str = os.getenv("WEBHOOK_SECRET", "").strip()
    webhook_url: str = os.getenv("WEBHOOK_URL", "").strip()
    tmdb_image_size: str = os.getenv("TMDB_IMAGE_SIZE", "w500").strip() or "w500"
    admin_ids_raw: str = os.getenv("ADMIN_IDS", "").strip()

    @property
    def tmdb_configured(self) -> bool:
        return bool(self.tmdb_read_access_token or self.tmdb_api_key)

    @property
    def admin_ids(self) -> set[int]:
        ids: set[int] = set()
        for item in self.admin_ids_raw.split(","):
            item = item.strip()
            if item.isdigit():
                ids.add(int(item))
        return ids

    def validate(self, *, require_webhook: bool = False) -> None:
        missing = []
        if not self.bot_token:
            missing.append("BOT_TOKEN")
        if not self.tmdb_configured:
            missing.append("TMDB_READ_ACCESS_TOKEN (or TMDB_API_KEY)")
        if require_webhook and not (self.webhook_url or os.getenv("RENDER_EXTERNAL_URL", "").strip()):
            missing.append("WEBHOOK_URL (or Render's RENDER_EXTERNAL_URL)")
        if missing:
            raise RuntimeError("Missing required environment setting(s): " + ", ".join(missing))


settings = Settings()
