#!/bin/bash

# Ultra-fast development build with maximum caching
# This is the fastest way to rebuild during development

set -e

echo "⚡ Lightning-fast RiffScribe rebuild..."

# Enable BuildKit
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

# Use docker-compose with parallel builds
echo "🔨 Building services in parallel..."
docker-compose build --parallel

echo "✅ Build complete!"

# Optionally start services
if [ "$1" == "up" ]; then
    echo "🚀 Starting services..."
    docker-compose up -d
    echo "📱 RiffScribe is running at http://localhost:8000"
    echo "🌸 Flower (Celery monitoring) at http://localhost:5555"
fi

# Show what changed
echo ""
echo "📊 Image info:"
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}" | grep -E "(REPOSITORY|riffscribe)" | head -6