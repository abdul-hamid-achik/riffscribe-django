# syntax=docker/dockerfile:1.4
# Enable BuildKit for better caching and parallel builds

# ============================================
# BASE IMAGE - Shared by all stages
# ============================================
FROM python:3.11-slim-bookworm AS python-base

# Python optimizations
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

# ============================================
# BUILDER BASE - For compiling dependencies
# ============================================
FROM python-base AS builder-base

# Install build dependencies in a single layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    libsndfile1-dev \
    libportaudio2 \
    portaudio19-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp

# ============================================
# DEPENDENCY BUILDER - Compile Python packages
# ============================================
FROM builder-base AS dependency-builder

# Use BuildKit cache mount for pip
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements/base.txt,target=base.txt \
    pip install --user --no-warn-script-location -r base.txt

# Build ML dependencies separately for better caching
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements/ml.txt,target=ml.txt \
    pip install --user --no-warn-script-location -r ml.txt

# ============================================
# RUNTIME BASE - Minimal runtime dependencies
# ============================================
FROM python-base AS runtime-base

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    libgomp1 \
    libportaudio2 \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user
RUN groupadd -r django && useradd -r -g django django

# ============================================
# DEVELOPMENT STAGE
# ============================================
FROM runtime-base AS development

WORKDIR /app

# Copy compiled dependencies from builder
COPY --from=dependency-builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Install dev dependencies with cache mount
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements/dev.txt,target=dev.txt \
    pip install --no-warn-script-location -r dev.txt

# Copy application code
COPY --chown=django:django . .

# Create required directories
RUN mkdir -p /app/media /app/static /app/staticfiles \
    && chown -R django:django /app/media /app/static /app/staticfiles

EXPOSE 8000

USER django

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
# ============================================
# PRODUCTION STAGE - Optimized for size
# ============================================
FROM runtime-base AS production

WORKDIR /app

# Copy compiled dependencies from builder
COPY --from=dependency-builder --chown=django:django /root/.local /usr/local

# Copy only necessary application files
COPY --chown=django:django manage.py ./
COPY --chown=django:django riffscribe ./riffscribe
COPY --chown=django:django transcriber ./transcriber
COPY --chown=django:django templates ./templates
COPY --chown=django:django static ./static

# Create required directories with proper permissions
RUN mkdir -p /app/media /app/staticfiles \
    && chown -R django:django /app

# Collect static files
RUN python manage.py collectstatic --noinput || true

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import django; django.setup()" || exit 1

EXPOSE 8000

USER django

# Use gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--threads", "2", "--timeout", "120", "riffscribe.wsgi:application"]

# ============================================
# CELERY WORKER STAGE
# ============================================
FROM production AS celery

USER django

# Override command for Celery worker
CMD ["celery", "-A", "riffscribe", "worker", "--loglevel=info", "--concurrency=2"]

# ============================================
# CELERY BEAT STAGE
# ============================================
FROM production AS celery-beat

USER django

# Override command for Celery beat
CMD ["celery", "-A", "riffscribe", "beat", "--loglevel=info"]
