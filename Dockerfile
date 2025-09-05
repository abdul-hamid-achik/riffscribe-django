# Base image with Python 3.11
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    git \
    build-essential \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    libsndfile1-dev \
    libportaudio2 \
    libportaudiocpp0 \
    portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Create media directory
RUN mkdir -p /app/media /app/static

# Expose port
EXPOSE 8000

# Default command (will be overridden in docker-compose)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]