"""Telegram-safe formatting and OTTGuild URL helpers."""
from __future__ import annotations

import re
from html import escape
from urllib.parse import quote

from config import settings


def html(value: object | None) -> str:
    return escape(str(value or ""), quote=False)


def year_from_date(date_value: str | None) -> str:
    return date_value[:4] if date_value and len(date_value) >= 4 else "Year unknown"


def human_money(amount: object) -> str:
    try:
        value = int(amount or 0)
    except (TypeError, ValueError):
        return "Not available"
    return f"${value:,.0f}" if value > 0 else "Not available"


def human_runtime(value: object) -> str:
    try:
        minutes = int(value or 0)
    except (TypeError, ValueError):
        return "Not available"
    if minutes <= 0:
        return "Not available"
    hours, remainder = divmod(minutes, 60)
    if hours and remainder:
        return f"{hours}h {remainder}m"
    if hours:
        return f"{hours}h"
    return f"{remainder}m"


def movie_site_url(title: str) -> str:
    """Build a link for the configured movie page/search URL.

    Supported placeholders: {query} (URL-encoded title) and {slug} (simple slug).
    The default links to the WordPress-style search URL under /movies/.
    """
    template = settings.movie_site_url_template or "https://ottguild.online/movies/?s={query}"
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return template.replace("{query}", quote(title, safe="")).replace("{slug}", quote(slug, safe="-"))


def movie_result_label(movie: dict) -> str:
    title = str(movie.get("title") or movie.get("original_title") or "Untitled")
    date = year_from_date(movie.get("release_date"))
    return f"{title[:45]} ({date if date != 'Year unknown' else 'N/A'})"


def movie_details_text(movie: dict) -> str:
    title = html(movie.get("title") or movie.get("original_title") or "Untitled")
    original_title = movie.get("original_title")
    overview = str(movie.get("overview") or "No synopsis is available from TMDB.").strip()
    if len(overview) > 1100:
        overview = overview[:1097].rsplit(" ", 1)[0] + "..."

    genres = ", ".join(g.get("name", "") for g in movie.get("genres", []) if g.get("name")) or "Not available"
    countries = ", ".join(c.get("name", "") for c in movie.get("production_countries", []) if c.get("name")) or "Not available"
    languages = ", ".join(l.get("english_name") or l.get("name", "") for l in movie.get("spoken_languages", []) if l.get("english_name") or l.get("name")) or "Not available"
    companies = ", ".join(c.get("name", "") for c in movie.get("production_companies", [])[:4] if c.get("name")) or "Not available"

    credits = movie.get("credits") or {}
    cast = credits.get("cast") or []
    cast_names = ", ".join(c.get("name", "") for c in cast[:8] if c.get("name")) or "Not available"
    crew = credits.get("crew") or []
    directors = ", ".join(c.get("name", "") for c in crew if c.get("job") == "Director" and c.get("name")) or "Not available"
    writers = ", ".join(c.get("name", "") for c in crew if c.get("job") in {"Writer", "Screenplay", "Story"} and c.get("name"))
    writers = writers or "Not available"

    vote = movie.get("vote_average")
    rating = f"{float(vote):.1f}/10 ({int(movie.get('vote_count') or 0):,} votes)" if isinstance(vote, (int, float)) else "Not available"
    release_date = movie.get("release_date") or "Not available"
    status = movie.get("status") or "Not available"
    original_language = movie.get("original_language") or "Not available"
    tagline = movie.get("tagline") or ""

    lines = [
        f"🎬 <b>{title}</b>",
        f"📅 <b>Release:</b> {html(release_date)}",
        f"⭐ <b>TMDB rating:</b> {html(rating)}",
        f"🎭 <b>Genres:</b> {html(genres)}",
        f"⏱ <b>Runtime:</b> {html(human_runtime(movie.get('runtime')))}",
        f"🎬 <b>Director:</b> {html(directors)}",
        f"✍️ <b>Writer:</b> {html(writers)}",
        f"🌟 <b>Cast:</b> {html(cast_names)}",
        f"🌐 <b>Language(s):</b> {html(languages)}",
        f"🗺 <b>Country:</b> {html(countries)}",
        f"🏢 <b>Production:</b> {html(companies)}",
        f"📌 <b>Status:</b> {html(status)}",
        f"🗣 <b>Original language code:</b> {html(original_language)}",
        f"💰 <b>Budget:</b> {html(human_money(movie.get('budget')))}",
        f"💵 <b>Revenue:</b> {html(human_money(movie.get('revenue')))}",
    ]
    if original_title and original_title != movie.get("title"):
        lines.insert(1, f"📝 <b>Original title:</b> {html(original_title)}")
    if tagline:
        lines.insert(1, f"<i>{html(tagline)}</i>")
    lines.extend(["", "<b>Synopsis</b>", html(overview), "", "<i>Data and artwork supplied by TMDB. This bot is not endorsed or certified by TMDB.</i>"])
    return "\n".join(lines)
