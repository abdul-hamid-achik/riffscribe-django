"""
Integration tests for the upload form fix.
"""
import pytest
from django.urls import reverse
from unittest.mock import patch


@pytest.mark.django_db
class TestUploadFormFix:
    """Test the fixed upload form functionality."""
    
    @pytest.mark.integration
    def test_upload_without_file_returns_error(self, django_client):
        """Test that uploading without a file returns an appropriate error."""
        response = django_client.post(
            reverse('transcriber:upload'),
            {},  # No file
            HTTP_HX_REQUEST='true'  # Simulate HTMX request
        )
        
        assert response.status_code == 400
        assert b'No file provided' in response.content
        assert b'upload_error' in response.content or b'Upload Failed' in response.content
    
    @pytest.mark.integration
    def test_upload_with_invalid_format_returns_error(self, django_client):
        """Test that uploading an invalid format returns an error."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        
        invalid_file = SimpleUploadedFile(
            "test.pdf",
            b"PDF content",
            content_type="application/pdf"
        )
        
        response = django_client.post(
            reverse('transcriber:upload'),
            {'audio_file': invalid_file},
            HTTP_HX_REQUEST='true'
        )
        
        assert response.status_code == 400
        assert b'Invalid file format' in response.content
    
    @pytest.mark.integration
    def test_upload_with_valid_file_succeeds(self, django_client, sample_audio_file):
        """Test that uploading a valid file works correctly."""
        from unittest.mock import patch, MagicMock
        
        with patch('transcriber.views.process_transcription.delay') as mock_task:
            mock_task.return_value = MagicMock(id='test-task-123')
            
            response = django_client.post(
                reverse('transcriber:upload'),
                {'audio_file': sample_audio_file},
                HTTP_HX_REQUEST='true'
            )
            
            # Should return success partial
            assert response.status_code == 200
            assert b'Upload Successful' in response.content or b'successful' in response.content
            assert b'View Progress' in response.content
    
    @pytest.mark.integration
    def test_upload_form_client_side_validation(self, django_client):
        """Test that the upload form has proper client-side validation."""
        response = django_client.get(reverse('transcriber:upload'))
        
        assert response.status_code == 200
        
        # Check for Alpine.js validation code
        assert b'validateAndSubmit' in response.content
        assert b'hasFile' in response.content
        assert b'Select a File First' in response.content
        
        # Check for disabled state when no file
        assert b':disabled="uploading || !hasFile"' in response.content
    
    @pytest.mark.integration
    def test_upload_handles_large_files(self, django_client):
        """Test that large files are rejected properly."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        
        # Create a "large" file (just fake the size check)
        large_file = SimpleUploadedFile(
            "large_audio.wav",
            b"x" * (101 * 1024 * 1024),  # 101MB
            content_type="audio/wav"
        )
        
        with patch('django.core.files.uploadedfile.SimpleUploadedFile.size', 101 * 1024 * 1024):
            response = django_client.post(
                reverse('transcriber:upload'),
                {'audio_file': large_file},
                HTTP_HX_REQUEST='true'
            )
            
            # Note: This might not work as expected due to Django's own limits
            # but the view should handle it
            assert response.status_code in [400, 413]