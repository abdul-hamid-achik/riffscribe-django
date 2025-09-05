#!/bin/bash
# Setup script for Cursor Background Agents
# This script initializes the Django development environment

set -e  # Exit on any error

echo "🚀 Setting up Cursor Background Agent environment for riffscribe-django..."

# Ensure we're in the right directory
cd /app

# Install Python dependencies using UV
echo "📦 Installing Python dependencies..."
uv sync

# Apply database migrations
echo "🗄️  Applying database migrations..."
if [ "$DATABASE_URL" ]; then
    echo "Using external database: $DATABASE_URL"
    uv run python manage.py migrate --noinput
else
    echo "⚠️  No DATABASE_URL found. Background agent will need database connection."
    echo "   Please configure DATABASE_URL in Cursor settings secrets."
fi

# Collect static files
echo "🎨 Collecting static files..."
uv run python manage.py collectstatic --noinput --clear

# Create necessary directories
echo "📁 Creating application directories..."
mkdir -p media/audio static staticfiles tmp audio exports

# Set permissions for non-root user
echo "🔐 Setting permissions..."
chown -R django:django media static staticfiles tmp audio exports

# Verify the setup
echo "✅ Verifying setup..."
uv run python manage.py check --deploy || true

# Print helpful information
echo ""
echo "🎯 Setup complete! Available commands:"
echo "  • Django dev server: uv run python manage.py runserver 0.0.0.0:8000"
echo "  • Celery worker: uv run celery -A riffscribe worker --loglevel=info"
echo "  • Celery beat: uv run celery -A riffscribe beat --loglevel=info"
echo "  • Tests: uv run pytest -v"
echo "  • Django shell: uv run python manage.py shell"
echo ""
echo "📋 Required secrets (configure in Cursor settings):"
echo "  • DATABASE_URL (PostgreSQL connection)"
echo "  • REDIS_URL (Redis for Celery)"
echo "  • SECRET_KEY (Django secret key)"
echo "  • OPENAI_API_KEY (for AI transcription)"
echo ""
echo "🎵 Ready to process audio to guitar tabs!"
