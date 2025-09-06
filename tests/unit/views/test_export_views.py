"""
Tests for export views
"""
import json
import pytest
from django.test import Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.files.base import ContentFile
from unittest.mock import patch, MagicMock, PropertyMock
from model_bakery import baker

User = get_user_model()

def create_test_file():
    """Helper to create a test file for transcriptions using real sample audio"""
    import os
    from pathlib import Path
    
    # Use real sample audio file if available
    sample_path = Path(__file__).parent.parent.parent / 'samples' / 'simple-riff.wav'
    if sample_path.exists():
        with open(sample_path, 'rb') as f:
            return ContentFile(f.read(), 'simple-riff.wav')
    else:
        # Fallback to fake data
        return ContentFile(b'test audio data', 'test.wav')


@pytest.mark.django_db
class TestExportView:
    """Test the main export view"""
    
    def test_export_view_get_request(self, django_client):
        """Test GET request to export view shows export options"""
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        
        response = django_client.get(reverse('transcriber:export', kwargs={'pk': transcription.pk}))
        
        assert response.status_code == 200
        assert 'transcription' in response.context
        assert response.context['transcription'].id == transcription.id
        
    def test_export_view_access_denied_for_other_users(self, django_client):
        """Test access control for export view"""
        owner = baker.make(User)
        other_user = baker.make(User)
        transcription = baker.make('transcriber.Transcription', user=owner, status='completed', filename='test.wav', original_audio=create_test_file())
        
        django_client.force_login(other_user)
        response = django_client.get(reverse('transcriber:export', kwargs={'pk': transcription.pk}))
        
        assert response.status_code == 403
        
    @patch('transcriber.views.export.generate_export')
    def test_export_post_single_format(self, mock_generate_export, django_client):
        """Test POST request to generate single format export"""
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        
        # Mock the Celery task
        mock_task = MagicMock()
        mock_task.id = 'export-task-id'
        mock_generate_export.delay.return_value = mock_task
        
        response = django_client.post(
            reverse('transcriber:export', kwargs={'pk': transcription.pk}),
            {'format': 'musicxml'}
        )
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['task_id'] == 'export-task-id'
        assert data['format'] == 'musicxml'
        assert data['status'] == 'processing'
        mock_generate_export.delay.assert_called_once_with(str(transcription.id), 'musicxml')
        
    def test_export_with_existing_export(self, django_client):
        """Test export when export already exists"""
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        existing_export = baker.make('transcriber.TabExport', format='musicxml', transcription=transcription)
        
        response = django_client.post(
            reverse('transcriber:export', kwargs={'pk': transcription.pk}),
            {'format': 'musicxml'}
        )
        
        assert response.status_code == 302  # Redirect to download
        assert f'/download/{existing_export.id}/' in response.url
        
    @patch('transcriber.views.export.generate_export')
    def test_export_post_all_formats(self, mock_generate_export, django_client):
        """Test POST request to generate all formats"""
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        
        # Mock the Celery task
        mock_task = MagicMock()
        mock_task.id = 'export-task-id'
        mock_generate_export.delay.return_value = mock_task
        
        response = django_client.post(
            reverse('transcriber:export', kwargs={'pk': transcription.pk}),
            {'format': 'all'}
        )
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['status'] == 'processing_all'
        assert 'tasks' in data
        assert len(data['tasks']) == 4  # musicxml, gp5, midi, ascii
        
    @patch('transcriber.views.export.generate_export')
    def test_export_htmx_request(self, mock_generate_export, django_client):
        """Test export with HTMX returns HTML partial"""
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        
        mock_task = MagicMock()
        mock_task.id = 'export-task-id'
        mock_generate_export.delay.return_value = mock_task
        
        response = django_client.post(
            reverse('transcriber:export', kwargs={'pk': transcription.pk}),
            {'format': 'musicxml'},
            HTTP_HX_REQUEST='true'
        )
        
        assert response.status_code == 200
        assert response['Content-Type'].startswith('text/html')


@pytest.mark.django_db
class TestDownloadView:
    """Test the download view"""
    
    def test_download_export_file(self, django_client):
        """Test downloading an export file"""
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        
        # Create an export with a file
        from transcriber.models import TabExport
        export = TabExport.objects.create(
            transcription=transcription,
            format='musicxml'
        )
        export.file.save('test.xml', ContentFile(b'<?xml version="1.0"?>'))
        
        response = django_client.get(
            reverse('transcriber:download', kwargs={'pk': transcription.pk, 'export_id': export.id})
        )
        
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/xml'
        assert 'attachment' in response['Content-Disposition']
        assert b'<?xml version="1.0"?>' in response.content
        
    def test_download_missing_file_returns_404(self, django_client):
        """Test downloading export without file returns 404"""
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        export = baker.make('transcriber.TabExport', format='musicxml', transcription=transcription)
        
        response = django_client.get(
            reverse('transcriber:download', kwargs={'pk': transcription.pk, 'export_id': export.id})
        )
        
        assert response.status_code == 404
        
    def test_download_access_control(self, django_client):
        """Test access control for downloads"""
        owner = baker.make(User)
        other_user = baker.make(User)
        transcription = baker.make('transcriber.Transcription', user=owner, status='completed', filename='test.wav', original_audio=create_test_file())
        export = baker.make('transcriber.TabExport', format='musicxml', transcription=transcription)
        
        django_client.force_login(other_user)
        response = django_client.get(
            reverse('transcriber:download', kwargs={'pk': transcription.pk, 'export_id': export.id})
        )
        
        assert response.status_code == 403
        
    def test_download_different_formats(self, django_client):
        """Test downloading different export formats sets correct content type"""
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        
        # Test different formats
        formats_and_types = [
            ('musicxml', 'application/xml'),
            ('gp5', 'application/x-guitar-pro'),
            ('midi', 'audio/midi'),
            ('pdf', 'application/pdf'),
            ('ascii', 'text/plain'),
        ]
        
        for format_type, content_type in formats_and_types:
            from transcriber.models import TabExport
            export = TabExport.objects.create(
                transcription=transcription,
                format=format_type
            )
            export.file.save(f'test.{format_type}', ContentFile(b'test content'))
            
            response = django_client.get(
                reverse('transcriber:download', kwargs={'pk': transcription.pk, 'export_id': export.id})
            )
            
            assert response.status_code == 200
            assert response['Content-Type'] == content_type


@pytest.mark.django_db
class TestExportMusicXMLView:
    """Test the MusicXML export view"""
    
    def test_export_musicxml_with_stored_content(self, django_client):
        """Test MusicXML export with stored content"""
        transcription = baker.make(
            'transcriber.Transcription',
            status='completed',
            filename='test.wav',
            original_audio=create_test_file(),
            musicxml_content='<?xml version="1.0"?><score-partwise></score-partwise>'
        )
        
        response = django_client.get(
            reverse('transcriber:export_musicxml', kwargs={'pk': transcription.pk}),
            {'content': '1'}
        )
        
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/xml'
        assert b'<score-partwise>' in response.content
        
    def test_export_musicxml_public_transcription(self, django_client):
        """Test MusicXML export for public transcription"""
        owner = baker.make(User)
        other_user = baker.make(User)
        transcription = baker.make(
            'transcriber.Transcription',
            user=owner,
            status='completed',
            filename='test.wav',
            original_audio=create_test_file(),
            is_public=True,
            musicxml_content='<?xml version="1.0"?><score-partwise></score-partwise>'
        )
        
        django_client.force_login(other_user)
        response = django_client.get(
            reverse('transcriber:export_musicxml', kwargs={'pk': transcription.pk}),
            {'content': '1'}
        )
        
        assert response.status_code == 200
        
    def test_export_musicxml_private_access_denied(self, django_client):
        """Test MusicXML export access denied for private transcription"""
        owner = baker.make(User)
        other_user = baker.make(User)
        transcription = baker.make(
            'transcriber.Transcription',
            user=owner,
            status='completed',
            filename='test.wav',
            original_audio=create_test_file(),
            is_public=False
        )
        
        django_client.force_login(other_user)
        response = django_client.get(
            reverse('transcriber:export_musicxml', kwargs={'pk': transcription.pk})
        )
        
        assert response.status_code == 403
        
    @patch('transcriber.views.export.generate_basic_musicxml_from_guitar_notes')
    def test_export_musicxml_generates_from_guitar_notes(self, mock_generate, django_client):
        """Test MusicXML generation from guitar notes"""
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        mock_generate.return_value = '<?xml version="1.0"?><generated></generated>'
        
        response = django_client.get(
            reverse('transcriber:export_musicxml', kwargs={'pk': transcription.pk}),
            {'content': '1'}
        )
        
        assert response.status_code == 200
        assert b'<generated>' in response.content
        mock_generate.assert_called_once_with(transcription)
        
    def test_export_musicxml_with_existing_export_file(self, django_client):
        """Test MusicXML with existing export file"""
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        
        # Create an export with a file
        from transcriber.models import TabExport
        export = TabExport.objects.create(
            transcription=transcription,
            format='musicxml'
        )
        export.file.save('test.xml', ContentFile(b'<?xml version="1.0"?><from-file></from-file>'))
        
        response = django_client.get(
            reverse('transcriber:export_musicxml', kwargs={'pk': transcription.pk}),
            {'content': '1'}
        )
        
        assert response.status_code == 200
        assert b'<from-file>' in response.content
        
    @patch('transcriber.views.export.generate_basic_musicxml_from_guitar_notes')
    def test_export_musicxml_fallback_on_error(self, mock_generate, django_client):
        """Test MusicXML returns basic XML on generation error"""
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        mock_generate.side_effect = Exception('Generation failed')
        
        response = django_client.get(
            reverse('transcriber:export_musicxml', kwargs={'pk': transcription.pk}),
            {'content': '1'}
        )
        
        assert response.status_code == 200
        assert b'<score-partwise version="3.1">' in response.content  # Basic fallback XML


@pytest.mark.django_db
class TestClearExportsView:
    """Test the clear exports view"""
    
    def test_clear_all_exports(self, django_client):
        """Test clearing all exports for a transcription"""
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        
        # Create multiple exports with files
        from transcriber.models import TabExport
        for format_type in ['musicxml', 'gp5', 'midi']:
            export = TabExport.objects.create(
                transcription=transcription,
                format=format_type
            )
            export.file.save(f'test.{format_type}', ContentFile(b'test content'))
        
        response = django_client.post(
            reverse('transcriber:clear_exports', kwargs={'pk': transcription.pk})
        )
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['status'] == 'success'
        
        # Verify exports are deleted
        assert transcription.exports.count() == 0
        
    def test_clear_exports_htmx_returns_empty(self, django_client):
        """Test clear exports with HTMX returns empty response"""
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        export = baker.make('transcriber.TabExport', format='musicxml', transcription=transcription)
        
        response = django_client.post(
            reverse('transcriber:clear_exports', kwargs={'pk': transcription.pk}),
            HTTP_HX_REQUEST='true'
        )
        
        assert response.status_code == 200
        assert response.content == b''
        
    def test_clear_exports_access_control(self, django_client):
        """Test access control for clearing exports"""
        owner = baker.make(User)
        other_user = baker.make(User)
        transcription = baker.make('transcriber.Transcription', user=owner, status='completed', filename='test.wav', original_audio=create_test_file())
        
        django_client.force_login(other_user)
        response = django_client.post(
            reverse('transcriber:clear_exports', kwargs={'pk': transcription.pk})
        )
        
        assert response.status_code == 403