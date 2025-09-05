"""
Pytest configuration and fixtures for RiffScribe tests.
"""
import os
import sys
import pytest
import django
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'riffscribe.settings')
django.setup()

from django.test import Client
from django.core.files.uploadedfile import SimpleUploadedFile
from transcriber.models import Transcription


@pytest.fixture
def django_client():
    """Django test client."""
    return Client()


@pytest.fixture
def sample_audio_file():
    """Create a sample audio file for testing."""
    # Create a minimal WAV file header (44 bytes)
    wav_header = bytes([
        0x52, 0x49, 0x46, 0x46,  # "RIFF"
        0x24, 0x00, 0x00, 0x00,  # File size
        0x57, 0x41, 0x56, 0x45,  # "WAVE"
        0x66, 0x6D, 0x74, 0x20,  # "fmt "
        0x10, 0x00, 0x00, 0x00,  # Subchunk size
        0x01, 0x00,              # Audio format (PCM)
        0x01, 0x00,              # Channels (1)
        0x44, 0xAC, 0x00, 0x00,  # Sample rate (44100)
        0x88, 0x58, 0x01, 0x00,  # Byte rate
        0x02, 0x00,              # Block align
        0x10, 0x00,              # Bits per sample
        0x64, 0x61, 0x74, 0x61,  # "data"
        0x00, 0x00, 0x00, 0x00   # Data size
    ])
    
    return SimpleUploadedFile(
        "test_audio.wav",
        wav_header + b'\x00' * 100,  # Add some silent audio data
        content_type="audio/wav"
    )


@pytest.fixture
def sample_transcription(sample_audio_file):
    """Create a sample transcription in the database."""
    transcription = Transcription.objects.create(
        filename="test_audio.wav",
        original_audio=sample_audio_file,
        status="pending"
    )
    return transcription


@pytest.fixture
def completed_transcription():
    """Create a completed transcription with results."""
    transcription = Transcription.objects.create(
        filename="completed.wav",
        status="completed",
        duration=30.5,
        estimated_tempo=120,
        estimated_key="C Major",
        complexity="moderate",
        detected_instruments=["guitar"],
        guitar_notes={
            "tempo": 120,
            "time_signature": "4/4",
            "measures": [
                {
                    "notes": [
                        {"string": 0, "fret": 3, "time": 0.0, "duration": 0.5}
                    ]
                }
            ]
        }
    )
    return transcription


@pytest.fixture
def live_server_url():
    """URL for the live test server."""
    return "http://localhost:8000"