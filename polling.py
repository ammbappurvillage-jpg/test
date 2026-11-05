"""Optional local polling runner. Use this for testing on a computer, not Render."""
from __future__ import annotations

import logging

from telegram import BotCommand
from telegram.ext import Application

from config import settings
from handlers import register_handlers
from tmdb import TMDBClient


async def post_init(application: Application) -> None:
    await application.bot_data["tmdb"].start()
    await application.bot.set_my_commands([
        BotCommand("start", "Start the movie bot"),
        BotCommand("search", "Search movies by name"),
        BotCommand("movie", "Get movie details by name or TMDB ID"),
        BotCommand("popular", "Popular movies"),
        BotCommand("trending", "Trending movies this week"),
        BotCommand("help", "Show bot help"),
    ])


async def post_shutdown(application: Application) -> None:
    await application.bot_data["tmdb"].close()


def main() -> None:
    settings.validate()
    logging.basicConfig(level="INFO", format="%(asctime)s | %(levelname)s | %(message)s")
    application = (
        Application.builder()
        .token(settings.bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    application.bot_data["tmdb"] = TMDBClient()
    register_handlers(application)
    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
