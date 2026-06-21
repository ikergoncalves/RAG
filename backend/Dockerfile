# syntax=docker/dockerfile:1

# --- Builder stage -----------------------------------------------------------
# Installs all Python dependencies into an isolated virtualenv so the runtime
# stage can copy a single self-contained directory and nothing else.
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build the virtualenv at a fixed path; the runtime stage copies it as-is.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Install dependencies first so this layer is cached unless requirements change.
# Re-ranking is delegated to the Cohere API, so there is no torch /
# sentence-transformers to install — the build is fast and the image stays small.
# All current dependencies ship manylinux wheels, so no compiler toolchain is
# needed here.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# --- Runtime stage -----------------------------------------------------------
# Minimal final image: the base interpreter, the pre-built venv and the app
# code, running as an unprivileged user.
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Unprivileged user that owns the app and its writable upload directory.
RUN useradd --create-home --uid 1000 app

# Bring in the dependencies built in the previous stage.
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=app:app . .

# UPLOAD_DIR (see docker-compose) lives here and must be writable by `app`.
RUN mkdir -p /app/var/uploads && chown -R app:app /app/var

USER app

EXPOSE 8000

# Start command: run migrations, then the API server. `exec` makes uvicorn the
# foreground PID for clean signal handling; `${PORT:-8000}` honors the platform
# port ($PORT on Railway/Render/Fly) and falls back to 8000 locally.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
