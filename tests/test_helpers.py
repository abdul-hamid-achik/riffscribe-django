"""
Common test helpers and utilities
"""
from django.core.files.base import ContentFile
from pathlib import Path


def create_test_audio_file(filename='test.wav'):
    """Helper to create a test file for transcriptions using real sample audio"""
    # Use real sample audio file if available
    sample_path = Path(__file__).parent / 'samples' / 'simple-riff.wav'
    if sample_path.exists():
        with open(sample_path, 'rb') as f:
            return ContentFile(f.read(), filename)
    else:
        # Fallback to fake data
        return ContentFile(b'test audio data', filename)


def create_transcription_data(**kwargs):
    """Helper to create common transcription test data"""
    defaults = {
        'status': 'completed',
        'filename': 'test_song.wav',
        'original_audio': create_test_audio_file(),
    }
    defaults.update(kwargs)
    return defaults