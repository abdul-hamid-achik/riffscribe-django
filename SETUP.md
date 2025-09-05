# RiffScribe Setup Guide

## Complete Implementation Status

✅ **Docker Infrastructure**
- Dockerfile with all dependencies
- docker-compose.yml with Django, Celery, Redis, PostgreSQL, and Flower
- Environment configuration

✅ **Celery & Redis**
- Async task processing with Celery workers
- Redis as message broker
- Flower for monitoring at port 5555
- Background task management

✅ **Advanced ML Pipeline**
- **basic-pitch** for polyphonic transcription
- **demucs** for source separation
- **crepe** for monophonic pitch detection
- **madmom** for accurate tempo detection
- **music21** for key detection
- Fallback to librosa for basic processing

✅ **Tab Generation**
- Dynamic Programming optimizer for string/fret mapping
- Playability optimization
- Technique detection (hammer-ons, pull-offs, slides, bends, vibrato)
- Multiple tuning support

✅ **Export Formats**
- MusicXML generation (with and without music21)
- Guitar Pro 5 (.gp5) support
- MIDI export
- ASCII tab export
- PDF support (requires lilypond setup)

✅ **Frontend Integration**
- HTMX for reactive UI
- AlphaTab for interactive tab rendering
- Real-time status updates
- Progress tracking

## Quick Start

### 1. Clone and Setup Environment

```bash
# Clone the repository
git clone <your-repo>
cd riffscribe-django

# Copy environment file
cp .env.example .env
# Edit .env and update DJANGO_SECRET_KEY
```

### 2. Run with Docker (Recommended)

```bash
# Build and start all services
docker-compose up --build

# In another terminal, run migrations
docker-compose exec django python manage.py migrate

# Create superuser (optional)
docker-compose exec django python manage.py createsuperuser

# Access the application
# Main app: http://localhost:8000
# Flower (Celery monitoring): http://localhost:5555
```

### 3. Alternative: Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Start Redis (required)
docker run -p 6379:6379 redis:7

# Run migrations
python manage.py migrate

# Start Django
python manage.py runserver

# In another terminal, start Celery worker
celery -A riffscribe worker -l info

# In another terminal, start Celery beat (optional)
celery -A riffscribe beat -l info

# Start Flower (optional, for monitoring)
celery -A riffscribe flower
```

## Usage

1. **Upload Audio**
   - Navigate to http://localhost:8000
   - Click "Upload Audio"
   - Select an audio file (MP3, WAV, M4A, FLAC, OGG)
   - Max file size: 50MB

2. **Processing**
   - The system will automatically:
     - Analyze audio (tempo, key, complexity)
     - Separate guitar track (if multiple instruments detected)
     - Transcribe notes using ML models
     - Generate optimized guitar tabs
     - Create MusicXML for rendering

3. **View Results**
   - Interactive tab preview with AlphaTab
   - Playback controls
   - Export to multiple formats

4. **Export Options**
   - MusicXML (for music software)
   - Guitar Pro 5 (for Guitar Pro)
   - MIDI (for DAWs)
   - ASCII Tab (text format)
   - PDF (requires additional setup)

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │────▶│   Django    │────▶│   Celery    │
│   (HTMX)    │◀────│   (8000)    │◀────│   Workers   │
└─────────────┘     └─────────────┘     └─────────────┘
                           │                     │
                           ▼                     ▼
                    ┌─────────────┐     ┌─────────────┐
                    │ PostgreSQL  │     │    Redis    │
                    │   Database  │     │   (6379)    │
                    └─────────────┘     └─────────────┘
```

## ML Pipeline Flow

```
Audio Input
    ↓
[Demucs] → Source Separation
    ↓
[Basic-Pitch/CREPE] → Note Detection
    ↓
[Madmom/Librosa] → Tempo/Beat Analysis
    ↓
[Music21] → Key Detection
    ↓
[DP Optimizer] → String/Fret Mapping
    ↓
[Technique Detector] → Add Articulations
    ↓
[Export Manager] → Generate Files
```

## Configuration

### Environment Variables

- `DJANGO_SECRET_KEY`: Secret key for Django
- `DEBUG`: Set to False in production
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection URL
- `USE_GPU`: Enable GPU acceleration (if available)
- `DEMUCS_MODEL`: Demucs model to use (htdemucs, htdemucs_ft)
- `MAX_AUDIO_LENGTH`: Maximum audio length in seconds

### ML Models

The system will automatically download ML models on first use:
- Basic-pitch model (~30MB)
- Demucs model (~500MB)
- CREPE model (~200MB)

## Troubleshooting

### Common Issues

1. **Out of Memory**
   - Reduce `MAX_AUDIO_LENGTH` in .env
   - Use smaller Demucs model
   - Increase Docker memory allocation

2. **Slow Processing**
   - Enable GPU support (requires CUDA)
   - Reduce audio quality/length
   - Skip source separation for single instruments

3. **Model Download Failed**
   - Check internet connection
   - Manually download models to `ml_models/` directory
   - Use fallback transcription (librosa)

4. **AlphaTab Not Loading**
   - Check browser console for errors
   - Ensure MusicXML generation succeeded
   - Verify CDN access (may need local hosting)

## Performance Tips

- **GPU Acceleration**: Set `USE_GPU=True` and use nvidia-docker
- **Caching**: Redis caches task results automatically
- **Batch Processing**: Use Celery's batch features for multiple files
- **Model Selection**: Choose models based on accuracy vs speed tradeoff

## API Endpoints

- `GET /` - Homepage
- `GET /upload/` - Upload form
- `POST /upload/` - Submit audio file
- `GET /transcription/<id>/` - View transcription
- `GET /transcription/<id>/status/` - Get status (HTMX)
- `POST /transcription/<id>/export/` - Generate export
- `GET /transcription/<id>/preview/` - Tab preview
- `GET /library/` - Browse completed transcriptions

## Contributing

The codebase is organized as:
- `transcriber/` - Django app
- `transcriber/ml_pipeline.py` - ML processing
- `transcriber/tab_generator.py` - Tab optimization
- `transcriber/export_manager.py` - File exports
- `transcriber/tasks.py` - Celery tasks
- `transcriber/templates/` - HTMX templates

## License

MIT License - See LICENSE file