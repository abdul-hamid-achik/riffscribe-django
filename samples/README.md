# Sample Audio Files

This directory contains sample audio files for testing the RiffScribe transcription pipeline.

## Files

### Simple Riff Sample
A simple guitar riff with clear notes, ideal for testing basic transcription:
- **simple-riff.wav** - Original WAV format (uncompressed)
- **simple-riff.mp3** - MP3 format (192kbps, widely supported)
- **simple-riff.flac** - FLAC format (lossless compression)
- **simple-riff.m4a** - M4A format (256kbps AAC, Apple preferred)
- **simple-riff.ogg** - OGG Vorbis format (open source alternative)
- **simple-riff.aac** - AAC format (256kbps, high quality)

### Complex Riff Sample
A more complex guitar piece with multiple techniques, good for testing advanced features:
- **complex-riff.wav** - Original WAV format (uncompressed)
- **complex-riff.mp3** - MP3 format (192kbps, widely supported)
- **complex-riff.flac** - FLAC format (lossless compression)
- **complex-riff.m4a** - M4A format (256kbps AAC, Apple preferred)
- **complex-riff.ogg** - OGG Vorbis format (open source alternative)
- **complex-riff.aac** - AAC format (256kbps, high quality)

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

### Regenerating Sample Formats
If you need to regenerate the sample files in different formats:
```bash
# Generate all supported formats from the WAV source files
python scripts/generate_sample_formats.py

# Or with Docker
docker-compose exec django python scripts/generate_sample_formats.py
```

## Supported Formats

The RiffScribe application supports the following audio formats:
- **WAV** - Uncompressed, best quality, larger files
- **MP3** - Widely supported, good compression, 192kbps quality
- **FLAC** - Lossless compression, smaller than WAV but larger than lossy formats
- **M4A** - Apple's preferred format, 256kbps AAC encoding
- **OGG** - Open-source alternative to MP3, variable quality
- **AAC** - Advanced Audio Coding, 256kbps, excellent quality-to-size ratio

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