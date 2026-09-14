# syntax=docker/dockerfile:1
# =============================================================================
# Kairos Backend — multi-stage build (FastAPI API + Celery/Temporal workers)
# One image, four roles (command is set per-service in docker-compose).
#   builder  → installs all deps into a venv (needs the build toolchain)
#   runtime  → slim image with only runtime libs + the venv, runs as non-root
# No HEALTHCHECK here: this image serves both HTTP (API) and non-HTTP (workers)
# roles, so the health probe is defined per-service in docker-compose.yml.
# =============================================================================

# ---- builder --------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build toolchain — stays in the builder stage only, never in the final image.
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Isolated venv so it can be copied wholesale into the runtime stage.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- runtime --------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Runtime shared libs required by OpenCV/torch/PyMuPDF + curl for the API probe.
# (Build headers live in the builder stage; only the runtime .so files land here.)
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    libgomp1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Pre-built dependencies from the builder stage.
COPY --from=builder /opt/venv /opt/venv

# Non-root runtime user.
RUN groupadd --system --gid 1001 kairos \
    && useradd --system --uid 1001 --gid kairos --no-create-home kairos

# Application code (build context is ./backend; .dockerignore trims caches).
COPY --chown=kairos:kairos . .

# Numeric uid:gid (the `kairos` user above, 1001:1001) so the runtime user resolves on any host
# and orchestrators can verify it is non-root without reading /etc/passwd (hadolint DL3066).
USER 1001:1001

EXPOSE 8000

# Default = API. Workers override `command:` in docker-compose.yml.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
