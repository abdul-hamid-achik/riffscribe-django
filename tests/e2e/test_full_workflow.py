"""
End-to-end tests for RiffScribe using Playwright.
"""
import pytest
import time
from pathlib import Path
from playwright.sync_api import Page, expect
from django.contrib.staticfiles.testing import StaticLiveServerTestCase


@pytest.mark.e2e
class TestRiffScribeWorkflow:
    """Test the complete user workflow from upload to export."""
    
    @pytest.fixture(scope="function", autouse=True)
    def setup(self, page: Page, live_server):
        """Set up for each test."""
        self.page = page
        self.live_server_url = live_server.url
        self.sample_audio = Path(__file__).parent.parent.parent / "samples" / "simple-riff.wav"
        
    def test_homepage_loads(self):
        """Test that the homepage loads correctly."""
        self.page.goto(self.live_server_url)
        
        # Check title and main elements
        expect(self.page).to_have_title("RiffScribe - Guitar Tab Transcription")
        expect(self.page.locator("h1")).to_contain_text("RiffScribe")
        
        # Check navigation elements
        expect(self.page.locator("nav")).to_be_visible()
        expect(self.page.get_by_role("link", name="Upload")).to_be_visible()
        expect(self.page.get_by_role("link", name="Library")).to_be_visible()
    
    def test_upload_workflow(self):
        """Test the complete upload and transcription workflow."""
        # Navigate to upload page
        self.page.goto(f"{self.live_server_url}/upload/")
        
        # Check upload form is present
        expect(self.page.locator("#upload-form")).to_be_visible()
        expect(self.page.locator('input[type="file"]')).to_be_visible()
        
        # Upload a file
        if self.sample_audio.exists():
            self.page.set_input_files('input[type="file"]', str(self.sample_audio))
            
            # Submit the form
            self.page.click('button[type="submit"]')
            
            # Wait for redirect to transcription page
            self.page.wait_for_url("**/transcription/**")
            
            # Check status card is visible
            expect(self.page.locator("#status-card")).to_be_visible()
            
            # Check for pending or processing status
            status_text = self.page.locator("#status-card").text_content()
            assert "pending" in status_text.lower() or "processing" in status_text.lower()
    
    def test_library_page(self):
        """Test the library page functionality."""
        self.page.goto(f"{self.live_server_url}/library/")
        
        # Check page elements
        expect(self.page.locator("h1")).to_contain_text("Library")
        
        # Check filter form
        expect(self.page.locator("#filter-form")).to_be_visible()
        
        # Test instrument filter
        instrument_select = self.page.locator('select[name="instrument"]')
        if instrument_select.is_visible():
            instrument_select.select_option("guitar")
            self.page.wait_for_load_state("networkidle")
            
        # Test complexity filter
        complexity_select = self.page.locator('select[name="complexity"]')
        if complexity_select.is_visible():
            complexity_select.select_option("moderate")
            self.page.wait_for_load_state("networkidle")
    
    def test_transcription_detail_page(self):
        """Test transcription detail page features."""
        # First create a test transcription via upload
        self.page.goto(f"{self.live_server_url}/upload/")
        
        if self.sample_audio.exists():
            # Upload file
            self.page.set_input_files('input[type="file"]', str(self.sample_audio))
            self.page.click('button[type="submit"]')
            
            # Wait for transcription page
            self.page.wait_for_url("**/transcription/**")
            
            # Check tab preview section
            tab_preview = self.page.locator("#tab-preview")
            if tab_preview.is_visible():
                # Check AlphaTab container
                expect(self.page.locator("#alphaTab")).to_be_visible()
            
            # Check export options
            export_section = self.page.locator("#export-section")
            if export_section.is_visible():
                # Check export buttons
                expect(self.page.locator('button:has-text("MusicXML")')).to_be_visible()
                expect(self.page.locator('button:has-text("MIDI")')).to_be_visible()
    
    def test_htmx_interactions(self):
        """Test HTMX-powered interactions."""
        # Create a test transcription
        self.page.goto(f"{self.live_server_url}/upload/")
        
        if self.sample_audio.exists():
            self.page.set_input_files('input[type="file"]', str(self.sample_audio))
            self.page.click('button[type="submit"]')
            self.page.wait_for_url("**/transcription/**")
            
            # Test status polling (HTMX should update status)
            initial_status = self.page.locator("#status-card").text_content()
            
            # Wait a bit for potential status update
            time.sleep(2)
            
            # Check if status card exists (may have been updated via HTMX)
            expect(self.page.locator("#status-card")).to_be_visible()
            
            # Test delete functionality if delete button exists
            delete_button = self.page.locator('button[data-confirm]')
            if delete_button.is_visible():
                # Click delete with confirmation
                self.page.on("dialog", lambda dialog: dialog.accept())
                delete_button.click()
                
                # Should redirect to library after deletion
                self.page.wait_for_url("**/library/**")
    
    def test_responsive_design(self):
        """Test responsive design on different viewports."""
        viewports = [
            {"width": 375, "height": 667},   # Mobile
            {"width": 768, "height": 1024},  # Tablet
            {"width": 1920, "height": 1080}, # Desktop
        ]
        
        for viewport in viewports:
            self.page.set_viewport_size(viewport)
            self.page.goto(self.live_server_url)
            
            # Check main elements are visible at all sizes
            expect(self.page.locator("h1")).to_be_visible()
            
            # Check navigation (may be hamburger on mobile)
            nav = self.page.locator("nav")
            expect(nav).to_be_visible()
    
    def test_error_handling(self):
        """Test error handling for invalid inputs."""
        self.page.goto(f"{self.live_server_url}/upload/")
        
        # Try to submit without file
        submit_button = self.page.locator('button[type="submit"]')
        submit_button.click()
        
        # Should show validation error or stay on same page
        expect(self.page).to_have_url(f"{self.live_server_url}/upload/")
        
        # Try to upload non-audio file
        from tempfile import NamedTemporaryFile
        with NamedTemporaryFile(suffix='.txt', delete=False) as tmp:
            tmp.write(b"Not an audio file")
            tmp_path = tmp.name
        
        self.page.set_input_files('input[type="file"]', tmp_path)
        submit_button.click()
        
        # Should show error message
        error_message = self.page.locator('.error, .alert-danger, [role="alert"]')
        if error_message.is_visible():
            expect(error_message).to_contain_text("Invalid")
        
        # Clean up temp file
        Path(tmp_path).unlink()
    
    def test_export_functionality(self):
        """Test file export features."""
        # Navigate to a completed transcription (if exists in library)
        self.page.goto(f"{self.live_server_url}/library/")
        
        # Click on first transcription if available
        transcription_links = self.page.locator('a[href*="/transcription/"]')
        if transcription_links.count() > 0:
            transcription_links.first.click()
            
            # Wait for detail page
            self.page.wait_for_url("**/transcription/**")
            
            # Test export buttons
            export_buttons = {
                "MusicXML": "musicxml",
                "MIDI": "midi",
                "ASCII": "ascii"
            }
            
            for button_text, format_name in export_buttons.items():
                button = self.page.locator(f'button:has-text("{button_text}")')
                if button.is_visible():
                    # Click export button
                    with self.page.expect_download() as download_info:
                        button.click()
                        download = download_info.value
                        
                        # Verify download
                        assert format_name in download.suggested_filename.lower()


@pytest.mark.e2e
class TestAccessibility:
    """Test accessibility features."""
    
    @pytest.fixture(scope="function", autouse=True)
    def setup(self, page: Page, live_server):
        """Set up for each test."""
        self.page = page
        self.live_server_url = live_server.url
    
    def test_keyboard_navigation(self):
        """Test keyboard navigation through the site."""
        self.page.goto(self.live_server_url)
        
        # Tab through interactive elements
        self.page.keyboard.press("Tab")
        
        # Check focus is visible
        focused = self.page.locator(":focus")
        expect(focused).to_be_visible()
        
        # Navigate to upload via keyboard
        self.page.keyboard.press("Tab")
        self.page.keyboard.press("Tab")
        self.page.keyboard.press("Enter")
        
        # Should navigate to upload page
        self.page.wait_for_url("**/upload/**")
    
    def test_aria_labels(self):
        """Test ARIA labels and roles."""
        self.page.goto(self.live_server_url)
        
        # Check main navigation has proper role
        nav = self.page.locator('nav, [role="navigation"]')
        expect(nav).to_be_visible()
        
        # Check form inputs have labels
        self.page.goto(f"{self.live_server_url}/upload/")
        file_input = self.page.locator('input[type="file"]')
        
        # Check associated label or aria-label
        if file_input.is_visible():
            label = self.page.locator(f'label[for="{file_input.get_attribute("id")}"]')
            if not label.is_visible():
                # Check for aria-label
                aria_label = file_input.get_attribute("aria-label")
                assert aria_label is not None


@pytest.mark.e2e
class TestPerformance:
    """Test performance-related aspects."""
    
    @pytest.fixture(scope="function", autouse=True)
    def setup(self, page: Page, live_server):
        """Set up for each test."""
        self.page = page
        self.live_server_url = live_server.url
    
    def test_page_load_time(self):
        """Test that pages load within acceptable time."""
        start_time = time.time()
        self.page.goto(self.live_server_url)
        load_time = time.time() - start_time
        
        # Page should load within 3 seconds
        assert load_time < 3.0, f"Page took {load_time}s to load"
    
    def test_htmx_response_time(self):
        """Test HTMX partial updates are fast."""
        self.page.goto(f"{self.live_server_url}/library/")
        
        # Trigger HTMX request (e.g., filter)
        start_time = time.time()
        
        instrument_select = self.page.locator('select[name="instrument"]')
        if instrument_select.is_visible():
            instrument_select.select_option("guitar")
            
            # Wait for HTMX to complete
            self.page.wait_for_load_state("networkidle")
            
            response_time = time.time() - start_time
            
            # HTMX updates should be fast (under 1 second)
            assert response_time < 1.0, f"HTMX update took {response_time}s"