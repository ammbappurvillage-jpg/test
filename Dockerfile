# Mraprguild TMDB Telegram Bot
# Build: docker build -t mraprguild-tmdb-bot .
# Run:   docker run --env-file .env -p 8000:8000 mraprguild-tmdb-bot

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

# Install dependencies first to improve Docker layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application source.
COPY . .

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Render and other container platforms can supply PORT at runtime.
CMD ["sh", "-c", "uvicorn bot:app --host 0.0.0.0 --port ${PORT:-8000}"]
