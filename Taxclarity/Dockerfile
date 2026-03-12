# =============================================================================
# Stage 1: Build frontend static assets
# =============================================================================
FROM node:22-slim AS frontend-builder

WORKDIR /build
COPY frontend-next/package.json frontend-next/package-lock.json ./
RUN npm ci
COPY frontend-next/ ./
RUN npm run build

# =============================================================================
# Stage 2: Install Python dependencies with uv (fast)
# =============================================================================
FROM python:3.12-slim-bookworm AS python-deps

WORKDIR /deps
RUN pip install --no-cache-dir uv
COPY requirements.txt ./
RUN uv pip install --system --no-cache -r requirements.txt

# NOTE: Playwright browsers are NOT installed (~1GB savings).
# The Fetcher (Playwright) tier will be unavailable; scrapers fall back to
# HTTP and StealthyFetcher tiers which work without browser binaries.

# =============================================================================
# Stage 3: Runtime image with nginx + honcho
# =============================================================================
FROM python:3.12-slim-bookworm AS runtime

# Install nginx
RUN apt-get update && \
    apt-get install -y --no-install-recommends nginx && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python packages from deps stage
COPY --from=python-deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=python-deps /usr/local/bin /usr/local/bin

# Copy frontend build
COPY --from=frontend-builder /build/out /app/frontend-next/out

# Copy nginx config
COPY nginx.conf /etc/nginx/nginx.conf

# Copy application code
COPY agents/ /app/agents/
COPY backend/ /app/backend/
COPY memory/ /app/memory/
COPY orchestrator/ /app/orchestrator/
COPY config.py /app/config.py
COPY Procfile /app/Procfile
COPY pyproject.toml /app/pyproject.toml

# Environment
ENV PYTHONUNBUFFERED=1
ENV LOG_FORMAT=json
ENV PORT=8080

EXPOSE 8080

# Start nginx in background (daemon on by default in nginx.conf is overridden
# here -- our nginx.conf sets "daemon off" but we run it with & so it stays
# in the background), then honcho in foreground manages all Python services.
# If honcho dies (any child process exits), the container crashes and Cloud Run
# restarts it automatically.
CMD ["sh", "-c", "nginx -c /etc/nginx/nginx.conf -g 'daemon on;' && exec honcho start -f Procfile"]
