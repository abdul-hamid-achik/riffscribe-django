# Sample Audio Files

This directory contains sample audio files for testing the RiffScribe transcription pipeline.

## Files

- **simple-riff.wav** - A simple guitar riff with clear notes, ideal for testing basic transcription
- **complex-riff.wav** - A more complex guitar piece with multiple techniques, good for testing advanced features

## Usage

### Testing via Web Interface
1. Start the application with `docker-compose up`
2. Navigate to http://localhost:8000
3. Click "Upload Audio"
4. Select one of these sample files

### Testing via Command Line
```bash
# Test the ML pipeline directly
python scripts/test_pipeline.py

# Or with Docker
docker-compose exec django python scripts/test_pipeline.py
```

## Expected Results

### simple-riff.wav
- Should detect clear individual notes
- Tempo around 120-140 BPM
- Simple complexity rating
- Basic string/fret positions

### complex-riff.wav
- Should detect multiple simultaneous notes
- Various techniques (bends, slides, etc.)
- Moderate to complex rating
- Optimized fingering positions

## Adding Your Own Samples

Place any `.wav`, `.mp3`, `.m4a`, or `.flac` files in this directory for testing.

Recommended specifications:
- Sample rate: 44.1 kHz or 48 kHz
- Bit depth: 16 or 24 bit
- Duration: 10-60 seconds for best results
- Clean recording with minimal background noise