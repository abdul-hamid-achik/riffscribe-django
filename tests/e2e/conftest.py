"""
Playwright configuration for end-to-end tests.
"""
import pytest
from playwright.sync_api import sync_playwright
from pathlib import Path


@pytest.fixture(scope="session")
def django_db_setup():
    """Override django_db_setup to use transactional test database."""
    pass


@pytest.fixture(scope="session")
def browser():
    """Create a browser instance for the test session."""
    with sync_playwright() as p:
        # Launch with options for better debugging
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        yield browser
        browser.close()


@pytest.fixture(scope="function")
def page(browser, live_server):
    """Create a new page for each test with live_server URL."""
    context = browser.new_context(
        base_url=live_server.url,
        ignore_https_errors=True
    )
    page = context.new_page()
    yield page
    context.close()


@pytest.fixture(autouse=True)
def setup_test_data(transactional_db):
    """Set up test data in the database using transactional_db for live_server tests."""
    from transcriber.models import Transcription
    
    # Create some test transcriptions for library tests
    Transcription.objects.create(
        filename="test_completed.wav",
        status="completed",
        duration=30.5,
        estimated_tempo=120,
        estimated_key="C Major",
        complexity="moderate",
        detected_instruments=["guitar"],
        guitar_notes={
            "tempo": 120,
            "time_signature": "4/4",
            "measures": [{"notes": []}]
        }
    )
    
    Transcription.objects.create(
        filename="test_pending.wav",
        status="pending"
    )
    
    yield
    
    # Cleanup
    Transcription.objects.all().delete()


@pytest.fixture
def sample_audio_path():
    """Get path to sample audio file for testing."""
    samples_dir = Path(__file__).parent.parent.parent / "samples"
    audio_file = samples_dir / "simple-riff.wav"
    if audio_file.exists():
        return str(audio_file)
    return None