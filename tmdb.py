"""Small async client for The Movie Database (TMDB) API v3."""
from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx

from config import settings


class TMDBError(Exception):
    """Readable error returned to the Telegram user when TMDB cannot be reached."""


class TMDBClient:
    API_ROOT = "https://api.themoviedb.org/3/"
    IMAGE_ROOT = "https://image.tmdb.org/t/p/"

    def __init__(self) -> None:
        self._http: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._http is None:
            headers = {"Accept": "application/json"}
            if settings.tmdb_read_access_token:
                headers["Authorization"] = f"Bearer {settings.tmdb_read_access_token}"
            self._http = httpx.AsyncClient(
                base_url=self.API_ROOT,
                headers=headers,
                timeout=httpx.Timeout(20.0, connect=10.0),
                follow_redirects=True,
            )

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._http is None:
            await self.start()
        request_params = {"language": settings.tmdb_language}
        if params:
            request_params.update(params)
        if settings.tmdb_api_key and not settings.tmdb_read_access_token:
            request_params["api_key"] = settings.tmdb_api_key
        try:
            assert self._http is not None
            response = await self._http.get(path, params=request_params)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise TMDBError("TMDB returned an unexpected response.")
            return payload
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 401:
                raise TMDBError("TMDB rejected the API credentials. Check your TMDB Read Access Token or API key.") from exc
            if status == 404:
                raise TMDBError("That movie could not be found in TMDB.") from exc
            if status == 429:
                raise TMDBError("TMDB is receiving too many requests. Please try again shortly.") from exc
            raise TMDBError(f"TMDB request failed (HTTP {status}). Please try again later.") from exc
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise TMDBError("TMDB could not be reached. Please try again in a moment.") from exc
        except ValueError as exc:
            raise TMDBError("TMDB returned invalid data. Please try again later.") from exc

    async def search_movies(self, query: str, page: int = 1) -> dict[str, Any]:
        return await self._get(
            "search/movie",
            {"query": query, "page": max(1, page), "include_adult": "false"},
        )

    async def movie_details(self, movie_id: int) -> dict[str, Any]:
        return await self._get(
            f"movie/{movie_id}",
            {"append_to_response": "credits,videos,release_dates"},
        )

    async def list_movies(self, category: str, page: int = 1) -> dict[str, Any]:
        allowed = {"popular", "trending", "now_playing", "top_rated", "upcoming"}
        if category not in allowed:
            raise TMDBError("Unknown movie category.")
        if category == "trending":
            return await self._get("trending/movie/week", {"page": max(1, page)})
        return await self._get(f"movie/{category}", {"page": max(1, page)})

    @classmethod
    def image_url(cls, image_path: str | None, size: str | None = None) -> str | None:
        if not image_path:
            return None
        selected_size = size or settings.tmdb_image_size
        return urljoin(cls.IMAGE_ROOT, f"{selected_size}/{image_path.lstrip('/')}")
