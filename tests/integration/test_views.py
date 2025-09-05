"""
Integration tests for Django views.
"""
import pytest
import json
from django.urls import reverse
from unittest.mock import patch, MagicMock
from transcriber.models import Transcription, TabExport


@pytest.mark.django_db
class TestTranscriberViews:
    """Test the transcriber views."""
    
    @pytest.mark.integration
    def test_index_view(self, django_client):
        """Test the index page loads."""
        response = django_client.get('/')
        assert response.status_code == 200
        assert b'RiffScribe' in response.content
    
    @pytest.mark.integration
    def test_upload_page(self, django_client):
        """Test the upload page loads."""
        response = django_client.get('/upload/')
        assert response.status_code == 200
        assert b'Upload' in response.content or b'upload' in response.content
    
    @pytest.mark.integration
    def test_file_upload_success(self, django_client, sample_audio_file):
        """Test successful file upload."""
        with patch('transcriber.tasks.process_transcription.delay') as mock_task:
            mock_task.return_value = MagicMock(id='test-task-id')
            
            response = django_client.post(
                '/upload/',
                {'audio_file': sample_audio_file},
                follow=True
            )
            
            assert response.status_code == 200
            assert Transcription.objects.count() == 1
            
            transcription = Transcription.objects.first()
            assert transcription.filename == 'test_audio.wav'
            assert transcription.status == 'pending'
    
    @pytest.mark.integration
    def test_file_upload_invalid_format(self, django_client):
        """Test upload with invalid file format."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        
        invalid_file = SimpleUploadedFile(
            "test.txt",
            b"Not an audio file",
            content_type="text/plain"
        )
        
        response = django_client.post(
            '/upload/',
            {'audio_file': invalid_file}
        )
        
        assert response.status_code == 400
        data = json.loads(response.content)
        assert 'error' in data
        assert 'Invalid file format' in data['error']
    
    @pytest.mark.integration
    def test_transcription_detail_view(self, django_client, completed_transcription):
        """Test the transcription detail page."""
        url = f'/transcription/{completed_transcription.id}/'
        response = django_client.get(url)
        
        assert response.status_code == 200
        assert completed_transcription.filename.encode() in response.content
        assert b'completed' in response.content.lower()
    
    @pytest.mark.integration
    def test_status_endpoint(self, django_client, sample_transcription):
        """Test the status endpoint for HTMX polling."""
        url = f'/transcription/{sample_transcription.id}/status/'
        
        # Test JSON response
        response = django_client.get(url)
        assert response.status_code == 200
        
        data = json.loads(response.content)
        assert 'status' in data
        assert data['id'] == str(sample_transcription.id)
        
        # Test HTMX response
        response = django_client.get(
            url,
            HTTP_HX_REQUEST='true'
        )
        assert response.status_code == 200
        assert b'status-card' in response.content
    
    @pytest.mark.integration
    def test_export_generation(self, django_client, completed_transcription):
        """Test export generation."""
        url = f'/transcription/{completed_transcription.id}/export/'
        
        with patch('transcriber.tasks.generate_export.delay') as mock_export:
            mock_export.return_value = MagicMock(id='export-task-id')
            
            response = django_client.post(
                url,
                {'format': 'musicxml'}
            )
            
            assert response.status_code == 200
            mock_export.assert_called_once_with(
                str(completed_transcription.id),
                'musicxml'
            )
    
    @pytest.mark.integration
    def test_library_view(self, django_client, completed_transcription):
        """Test the library page with filters."""
        # Test without filters
        response = django_client.get('/library/')
        assert response.status_code == 200
        assert completed_transcription.filename.encode() in response.content
        
        # Test with instrument filter
        response = django_client.get('/library/?instrument=guitar')
        assert response.status_code == 200
        
        # Test with complexity filter
        response = django_client.get('/library/?complexity=moderate')
        assert response.status_code == 200
        assert completed_transcription.filename.encode() in response.content
    
    @pytest.mark.integration
    def test_delete_transcription(self, django_client, sample_transcription):
        """Test deleting a transcription."""
        url = f'/transcription/{sample_transcription.id}/delete/'
        
        # Test HTMX delete
        response = django_client.delete(
            url,
            HTTP_HX_REQUEST='true'
        )
        assert response.status_code == 204
        assert Transcription.objects.filter(id=sample_transcription.id).count() == 0
    
    @pytest.mark.integration
    def test_preview_tab_endpoint(self, django_client, completed_transcription):
        """Test the tab preview endpoint."""
        url = f'/transcription/{completed_transcription.id}/preview/'
        response = django_client.get(url)
        
        assert response.status_code == 200
        assert b'alphatab' in response.content.lower()
    
    @pytest.mark.integration
    def test_task_status_endpoint(self, django_client):
        """Test Celery task status endpoint."""
        with patch('transcriber.views.AsyncResult') as mock_result:
            mock_result.return_value = MagicMock(
                state='SUCCESS',
                result={'status': 'completed'},
                info={'step': 'Done'}
            )
            
            response = django_client.get('/task/test-task-id/status/')
            assert response.status_code == 200
            
            data = json.loads(response.content)
            assert data['task_id'] == 'test-task-id'
            assert data['state'] == 'SUCCESS'