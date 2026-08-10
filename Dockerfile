FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-xlib-2.0-0 \
    libffi-dev \
    libcairo2 \
    ffmpeg \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --no-install-project

COPY app/ ./app/
COPY migrations/ ./migrations/
COPY scripts/ ./scripts/
COPY alembic.ini ./alembic.ini

RUN mkdir -p /app/uploads/blogs

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '7860') + '/health', timeout=3)" || exit 1

CMD ["/bin/sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
