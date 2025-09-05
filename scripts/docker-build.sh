#!/bin/bash

# Optimized Docker build script with BuildKit
# This script builds the Docker images with maximum optimization

set -e

echo "🚀 Building RiffScribe with Docker BuildKit optimizations..."

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Export BuildKit environment variables
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1
export BUILDKIT_PROGRESS=plain

# Build target (default: development)
TARGET=${1:-development}

echo -e "${YELLOW}Building target: ${TARGET}${NC}"

# Pull latest base images for cache
echo -e "${GREEN}Pulling base images for cache...${NC}"
docker pull python:3.11-slim-bookworm || true

# Build with BuildKit and cache
if [ "$TARGET" == "production" ]; then
    echo -e "${GREEN}Building production image...${NC}"
    docker build \
        --target production \
        --cache-from python:3.11-slim-bookworm \
        --cache-from riffscribe:builder \
        --cache-from riffscribe:latest \
        --tag riffscribe:latest \
        --tag riffscribe:production \
        --build-arg BUILDKIT_INLINE_CACHE=1 \
        .
    
    # Also build worker images for production
    echo -e "${GREEN}Building Celery worker image...${NC}"
    docker build \
        --target celery \
        --cache-from riffscribe:production \
        --tag riffscribe:celery \
        .
    
    echo -e "${GREEN}Building Celery beat image...${NC}"
    docker build \
        --target celery-beat \
        --cache-from riffscribe:production \
        --tag riffscribe:celery-beat \
        .
        
elif [ "$TARGET" == "development" ]; then
    echo -e "${GREEN}Building development image...${NC}"
    docker build \
        --target development \
        --cache-from python:3.11-slim-bookworm \
        --cache-from riffscribe:builder \
        --cache-from riffscribe:dev \
        --tag riffscribe:dev \
        --tag riffscribe:latest \
        --build-arg BUILDKIT_INLINE_CACHE=1 \
        .
else
    echo -e "${YELLOW}Unknown target: ${TARGET}${NC}"
    echo "Usage: $0 [development|production]"
    exit 1
fi

# Save builder cache for future builds
echo -e "${GREEN}Saving builder cache...${NC}"
docker build \
    --target dependency-builder \
    --cache-from python:3.11-slim-bookworm \
    --tag riffscribe:builder \
    --build-arg BUILDKIT_INLINE_CACHE=1 \
    . || true

echo -e "${GREEN}✅ Build complete!${NC}"

# Show image sizes
echo -e "${YELLOW}Image sizes:${NC}"
docker images | grep riffscribe | head -5

# Estimate time saved
echo -e "${GREEN}💡 Tips for faster builds:${NC}"
echo "  - Use 'docker-compose build --parallel' for parallel service builds"
echo "  - Keep Docker daemon running to maintain build cache"
echo "  - Use './scripts/docker-build.sh production' for optimized prod images"