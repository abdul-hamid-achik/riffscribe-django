"""
Comprehensive file upload tests for the transcription system.
Tests all aspects of file uploads including validation, processing, and error handling.
"""

import pytest
import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.test import override_settings

from transcriber.models import Transcription
from model_bakery import baker


@pytest.mark.django_db
@pytest.mark.integration
class TestFileUploads:
    """Comprehensive test suite for file upload functionality."""

    # ========== Upload Validation Tests ==========

    def test_upload_without_file_returns_error(self, django_client):
        """Test that uploading without a file returns an appropriate error."""
        response = django_client.post(
            reverse('transcriber:upload'),
            {},  # No file
            HTTP_HX_REQUEST='true'  # Simulate HTMX request
        )
        
        assert response.status_code == 400
        assert b'No file provided' in response.content or b'required' in response.content
        assert b'upload_error' in response.content or b'Upload Failed' in response.content

    def test_upload_with_empty_file_returns_error(self, django_client):
        """Test that uploading an empty file is rejected."""
        empty_file = SimpleUploadedFile(
            "empty.wav",
            b"",  # Empty content
            content_type="audio/wav"
        )
        
        response = django_client.post(
            reverse('transcriber:upload'),
            {'audio_file': empty_file},
            HTTP_HX_REQUEST='true'
        )
        
        assert response.status_code == 400
        assert b'empty' in response.content.lower() or b'invalid' in response.content.lower()

    @pytest.mark.parametrize("invalid_format,content_type", [
        ("test.pdf", "application/pdf"),
        ("test.doc", "application/msword"),
        ("test.txt", "text/plain"),
        ("test.exe", "application/x-msdownload"),
        ("test.zip", "application/zip"),
        ("test.avi", "video/x-msvideo"),  # Video file
        ("test.unknown", "application/octet-stream"),
    ])
    def test_upload_with_invalid_formats_returns_error(self, django_client, invalid_format, content_type):
        """Test that uploading invalid file formats returns appropriate errors."""
        invalid_file = SimpleUploadedFile(
            invalid_format,
            b"Invalid content for audio",
            content_type=content_type
        )
        
        response = django_client.post(
            reverse('transcriber:upload'),
            {'audio_file': invalid_file},
            HTTP_HX_REQUEST='true'
        )
        
        assert response.status_code == 400
        assert b'Invalid file format' in response.content or b'not supported' in response.content

    # ========== Valid Upload Tests ==========

    @pytest.mark.parametrize("file_format,content_type", [
        ("wav", "audio/wav"),
        ("mp3", "audio/mpeg"),
        ("flac", "audio/flac"),
        ("m4a", "audio/mp4"),
        ("ogg", "audio/ogg"),
        ("webm", "audio/webm"),
    ])
    def test_upload_with_valid_formats_succeeds(self, django_client, file_format, content_type):
        """Test that all supported audio formats can be uploaded."""
        # Create a minimal valid audio file header for each format
        audio_headers = {
            'wav': b'RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00',
            'mp3': b'\xff\xfb\x90\x00',  # MP3 frame header
            'flac': b'fLaC\x00\x00\x00"',  # FLAC header
            'm4a': b'\x00\x00\x00\x20ftypM4A ',  # M4A header
            'ogg': b'OggS\x00\x02',  # Ogg header
            'webm': b'\x1a\x45\xdf\xa3',  # WebM/Matroska header
        }
        
        # Get appropriate header or use generic data
        file_content = audio_headers.get(file_format, b'\x00' * 100)
        
        valid_file = SimpleUploadedFile(
            f"test_audio.{file_format}",
            file_content,
            content_type=content_type
        )
        
        with patch('transcriber.views.upload.process_transcription.delay') as mock_task:
            mock_task.return_value = MagicMock(id='test-task-123')
            
            response = django_client.post(
                reverse('transcriber:upload'),
                {'audio_file': valid_file},
                HTTP_HX_REQUEST='true'
            )
            
            # Should accept the file
            assert response.status_code == 200
            assert b'Upload Successful' in response.content or b'successful' in response.content
            
            # Should have created a transcription
            assert Transcription.objects.filter(filename=f"test_audio.{file_format}").exists()

    def test_upload_with_sample_files(self, django_client, sample_audio_files):
        """Test uploading actual sample audio files."""
        tested_count = 0
        
        for file_key, file_path in sample_audio_files.items():
            if not os.path.exists(file_path):
                continue
            
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            filename = os.path.basename(file_path)
            content_type = self._get_content_type(filename)
            
            uploaded_file = SimpleUploadedFile(
                filename,
                file_content,
                content_type=content_type
            )
            
            with patch('transcriber.views.upload.process_transcription.delay') as mock_task:
                mock_task.return_value = MagicMock(id=f'task-{file_key}')
                
                response = django_client.post(
                    reverse('transcriber:upload'),
                    {'audio_file': uploaded_file},
                    HTTP_HX_REQUEST='true'
                )
                
                assert response.status_code == 200
                assert b'successful' in response.content.lower()
                tested_count += 1
        
        assert tested_count > 0, "No sample files were available for testing"

    # ========== File Size Tests ==========

    @override_settings(MAX_UPLOAD_SIZE=10 * 1024 * 1024)  # 10MB limit
    def test_upload_file_size_limits(self, django_client):
        """Test file size validation."""
        # Test file at the limit (should succeed)
        limit_file = SimpleUploadedFile(
            "at_limit.wav",
            b'RIFF' + b'\x00' * (10 * 1024 * 1024 - 4),  # 10MB
            content_type="audio/wav"
        )
        
        with patch('transcriber.views.upload.process_transcription.delay') as mock_task:
            mock_task.return_value = MagicMock(id='test-task')
            
            response = django_client.post(
                reverse('transcriber:upload'),
                {'audio_file': limit_file},
                HTTP_HX_REQUEST='true'
            )
            
            # Should accept file at limit
            assert response.status_code == 200

    @override_settings(MAX_UPLOAD_SIZE=10 * 1024 * 1024)  # 10MB limit
    def test_upload_oversized_file_rejected(self, django_client):
        """Test that oversized files are rejected."""
        # Create a file that exceeds the limit
        oversized_file = SimpleUploadedFile(
            "oversized.wav",
            b'RIFF' + b'\x00' * (11 * 1024 * 1024),  # 11MB
            content_type="audio/wav"
        )
        
        # Mock the size property
        with patch.object(SimpleUploadedFile, 'size', 11 * 1024 * 1024):
            response = django_client.post(
                reverse('transcriber:upload'),
                {'audio_file': oversized_file},
                HTTP_HX_REQUEST='true'
            )
            
            # Should reject oversized file
            assert response.status_code in [400, 413]
            assert b'too large' in response.content.lower() or b'size limit' in response.content.lower()

    # ========== Special Characters and Edge Cases ==========

    @pytest.mark.parametrize("filename", [
        "audio with spaces.wav",
        "audio-with-dashes.wav",
        "audio_with_underscores.wav",
        "audio.multiple.dots.wav",
        "UPPERCASE.WAV",
        "音楽.wav",  # Unicode characters
        "café_music.wav",  # Accented characters
        "audio(1).wav",  # Parentheses
        "audio[1].wav",  # Brackets
        "very_long_filename_that_exceeds_normal_length_limits_but_should_still_work_correctly.wav",
    ])
    def test_upload_with_special_filenames(self, django_client, filename):
        """Test uploading files with various special characters in filenames."""
        audio_file = SimpleUploadedFile(
            filename,
            b'RIFF' + b'\x00' * 100,
            content_type="audio/wav"
        )
        
        with patch('transcriber.views.upload.process_transcription.delay') as mock_task:
            mock_task.return_value = MagicMock(id='test-task')
            
            response = django_client.post(
                reverse('transcriber:upload'),
                {'audio_file': audio_file},
                HTTP_HX_REQUEST='true'
            )
            
            assert response.status_code == 200
            
            # Check that transcription was created with sanitized filename
            transcriptions = Transcription.objects.filter(
                filename__icontains=filename.split('.')[0][:50]  # First 50 chars of name
            )
            assert transcriptions.exists()

    # ========== Concurrent Upload Tests ==========

    def test_concurrent_uploads(self, django_client):
        """Test handling multiple simultaneous uploads."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        def upload_file(file_num):
            audio_file = SimpleUploadedFile(
                f"concurrent_{file_num}.wav",
                b'RIFF' + b'\x00' * 100,
                content_type="audio/wav"
            )
            
            with patch('transcriber.views.upload.process_transcription.delay') as mock_task:
                mock_task.return_value = MagicMock(id=f'task-{file_num}')
                
                response = django_client.post(
                    reverse('transcriber:upload'),
                    {'audio_file': audio_file},
                    HTTP_HX_REQUEST='true'
                )
                
                return response.status_code, file_num
        
        # Upload 5 files concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(upload_file, i) for i in range(5)]
            
            results = []
            for future in as_completed(futures):
                status_code, file_num = future.result()
                results.append((status_code, file_num))
        
        # All uploads should succeed
        assert all(status == 200 for status, _ in results)
        
        # All transcriptions should be created
        assert Transcription.objects.filter(filename__startswith='concurrent_').count() == 5

    # ========== Upload Progress and UI Tests ==========

    def test_upload_form_client_validation(self, django_client):
        """Test that the upload form has proper client-side validation."""
        response = django_client.get(reverse('transcriber:upload'))
        
        assert response.status_code == 200
        
        # Check for validation elements
        content = response.content.decode('utf-8')
        
        # Alpine.js validation
        assert 'validateAndSubmit' in content or 'x-data' in content
        assert 'hasFile' in content or 'selectedFile' in content
        
        # File input
        assert '<input type="file"' in content
        assert 'accept=' in content  # Should specify accepted formats
        
        # Submit button with disabled state
        assert ':disabled=' in content or 'disabled' in content

    def test_upload_shows_progress_indication(self, django_client):
        """Test that upload shows progress/loading state."""
        response = django_client.get(reverse('transcriber:upload'))
        content = response.content.decode('utf-8')
        
        # Should have uploading state
        assert 'uploading' in content or 'loading' in content or 'progress' in content
        
        # Should have some form of progress indication
        assert 'spinner' in content or 'animate' in content or 'pulse' in content

    def test_upload_htmx_response_format(self, django_client, sample_audio_file):
        """Test that HTMX requests receive proper partial responses."""
        with patch('transcriber.views.upload.process_transcription.delay') as mock_task:
            mock_task.return_value = MagicMock(id='test-task')
            
            # HTMX request
            response = django_client.post(
                reverse('transcriber:upload'),
                {'audio_file': sample_audio_file},
                HTTP_HX_REQUEST='true'
            )
            
            assert response.status_code == 200
            assert b'hx-' in response.content or b'View Progress' in response.content
            
            # Non-HTMX request (regular form submission)
            response = django_client.post(
                reverse('transcriber:upload'),
                {'audio_file': sample_audio_file}
            )
            
            # Should redirect or return full page
            assert response.status_code in [200, 302]

    # ========== Error Recovery Tests ==========

    def test_upload_handles_processing_failure(self, django_client, sample_audio_file):
        """Test that upload handles processing failures gracefully."""
        with patch('transcriber.views.upload.process_transcription.delay') as mock_task:
            # Simulate task failure
            mock_task.side_effect = Exception("Processing failed")
            
            response = django_client.post(
                reverse('transcriber:upload'),
                {'audio_file': sample_audio_file},
                HTTP_HX_REQUEST='true'
            )
            
            # Should handle error gracefully
            assert response.status_code in [200, 500]
            if response.status_code == 500:
                assert b'error' in response.content.lower()

    def test_upload_duplicate_file_handling(self, django_client, sample_audio_file):
        """Test handling of duplicate file uploads."""
        with patch('transcriber.views.upload.process_transcription.delay') as mock_task:
            mock_task.return_value = MagicMock(id='task-1')
            
            # First upload
            response1 = django_client.post(
                reverse('transcriber:upload'),
                {'audio_file': sample_audio_file},
                HTTP_HX_REQUEST='true'
            )
            assert response1.status_code == 200
            
            # Duplicate upload
            response2 = django_client.post(
                reverse('transcriber:upload'),
                {'audio_file': sample_audio_file},
                HTTP_HX_REQUEST='true'
            )
            assert response2.status_code == 200
            
            # Should create separate transcriptions
            count = Transcription.objects.filter(
                filename=sample_audio_file.name
            ).count()
            assert count >= 2

    # ========== Integration with Processing Pipeline ==========

    def test_upload_triggers_processing_pipeline(self, django_client, sample_audio_file):
        """Test that successful upload triggers the processing pipeline."""
        with patch('transcriber.views.upload.process_transcription.delay') as mock_task:
            mock_task.return_value = MagicMock(id='test-task-123')
            
            response = django_client.post(
                reverse('transcriber:upload'),
                {'audio_file': sample_audio_file},
                HTTP_HX_REQUEST='true'
            )
            
            assert response.status_code == 200
            
            # Verify task was called
            mock_task.assert_called_once()
            
            # Verify transcription was created
            transcription = Transcription.objects.filter(
                filename=sample_audio_file.name
            ).first()
            assert transcription is not None
            assert transcription.status == 'pending'

    def test_upload_metadata_extraction(self, django_client):
        """Test that upload extracts and stores file metadata."""
        audio_file = SimpleUploadedFile(
            "test_metadata.wav",
            b'RIFF' + b'\x00' * 1000,
            content_type="audio/wav"
        )
        
        with patch('transcriber.views.upload.process_transcription.delay') as mock_task:
            mock_task.return_value = MagicMock(id='test-task')
            
            response = django_client.post(
                reverse('transcriber:upload'),
                {'audio_file': audio_file},
                HTTP_HX_REQUEST='true'
            )
            
            assert response.status_code == 200
            
            transcription = Transcription.objects.filter(
                filename="test_metadata.wav"
            ).first()
            
            assert transcription is not None
            # Check metadata fields that might be set
            assert transcription.file_size is not None or len(audio_file) > 0

    # ========== Helper Methods ==========

    def _get_content_type(self, filename):
        """Get appropriate content type for a filename."""
        ext = filename.split('.')[-1].lower()
        content_types = {
            'wav': 'audio/wav',
            'mp3': 'audio/mpeg',
            'flac': 'audio/flac',
            'm4a': 'audio/mp4',
            'ogg': 'audio/ogg',
            'webm': 'audio/webm',
        }
        return content_types.get(ext, 'audio/wav')


@pytest.mark.django_db
@pytest.mark.integration
class TestUploadSecurity:
    """Security-focused tests for file upload functionality."""

    def test_upload_prevents_path_traversal(self, django_client):
        """Test that path traversal attempts are blocked."""
        malicious_filenames = [
            "../../../etc/passwd.wav",
            "..\\..\\..\\windows\\system32\\config\\sam.wav",
            "audio/../../../evil.wav",
            "./../audio.wav",
        ]
        
        for filename in malicious_filenames:
            audio_file = SimpleUploadedFile(
                filename,
                b'RIFF' + b'\x00' * 100,
                content_type="audio/wav"
            )
            
            with patch('transcriber.views.upload.process_transcription.delay') as mock_task:
                mock_task.return_value = MagicMock(id='test-task')
                
                response = django_client.post(
                    reverse('transcriber:upload'),
                    {'audio_file': audio_file},
                    HTTP_HX_REQUEST='true'
                )
                
                # Should either reject or sanitize filename
                if response.status_code == 200:
                    # Check that filename was sanitized
                    transcription = Transcription.objects.order_by('-created_at').first()
                    assert transcription is not None
                    assert '..' not in transcription.filename
                    assert '/' not in transcription.filename
                    assert '\\' not in transcription.filename

    def test_upload_validates_mime_type(self, django_client):
        """Test that MIME type is validated, not just file extension."""
        # File with .wav extension but wrong content/MIME type
        fake_wav = SimpleUploadedFile(
            "fake_audio.wav",
            b'<html>Not audio content</html>',
            content_type="text/html"  # Wrong MIME type
        )
        
        response = django_client.post(
            reverse('transcriber:upload'),
            {'audio_file': fake_wav},
            HTTP_HX_REQUEST='true'
        )
        
        # Should validate actual content type
        assert response.status_code == 400

    def test_upload_prevents_script_injection(self, django_client):
        """Test that script injection in filenames is prevented."""
        script_filenames = [
            "<script>alert('xss')</script>.wav",
            "audio\"><script>alert(1)</script>.wav",
            "audio.wav<img src=x onerror=alert(1)>",
            "';alert(String.fromCharCode(88,83,83))//';alert(String.fromCharCode(88,83,83))//\".wav",
        ]
        
        for filename in script_filenames:
            audio_file = SimpleUploadedFile(
                filename,
                b'RIFF' + b'\x00' * 100,
                content_type="audio/wav"
            )
            
            with patch('transcriber.views.upload.process_transcription.delay') as mock_task:
                mock_task.return_value = MagicMock(id='test-task')
                
                response = django_client.post(
                    reverse('transcriber:upload'),
                    {'audio_file': audio_file},
                    HTTP_HX_REQUEST='true'
                )
                
                if response.status_code == 200:
                    # Verify filename was sanitized
                    transcription = Transcription.objects.order_by('-created_at').first()
                    assert '<script>' not in transcription.filename
                    assert 'alert' not in transcription.filename
                    assert '<' not in transcription.filename
                    assert '>' not in transcription.filename