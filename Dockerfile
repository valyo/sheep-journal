# --- shared base: runtime dependencies --------------------------------------
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

# --- dev: used by docker compose (debug server, tests) ---------------------
FROM base AS dev

COPY requirements-dev.txt ./
RUN pip install -r requirements-dev.txt

COPY . .

EXPOSE 5000

CMD ["flask", "--app", "sheep_journal", "run", "--host", "0.0.0.0", "--port", "5000", "--debug"]

# --- production: the image built and published by CI ----------------------
FROM base AS production

RUN useradd --create-home --uid 1000 appuser

COPY --chown=appuser:appuser . .
RUN mkdir -p /app/instance && chown appuser:appuser /app/instance

USER appuser

# The database and uploaded photos live here: mount a volume.
VOLUME ["/app/instance"]

ENV SHEEP_JOURNAL_ENV=production

EXPOSE 8000

# One worker: SQLite and the startup migrations don't like parallel writers.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "sheep_journal:create_app()"]
