# syntax=docker/dockerfile:1.6
#
# Cross-platform image: builds and runs identically on Mac (Apple Silicon
# or Intel), Linux, and Windows (via WSL2 / Docker Desktop). Docker's
# BuildKit targets the host's native architecture by default; the
# interviewer runs `docker compose up --build` on their machine and gets
# an image matched to their CPU. No pre-built artifacts are shipped.

# ───────── Stage 1: build the React frontend ──────────────────────────
FROM node:22-alpine AS frontend-builder
WORKDIR /frontend

# Install pnpm via corepack (ships with recent Node)
RUN corepack enable

# Lockfile + package.json first for layer caching
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# Copy the rest of the frontend and build static assets into /frontend/dist
COPY frontend/ ./
RUN pnpm build

# ───────── Stage 2: python runtime ────────────────────────────────────
FROM python:3.11-slim AS runtime

# System deps: uv (for lockfile-based install) + CA certs for broker HTTPS calls.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir uv==0.8.15

WORKDIR /app

# Install Python deps from the lockfile first (cached unless pyproject or lock changes).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy the backend source.
COPY src ./src

# Bring in the already-built frontend from stage 1.
COPY --from=frontend-builder /frontend/dist ./frontend/dist

# Non-root user for the runtime.
RUN useradd --create-home --uid 1000 kalpi \
 && mkdir -p /app/data \
 && chown -R kalpi:kalpi /app
USER kalpi

# Session DB lives here; mount a docker volume to persist across restarts.
ENV SESSION_DB_PATH=/app/data/sessions.sqlite

# uvicorn from the uv-managed venv.
EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
