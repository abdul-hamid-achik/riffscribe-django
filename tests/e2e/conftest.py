"""
Playwright configuration for end-to-end tests.
"""
import pytest
from playwright.sync_api import sync_playwright
from django.contrib.staticfiles.testing import StaticLiveServerTestCase


@pytest.fixture(scope="session")
def browser():
    """Create a browser instance for the test session."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture(scope="function")
def page(browser):
    """Create a new page for each test."""
    context = browser.new_context()
    page = context.new_page()
    yield page
    context.close()


@pytest.fixture(scope="session")
def live_server():
    """Start Django's live test server."""
    class Server:
        url = "http://localhost:8081"
    
    return Server()


@pytest.fixture(autouse=True)
def setup_test_data(db):
    """Set up test data in the database."""
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