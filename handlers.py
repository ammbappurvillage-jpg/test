"""Telegram commands, search results, and movie detail handlers."""
from __future__ import annotations

import logging
import time
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import settings
from formatting import html, movie_details_text, movie_result_label, movie_site_url, year_from_date
from tmdb import TMDBClient, TMDBError

logger = logging.getLogger(__name__)
PAGE_SIZE = 6
PROCESS_STARTED_AT = time.monotonic()

def format_uptime(seconds: int) -> str:
    days, rem = divmod(max(0, seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{days}d {hours}h {minutes}m {secs}s"


def tmdb(context: ContextTypes.DEFAULT_TYPE) -> TMDBClient:
    return context.application.bot_data["tmdb"]


def is_admin(user_id: int | None) -> bool:
    return bool(user_id is not None and user_id in settings.admin_ids)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    text = (
        "<b>Welcome to Mraprguild TMDB Movie Bot</b> 🎬\n\n"
        "Search movies by name and get the poster, synopsis, cast, director, release date, "
        "genres, runtime, rating, production details, budget, revenue and trailer link.\n\n"
        "<b>Try:</b>\n"
        "• Send a movie name, such as <code>Interstellar</code>\n"
        "• <code>/search Avatar</code>\n"
        "• <code>/movie 27205</code> (TMDB movie ID)\n"
        "• <code>/popular</code>, <code>/trending</code>, <code>/upcoming</code>\n\n"
        "Website: <a href=\"https://ottguild.online/movies/\">OTTGuild Movies</a>\n\n"
        "<i>This product uses the TMDB API but is not endorsed or certified by TMDB.</i>"
    )
    await message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message:
        await message.reply_text(
            "<b>Bot commands</b>\n"
            "/search movie name — Search TMDB\n"
            "/movie movie name or TMDB ID — Find a movie\n"
            "/popular — Popular movies\n"
            "/trending — Trending this week\n"
            "/now_playing — Now playing\n"
            "/top_rated — Top-rated movies\n"
            "/upcoming — Upcoming movies\n"
            "/id — Show your Telegram user ID\n"
            "/status — Bot/TMDB configuration status (admins only)\n\n"
            "You can also send a movie title directly in a private chat.",
            parse_mode=ParseMode.HTML,
        )


async def show_search_results(
    message: Any,
    context: ContextTypes.DEFAULT_TYPE,
    page: int = 0,
    *,
    edit: bool = False,
    category_title: str = "Search results",
) -> None:
    results = context.user_data.get("movie_results", [])
    if not results:
        text = "No stored results. Send a movie name to search again."
        if edit:
            await message.edit_text(text)
        else:
            await message.reply_text(text)
        return

    total_pages = max(1, (len(results) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    context.user_data["movie_results_page"] = page
    start_index = page * PAGE_SIZE
    current = results[start_index : start_index + PAGE_SIZE]
    rows = []
    for movie in current:
        movie_id = movie.get("id")
        if movie_id:
            rows.append([InlineKeyboardButton(movie_result_label(movie), callback_data=f"movie:{int(movie_id)}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ Previous", callback_data=f"page:{page - 1}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton("Next ▶", callback_data=f"page:{page + 1}"))
    if nav:
        rows.append(nav)

    text = f"<b>{html(category_title)}</b> — page {page + 1}/{total_pages}\nChoose a movie for full details:"
    markup = InlineKeyboardMarkup(rows)
    if edit:
        await message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    else:
        await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)


async def search_for_title(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str) -> None:
    message = update.effective_message
    if not message:
        return
    query = query.strip()
    if not query:
        await message.reply_text("Please enter a movie name. Example: <code>/search Interstellar</code>", parse_mode=ParseMode.HTML)
        return
    if len(query) > 120:
        await message.reply_text("Please keep the movie name under 120 characters.")
        return
    try:
        payload = await tmdb(context).search_movies(query)
        results = payload.get("results") or []
        context.user_data["movie_results"] = results[:30]
        if not results:
            await message.reply_text(f"No movies found for <b>{html(query)}</b>.", parse_mode=ParseMode.HTML)
            return
        await show_search_results(message, context, category_title=f"Results for: {query}")
    except TMDBError as exc:
        await message.reply_text(html(str(exc)), parse_mode=ParseMode.HTML)


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await search_for_title(update, context, " ".join(context.args))


async def movie_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = " ".join(context.args).strip()
    if not query:
        await search_for_title(update, context, "")
        return
    if query.isdigit():
        await send_movie_details(update.effective_message, context, int(query))
    else:
        await search_for_title(update, context, query)


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    command = (update.effective_message.text or "").split()[0].split("@")[0].lstrip("/")
    category = {
        "popular": "popular",
        "trending": "trending",
        "now_playing": "now_playing",
        "top_rated": "top_rated",
        "upcoming": "upcoming",
    }.get(command)
    if not category:
        return
    try:
        payload = await tmdb(context).list_movies(category)
        results = payload.get("results") or []
        context.user_data["movie_results"] = results[:30]
        title = {
            "popular": "Popular movies",
            "trending": "Trending movies this week",
            "now_playing": "Now playing in cinemas",
            "top_rated": "Top-rated movies",
            "upcoming": "Upcoming movies",
        }[category]
        if results:
            await show_search_results(message, context, category_title=title)
        else:
            await message.reply_text("TMDB did not return any movies for this category.")
    except TMDBError as exc:
        await message.reply_text(html(str(exc)), parse_mode=ParseMode.HTML)


async def send_movie_details(message: Any, context: ContextTypes.DEFAULT_TYPE, movie_id: int) -> None:
    if message is None:
        return
    try:
        movie = await tmdb(context).movie_details(movie_id)
        title = str(movie.get("title") or movie.get("original_title") or "Movie")
        poster = TMDBClient.image_url(movie.get("poster_path"))
        trailer = next(
            (
                video for video in (movie.get("videos") or {}).get("results", [])
                if video.get("site") == "YouTube" and video.get("type") == "Trailer" and video.get("key")
            ),
            None,
        )
        keyboard = [[InlineKeyboardButton("🔎 Find on OTTGuild", url=movie_site_url(title))]]
        if trailer:
            keyboard.append([InlineKeyboardButton("▶ Watch trailer", url=f"https://www.youtube.com/watch?v={trailer['key']}")])
        keyboard.append([InlineKeyboardButton("TMDB movie page", url=f"https://www.themoviedb.org/movie/{movie_id}")])
        markup = InlineKeyboardMarkup(keyboard)

        if poster:
            caption = f"<b>{html(title)}</b> ({html(year_from_date(movie.get('release_date')))})"
            vote = movie.get("vote_average")
            if isinstance(vote, (int, float)):
                caption += f"\n⭐ {float(vote):.1f}/10"
            try:
                await message.reply_photo(photo=poster, caption=caption, parse_mode=ParseMode.HTML)
            except Exception as photo_error:  # Telegram may fail to fetch a remote image temporarily.
                logger.warning("Unable to send poster for TMDB ID %s: %s", movie_id, photo_error)
                await message.reply_text("The movie poster could not be loaded, but here are the details.")
        else:
            await message.reply_text("No poster is available for this title in TMDB.")

        details = movie_details_text(movie)
        await message.reply_text(
            details,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    except TMDBError as exc:
        await message.reply_text(html(str(exc)), parse_mode=ParseMode.HTML)


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""
    if data.startswith("page:"):
        try:
            page = int(data.split(":", 1)[1])
            await show_search_results(query.message, context, page, edit=True)
        except (ValueError, IndexError):
            await query.message.reply_text("That page selection is not valid. Please search again.")
    elif data.startswith("movie:"):
        try:
            movie_id = int(data.split(":", 1)[1])
            await send_movie_details(query.message, context, movie_id)
        except (ValueError, IndexError):
            await query.message.reply_text("That movie selection is not valid. Please search again.")


async def text_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message and message.text:
        await search_for_title(update, context, message.text)


async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if update.effective_message and user:
        await update.effective_message.reply_text(f"Your Telegram user ID: <code>{user.id}</code>", parse_mode=ParseMode.HTML)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if not message:
        return
    if not is_admin(user.id if user else None):
        await message.reply_text("This command is available to bot admins only.")
        return
    await message.reply_text(
        "<b>Bot status</b>\n"
        f"Bot token: {'configured' if settings.bot_token else 'missing'}\n"
        f"TMDB credentials: {'configured' if settings.tmdb_configured else 'missing'}\n"
        f"OTTGuild URL template: {html(settings.movie_site_url_template)}\n"
        f"Admin IDs configured: {len(settings.admin_ids)}\n"
        f"Process uptime: {format_uptime(int(time.monotonic() - PROCESS_STARTED_AT))}\n"
        f"Status API key: {'configured' if __import__('os').getenv('STATUS_API_KEY') else 'missing'}",
        parse_mode=ParseMode.HTML,
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled Telegram update error", exc_info=context.error)


def register_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("movie", movie_command))
    for command in ("popular", "trending", "now_playing", "top_rated", "upcoming"):
        application.add_handler(CommandHandler(command, list_command))
    application.add_handler(CommandHandler("id", id_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_search))
    application.add_error_handler(error_handler)


def build_application() -> Application:
    application = Application.builder().token(settings.bot_token).build()
    application.bot_data["tmdb"] = TMDBClient()
    register_handlers(application)
    return application
