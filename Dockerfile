# syntax=docker/dockerfile:1.4
# Enable BuildKit for better caching and parallel builds

# ============================================
# BASE IMAGE - Shared by all stages
# ============================================
FROM python:3.11-slim-bookworm AS python-base

# Python optimizations
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_NO_CACHE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# ============================================
# BUILDER BASE - For compiling dependencies
# ============================================
FROM python-base AS builder-base

# Install build dependencies and UV
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
    curl \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && /root/.local/bin/uv --version \
    && rm -rf /var/lib/apt/lists/*

# Add UV to PATH
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /tmp

# ============================================
# DEPENDENCY BUILDER - Compile Python packages with UV
# ============================================
FROM builder-base AS dependency-builder

WORKDIR /tmp

# Copy pyproject.toml and minimal project structure for dependency resolution
COPY pyproject.toml ./
COPY riffscribe ./riffscribe
COPY transcriber ./transcriber

# Install dependencies using UV with cache mount  
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/venv \
    && uv pip install --python=/opt/venv/bin/python -e .

# ============================================
# RUNTIME BASE - Minimal runtime dependencies
# ============================================
FROM python-base AS runtime-base

# Install runtime dependencies and UV
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    libgomp1 \
    libportaudio2 \
    postgresql-client \
    curl \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Add UV to PATH
ENV PATH="/root/.local/bin:$PATH"

# Create non-root user
RUN groupadd -r django && useradd -r -g django django

# ============================================
# DEVELOPMENT STAGE
# ============================================
FROM runtime-base AS development

WORKDIR /app

# Copy UV virtual environment from builder
COPY --from=dependency-builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy pyproject.toml for dev dependencies
COPY pyproject.toml ./

# Install dev dependencies with UV
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python=/opt/venv/bin/python --editable ".[dev]"

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

# Copy UV virtual environment from builder
COPY --from=dependency-builder --chown=django:django /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

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
