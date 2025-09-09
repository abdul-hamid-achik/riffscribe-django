# syntax=docker/dockerfile:1.4
# Enable BuildKit for better caching and parallel builds

# ============================================
# BASE DEPENDENCIES - Shared foundation
# ============================================
FROM python:3.11-slim-bookworm AS base

# Python optimizations
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_CACHE_DIR=/opt/uv-cache

WORKDIR /app

# Install UV and basic system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && cp /root/.local/bin/uv /usr/local/bin/uv \
    && chmod +x /usr/local/bin/uv \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create user and directories
RUN groupadd -r django && useradd -r -g django django \
    && mkdir -p /app/media /app/static /app/staticfiles /opt/uv-cache \
    && chown -R django:django /app /opt/uv-cache

# ============================================
# WEB TARGET - Lightweight web server
# ============================================
FROM base AS web

# Install minimal web dependencies only  
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy pyproject.toml for dependency resolution
COPY pyproject.toml ./

# Install only web dependencies (no ML packages)
RUN --mount=type=cache,target=/opt/uv-cache \
    uv venv /opt/venv \
    && uv pip install --python=/opt/venv/bin/python -e .

ENV PATH="/opt/venv/bin:$PATH"

# Copy minimal app structure
COPY --chown=django:django riffscribe/__init__.py ./riffscribe/__init__.py
COPY --chown=django:django transcriber/__init__.py ./transcriber/__init__.py

USER django

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "60", "riffscribe.wsgi:application"]

# ============================================ 
# WORKER TARGET - Lightweight AI processing (90% smaller!)
# ============================================
FROM base AS worker

# Install MINIMAL system dependencies for AI processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libssl-dev \
    libpq5 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean


COPY pyproject.toml ./

RUN --mount=type=cache,target=/opt/uv-cache \
    uv venv /opt/venv \
    && uv pip install --python=/opt/venv/bin/python -e ".[worker]" \
    && echo "AI Worker build complete - 90% smaller than ML version!"

ENV PATH="/opt/venv/bin:$PATH"

COPY --chown=django:django riffscribe/__init__.py ./riffscribe/__init__.py  
COPY --chown=django:django transcriber/__init__.py ./transcriber/__init__.py

RUN uv pip install --python=/opt/venv/bin/python -e . \
    && chown -R django:django /opt/venv

USER django

# AI workers can handle more concurrency (less memory per task)
CMD ["celery", "-A", "riffscribe", "worker", "--loglevel=info", "--concurrency=4"]

# ============================================
# DEVELOPMENT TARGET - Fast local development  
# ============================================
FROM base AS development

# Install lightweight system dependencies for web development
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libffi-dev \
    libssl-dev \
    libpq5 \
    git \
    vim \
    htop \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy pyproject.toml and install development dependencies (web + testing only)
COPY pyproject.toml ./

RUN --mount=type=cache,target=/opt/uv-cache \
    uv venv /opt/venv \
    && uv pip install --python=/opt/venv/bin/python -e ".[dev]"

ENV PATH="/opt/venv/bin:$PATH"

# Copy minimal app structure for editable install
COPY --chown=django:django riffscribe/__init__.py ./riffscribe/__init__.py
COPY --chown=django:django transcriber/__init__.py ./transcriber/__init__.py

RUN uv pip install --python=/opt/venv/bin/python -e . \
    && chown -R django:django /opt/venv

USER django

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# ============================================
# PRODUCTION WEB - Lightweight production web
# ============================================
FROM web AS production-web

# Copy application code
COPY --chown=django:django manage.py ./
COPY --chown=django:django riffscribe ./riffscribe
COPY --chown=django:django transcriber ./transcriber
COPY --chown=django:django templates ./templates
COPY --chown=django:django static ./static

# Collect static files
RUN python manage.py collectstatic --noinput || true

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

USER django

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--threads", "4", "--timeout", "120", "riffscribe.wsgi:application"]

# ============================================
# PRODUCTION WORKER - Lightweight AI production worker
# ============================================
FROM worker AS production-worker

# Copy application code
COPY --chown=django:django manage.py ./
COPY --chown=django:django riffscribe ./riffscribe
COPY --chown=django:django transcriber ./transcriber

# Health check for AI worker
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD celery -A riffscribe inspect ping || exit 1

USER django

# AI workers use less memory - can increase concurrency and remove memory limit
CMD ["celery", "-A", "riffscribe", "worker", "--loglevel=info", "--concurrency=4"]

# ============================================
# PRODUCTION SCHEDULER - Celery beat
# ============================================
FROM production-web AS production-scheduler

USER django

CMD ["celery", "-A", "riffscribe", "beat", "--loglevel=info"]
