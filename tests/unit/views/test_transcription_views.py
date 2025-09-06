"""
Tests for transcription views
"""
import json
import pytest
from django.test import Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from unittest.mock import patch, MagicMock, PropertyMock
from model_bakery import baker
from django.core.files.base import ContentFile

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
class TestTranscriptionDetailView:
    """Test the transcription detail view"""
    
    def test_detail_view_with_completed_transcription(self, django_client):
        """Test detail view with a completed transcription"""
        from django.core.files.base import ContentFile
        user = baker.make(User)
        # Create transcription with minimal file
        transcription = baker.make('transcriber.Transcription',
                                  user=user,
                                  status='completed',
                                  filename='test.wav',
                                  original_audio=create_test_file())
        
        django_client.force_login(user)
        response = django_client.get(reverse('transcriber:detail', kwargs={'pk': transcription.pk}))
        
        assert response.status_code == 200
        assert 'transcription' in response.context
        assert response.context['transcription'].id == transcription.id
        assert 'variants' in response.context
        assert 'metrics' in response.context
        
    def test_detail_view_anonymous_transcription(self, django_client):
        """Test detail view with an anonymous transcription"""
        transcription = baker.make('transcriber.Transcription',
                                  status='completed',
                                  filename='test.wav', original_audio=create_test_file())
        
        response = django_client.get(reverse('transcriber:detail', kwargs={'pk': transcription.pk}))
        
        assert response.status_code == 200
        assert response.context['transcription'].id == transcription.id
        
    def test_detail_view_access_denied_for_other_users(self, django_client):
        """Test that users cannot access other users' transcriptions"""
        owner = baker.make(User)
        other_user = baker.make(User)
        transcription = baker.make('transcriber.Transcription', user=owner, status='completed', filename='test.wav', original_audio=create_test_file())
        
        django_client.force_login(other_user)
        response = django_client.get(reverse('transcriber:detail', kwargs={'pk': transcription.pk}))
        
        assert response.status_code == 403
        
    def test_detail_view_superuser_can_access_any(self, django_client):
        """Test that superusers can access any transcription"""
        owner = baker.make(User)
        superuser = baker.make(User, is_superuser=True)
        transcription = baker.make('transcriber.Transcription', user=owner, status='completed', filename='test.wav', original_audio=create_test_file())
        
        django_client.force_login(superuser)
        response = django_client.get(reverse('transcriber:detail', kwargs={'pk': transcription.pk}))
        
        assert response.status_code == 200
        assert response.context['transcription'].id == transcription.id
        
    def test_detail_view_with_variants(self, django_client):
        """Test detail view with fingering variants"""
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        from transcriber.models import FingeringVariant
        variant_easy = baker.make('transcriber.FingeringVariant', 
                                 transcription=transcription,
                                 variant_name='easy',
                                 difficulty_score=20.0,
                                 is_selected=True)
        variant_balanced = baker.make('transcriber.FingeringVariant',
                                    transcription=transcription,
                                    variant_name='balanced',
                                    difficulty_score=40.0,
                                    is_selected=False)
        
        response = django_client.get(reverse('transcriber:detail', kwargs={'pk': transcription.pk}))
        
        assert response.status_code == 200
        assert response.context['has_variants'] is True
        assert response.context['selected_variant'] == variant_easy
        variants = response.context['variants']
        assert len(variants) == 2
        
    def test_detail_view_with_exports(self, django_client):
        """Test detail view with existing exports"""
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        from transcriber.models import TabExport
        export_musicxml = baker.make('transcriber.TabExport', 
                                    transcription=transcription,
                                    format='musicxml')
        export_gp5 = baker.make('transcriber.TabExport',
                              transcription=transcription,
                              format='gp5')
        
        response = django_client.get(reverse('transcriber:detail', kwargs={'pk': transcription.pk}))
        
        assert response.status_code == 200
        assert response.context['has_musicxml'] is True
        assert response.context['has_gp5'] is True
        assert response.context['export_musicxml'] == export_musicxml
        assert response.context['export_gp5'] == export_gp5
        
    @patch('transcriber.views.transcription.AsyncResult')
    def test_detail_view_with_processing_task(self, mock_async_result, django_client):
        """Test detail view with a processing transcription and task status"""
        transcription = baker.make('transcriber.Transcription', status='processing', filename='test.wav', original_audio=create_test_file())
        
        # Mock task result
        mock_result = MagicMock()
        mock_result.info = {'status': 'Processing audio...', 'progress': 50}
        mock_async_result.return_value = mock_result
        
        # Set task ID in session
        session = django_client.session
        session[f'task_{transcription.id}'] = 'test-task-id'
        session.save()
        
        response = django_client.get(reverse('transcriber:detail', kwargs={'pk': transcription.pk}))
        
        assert response.status_code == 200
        assert response.context['task_status'] == 'Processing audio...'


@pytest.mark.django_db
class TestTranscriptionStatusView:
    """Test the transcription status view"""
    
    def test_status_view_returns_json_for_regular_request(self, django_client):
        """Test status view returns JSON for non-HTMX requests"""
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        
        response = django_client.get(reverse('transcriber:status', kwargs={'pk': transcription.pk}))
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['id'] == str(transcription.id)
        assert data['status'] == 'completed'
        
    def test_status_view_returns_html_for_htmx(self, django_client):
        """Test status view returns HTML partial for HTMX requests"""
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        
        response = django_client.get(
            reverse('transcriber:status', kwargs={'pk': transcription.pk}),
            HTTP_HX_REQUEST='true'
        )
        
        assert response.status_code == 200
        assert b'transcriber/partials/status.html' not in response.content
        assert response['Content-Type'].startswith('text/html')
        
    @patch('transcriber.views.transcription.AsyncResult')
    def test_status_view_with_processing_task(self, mock_async_result, django_client):
        """Test status view with an active processing task"""
        transcription = baker.make('transcriber.Transcription', status='processing', filename='test.wav', original_audio=create_test_file())
        
        # Mock task result
        mock_result = MagicMock()
        mock_result.state = 'PROGRESS'
        mock_result.info = {'step': 3, 'progress': 40}
        mock_async_result.return_value = mock_result
        
        # Set task ID in session
        session = django_client.session
        session[f'task_{transcription.id}'] = 'test-task-id'
        session.save()
        
        response = django_client.get(
            reverse('transcriber:status', kwargs={'pk': transcription.pk}),
            HTTP_HX_REQUEST='true'
        )
        
        assert response.status_code == 200
        assert response['Content-Type'].startswith('text/html')
        
    def test_status_view_failed_transcription(self, django_client):
        """Test status view with a failed transcription"""
        transcription = baker.make('transcriber.Transcription', status='failed', error_message='Processing error for testing', filename='test.wav', original_audio=create_test_file())
        
        response = django_client.get(reverse('transcriber:status', kwargs={'pk': transcription.pk}))
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['status'] == 'failed'
        assert data['error_message'] == transcription.error_message


@pytest.mark.django_db
class TestDeleteTranscriptionView:
    """Test the delete transcription view"""
    
    def test_delete_own_transcription(self, django_client):
        """Test user can delete their own transcription"""
        user = baker.make(User)
        transcription = baker.make('transcriber.Transcription', user=user, status='completed', filename='test.wav', original_audio=create_test_file())
        
        django_client.force_login(user)
        response = django_client.post(reverse('transcriber:delete', kwargs={'pk': transcription.pk}))
        
        assert response.status_code == 302  # Redirect to dashboard
        from transcriber.models import Transcription
        assert not Transcription.objects.filter(pk=transcription.pk).exists()
        
    def test_delete_anonymous_transcription(self, django_client):
        """Test deleting an anonymous transcription"""
        transcription = baker.make('transcriber.Transcription', status='pending', filename='test.wav', original_audio=create_test_file())
        
        response = django_client.post(reverse('transcriber:delete', kwargs={'pk': transcription.pk}))
        
        assert response.status_code == 302
        from transcriber.models import Transcription
        assert not Transcription.objects.filter(pk=transcription.pk).exists()
        
    def test_delete_with_htmx_returns_204(self, django_client):
        """Test delete with HTMX returns 204 No Content"""
        transcription = baker.make('transcriber.Transcription', status='pending', filename='test.wav', original_audio=create_test_file())
        
        response = django_client.post(
            reverse('transcriber:delete', kwargs={'pk': transcription.pk}),
            HTTP_HX_REQUEST='true'
        )
        
        assert response.status_code == 204
        from transcriber.models import Transcription
        assert not Transcription.objects.filter(pk=transcription.pk).exists()
        
    def test_delete_access_denied_for_other_users(self, django_client):
        """Test users cannot delete other users' transcriptions"""
        owner = baker.make(User)
        other_user = baker.make(User)
        transcription = baker.make('transcriber.Transcription', user=owner, status='completed', filename='test.wav', original_audio=create_test_file())
        
        django_client.force_login(other_user)
        response = django_client.post(reverse('transcriber:delete', kwargs={'pk': transcription.pk}))
        
        assert response.status_code == 403
        from transcriber.models import Transcription
        assert Transcription.objects.filter(pk=transcription.pk).exists()


@pytest.mark.django_db
class TestToggleFavoriteView:
    """Test the toggle favorite view"""
    
    def test_toggle_favorite_adds_to_favorites(self, django_client):
        """Test toggling favorite adds transcription to favorites"""
        user = baker.make(User)
        transcription = baker.make('transcriber.Transcription', user=user, status='completed', filename='test.wav', original_audio=create_test_file())
        
        django_client.force_login(user)
        response = django_client.post(reverse('transcriber:toggle_favorite', kwargs={'pk': transcription.pk}))
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['is_favorite'] is True
        assert transcription in user.profile.favorite_transcriptions.all()
        
    def test_toggle_favorite_removes_from_favorites(self, django_client):
        """Test toggling favorite removes transcription from favorites"""
        user = baker.make(User)
        transcription = baker.make('transcriber.Transcription', user=user, status='completed', filename='test.wav', original_audio=create_test_file())
        user.profile.favorite_transcriptions.add(transcription)
        
        django_client.force_login(user)
        response = django_client.post(reverse('transcriber:toggle_favorite', kwargs={'pk': transcription.pk}))
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['is_favorite'] is False
        assert transcription not in user.profile.favorite_transcriptions.all()
        
    def test_toggle_favorite_requires_login(self, django_client):
        """Test toggle favorite requires authentication"""
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        
        response = django_client.post(reverse('transcriber:toggle_favorite', kwargs={'pk': transcription.pk}))
        
        # Django redirects to login page when auth required
        assert response.status_code == 302
        assert '/accounts/login/' in response.url
        
    def test_toggle_favorite_htmx_returns_html(self, django_client):
        """Test toggle favorite with HTMX returns HTML partial"""
        user = baker.make(User)
        transcription = baker.make('transcriber.Transcription', user=user, status='completed', filename='test.wav', original_audio=create_test_file())
        
        django_client.force_login(user)
        response = django_client.post(
            reverse('transcriber:toggle_favorite', kwargs={'pk': transcription.pk}),
            HTTP_HX_REQUEST='true'
        )
        
        assert response.status_code == 200
        assert response['Content-Type'].startswith('text/html')


@pytest.mark.django_db
class TestReprocessView:
    """Test the reprocess transcription view"""
    
    @patch('transcriber.tasks.process_transcription')
    def test_reprocess_transcription(self, mock_process_task, django_client):
        """Test reprocessing a transcription"""
        user = baker.make(User)
        transcription = baker.make('transcriber.Transcription', user=user, status='failed', error_message='Processing error for testing', filename='test.wav', original_audio=create_test_file())
        
        # Mock the Celery task
        mock_task = MagicMock()
        mock_task.id = 'new-task-id'
        mock_process_task.delay.return_value = mock_task
        
        django_client.force_login(user)
        response = django_client.post(reverse('transcriber:reprocess', kwargs={'pk': transcription.pk}))
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['status'] == 'success'
        assert data['task_id'] == 'new-task-id'
        
        # Verify transcription was reset
        transcription.refresh_from_db()
        assert transcription.status == 'processing'
        assert transcription.error_message == ''
        assert transcription.guitar_notes is None
        
    @patch('transcriber.tasks.process_transcription')
    def test_reprocess_with_htmx(self, mock_process_task, django_client):
        """Test reprocessing with HTMX returns status partial"""
        user = baker.make(User)
        transcription = baker.make('transcriber.Transcription', user=user, status='failed', error_message='Processing error for testing', filename='test.wav', original_audio=create_test_file())
        
        mock_task = MagicMock()
        mock_task.id = 'new-task-id'
        mock_process_task.delay.return_value = mock_task
        
        django_client.force_login(user)
        response = django_client.post(
            reverse('transcriber:reprocess', kwargs={'pk': transcription.pk}),
            HTTP_HX_REQUEST='true'
        )
        
        assert response.status_code == 200
        assert response['Content-Type'].startswith('text/html')
        
    def test_reprocess_requires_login(self, django_client):
        """Test reprocess requires authentication"""
        transcription = baker.make('transcriber.Transcription', status='failed', error_message='Processing error for testing', filename='test.wav', original_audio=create_test_file())
        
        response = django_client.post(reverse('transcriber:reprocess', kwargs={'pk': transcription.pk}))
        
        # Django redirects to login page when auth required
        assert response.status_code == 302
        assert '/accounts/login/' in response.url
        
    def test_reprocess_access_denied_for_other_users(self, django_client):
        """Test users cannot reprocess other users' transcriptions"""
        owner = baker.make(User)
        other_user = baker.make(User)
        transcription = baker.make('transcriber.Transcription', user=owner, status='failed', error_message='Processing error for testing', filename='test.wav', original_audio=create_test_file())
        
        django_client.force_login(other_user)
        response = django_client.post(reverse('transcriber:reprocess', kwargs={'pk': transcription.pk}))
        
        assert response.status_code == 403


@pytest.mark.django_db
class TestGetTaskStatusView:
    """Test the get task status view"""
    
    @patch('transcriber.views.transcription.AsyncResult')
    def test_get_task_status_success(self, mock_async_result, django_client):
        """Test getting task status for successful task"""
        mock_result = MagicMock()
        mock_result.state = 'SUCCESS'
        mock_result.info = {'result': 'Task completed successfully'}
        mock_async_result.return_value = mock_result
        
        response = django_client.get(reverse('transcriber:task_status', kwargs={'task_id': 'test-task-id'}))
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['state'] == 'SUCCESS'
        assert data['result'] == {'result': 'Task completed successfully'}
        
    @patch('transcriber.views.transcription.AsyncResult')
    def test_get_task_status_pending(self, mock_async_result, django_client):
        """Test getting task status for pending task"""
        mock_result = MagicMock()
        mock_result.state = 'PENDING'
        mock_async_result.return_value = mock_result
        
        response = django_client.get(reverse('transcriber:task_status', kwargs={'task_id': 'test-task-id'}))
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['state'] == 'PENDING'
        assert data['status'] == 'Pending...'
        
    @patch('transcriber.views.transcription.AsyncResult')
    def test_get_task_status_progress(self, mock_async_result, django_client):
        """Test getting task status with progress info"""
        mock_result = MagicMock()
        mock_result.state = 'PROGRESS'
        mock_result.info = {'status': 'Processing...', 'current': 50, 'total': 100}
        mock_async_result.return_value = mock_result
        
        response = django_client.get(reverse('transcriber:task_status', kwargs={'task_id': 'test-task-id'}))
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['state'] == 'PROGRESS'
        assert data['status'] == 'Processing...'
        assert data['current'] == 50
        assert data['total'] == 100
        
    @patch('transcriber.views.transcription.AsyncResult')
    def test_get_task_status_failure(self, mock_async_result, django_client):
        """Test getting task status for failed task"""
        mock_result = MagicMock()
        mock_result.state = 'FAILURE'
        mock_result.info = 'Task failed with error'
        mock_async_result.return_value = mock_result
        
        response = django_client.get(reverse('transcriber:task_status', kwargs={'task_id': 'test-task-id'}))
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['state'] == 'FAILURE'
        assert data['status'] == 'Task failed with error'