
"""
Pytest configuration and fixtures for RiffScribe tests.
"""
import os
import sys
import pytest
import django
from pathlib import Path

# Reclassify legacy markers into primary categories
@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    for item in items:
        if item.get_closest_marker("slow"):
            item.add_marker(pytest.mark.integration)
        if item.get_closest_marker("captcha"):
            item.add_marker(pytest.mark.integration)
        if item.get_closest_marker("comment"):
            item.add_marker(pytest.mark.integration)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'riffscribe.settings')
django.setup()

from django.test import Client
from django.core.files.uploadedfile import SimpleUploadedFile
from model_bakery import baker
from transcriber.models import Transcription
import pytest


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
def sample_transcription():
    """Create a sample transcription in the database using Model Bakery."""
    from django.core.files.uploadedfile import SimpleUploadedFile
    
    audio_file = SimpleUploadedFile(
        "test_audio.wav",
        b"fake audio content",
        content_type="audio/wav"
    )
    
    transcription = baker.make_recipe(
        'transcriber.transcription_basic',
        filename="test_audio.wav",
        original_audio=audio_file,
        status="pending"
    )
    return transcription


@pytest.fixture
def completed_transcription():
    """Create a completed transcription with results using Model Bakery."""
    from django.core.files.uploadedfile import SimpleUploadedFile
    
    audio_file = SimpleUploadedFile(
        "completed.wav",
        b"fake completed audio content",
        content_type="audio/wav"
    )
    
    transcription = baker.make_recipe(
        'transcriber.transcription_completed',
        filename="completed.wav",
        original_audio=audio_file,
        duration=30.5,
        estimated_tempo=120,
        estimated_key="C Major",
        complexity="moderate",
        detected_instruments=["guitar"]
    )
    return transcription


@pytest.fixture
def real_audio_file():
    """Get path to a real sample audio file."""
    import os
    samples_dir = Path(__file__).parent.parent / "samples"
    simple_riff = samples_dir / "simple-riff.wav"
    if simple_riff.exists():
        return str(simple_riff)
    return None

@pytest.fixture
def live_server_url():
    """URL for the live test server."""
    return "http://localhost:8000"