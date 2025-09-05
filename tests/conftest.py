
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
def simple_riff_wav():
    """Get path to simple-riff.wav sample file."""
    samples_dir = Path(__file__).parent.parent / "samples"
    simple_riff = samples_dir / "simple-riff.wav"
    if simple_riff.exists():
        return str(simple_riff)
    return None

@pytest.fixture
def complex_riff_wav():
    """Get path to complex-riff.wav sample file."""
    samples_dir = Path(__file__).parent.parent / "samples"
    complex_riff = samples_dir / "complex-riff.wav"
    if complex_riff.exists():
        return str(complex_riff)
    return None

@pytest.fixture
def sample_audio_files():
    """Get dict of all available sample audio files."""
    samples_dir = Path(__file__).parent.parent / "samples"
    files = {}
    
    for name in ['simple-riff', 'complex-riff']:
        for ext in ['wav', 'mp3', 'flac', 'm4a', 'ogg', 'aac']:
            file_path = samples_dir / f"{name}.{ext}"
            if file_path.exists():
                files[f"{name}_{ext}"] = str(file_path)
    
    return files

@pytest.fixture
def transcription_with_real_audio(simple_riff_wav):
    """Create a transcription with real sample audio file."""
    if not simple_riff_wav:
        pytest.skip("Sample audio file not available")
    
    from django.core.files import File
    from django.core.files.uploadedfile import SimpleUploadedFile
    
    # Read the real audio file and create an UploadedFile
    with open(simple_riff_wav, 'rb') as f:
        audio_content = f.read()
    
    audio_file = SimpleUploadedFile(
        "simple-riff.wav",
        audio_content,
        content_type="audio/wav"
    )
    
    transcription = baker.make_recipe(
        'transcriber.transcription_basic',
        filename="simple-riff.wav",
        original_audio=audio_file,
        status="pending"
    )
    return transcription

@pytest.fixture
def live_server_url():
    """URL for the live test server."""
    return "http://localhost:8000"