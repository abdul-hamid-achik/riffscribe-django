"""
Tests for media views
"""
import json
import pytest
from django.test import Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.cache import cache
from django.conf import settings
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
class TestSignedAudioURLView:
    """Test the signed audio URL generation view"""
    
    def setup_method(self):
        """Clear cache before each test"""
        cache.clear()
    
    @patch('transcriber.views.media.SecureMediaStorage')
    def test_generate_signed_url_success(self, mock_storage_class, django_client):
        """Test successful signed URL generation"""
        user = baker.make(User)
        transcription = baker.make('transcriber.Transcription', user=user, status='completed', filename='test.wav', original_audio=create_test_file())
        
        # Mock storage
        mock_storage = MagicMock()
        mock_storage.generate_signed_url.return_value = 'https://signed-url.example.com'
        mock_storage_class.return_value = mock_storage
        
        django_client.force_login(user)
        response = django_client.get(
            reverse('transcriber:media:signed_audio_url', kwargs={'transcription_id': transcription.id})
        )
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['url'] == 'https://signed-url.example.com'
        assert data['expires_in'] == 7200
        assert data['transcription_id'] == str(transcription.id)
        
    @patch('transcriber.views.media.SecureMediaStorage')
    def test_signed_url_cached(self, mock_storage_class, django_client):
        """Test signed URL is cached after first generation"""
        user = baker.make(User)
        transcription = baker.make('transcriber.Transcription', user=user, status='completed', filename='test.wav', original_audio=create_test_file())
        
        # Mock storage
        mock_storage = MagicMock()
        mock_storage.generate_signed_url.return_value = 'https://signed-url.example.com'
        mock_storage_class.return_value = mock_storage
        
        django_client.force_login(user)
        
        # First request
        response1 = django_client.get(
            reverse('transcriber:media:signed_audio_url', kwargs={'transcription_id': transcription.id})
        )
        data1 = json.loads(response1.content)
        assert 'cached' not in data1 or data1['cached'] is False
        
        # Second request should use cache
        response2 = django_client.get(
            reverse('transcriber:media:signed_audio_url', kwargs={'transcription_id': transcription.id})
        )
        data2 = json.loads(response2.content)
        assert data2['cached'] is True
        assert data2['url'] == data1['url']
        
        # Storage should only be called once
        mock_storage.generate_signed_url.assert_called_once()
        
    def test_signed_url_no_audio_file(self, django_client):
        """Test signed URL returns 404 when no audio file exists"""
        transcription = baker.make('transcriber.Transcription', status='pending', filename='test.wav', original_audio=create_test_file())
        transcription.original_audio.name = None
        transcription.save()
        
        response = django_client.get(
            reverse('transcriber:media:signed_audio_url', kwargs={'transcription_id': transcription.id})
        )
        
        assert response.status_code == 404
        data = json.loads(response.content)
        assert data['error'] == 'Audio file not found'
        
    def test_signed_url_transcription_not_found(self, django_client):
        """Test signed URL returns 500 for non-existent transcription (due to exception handling)"""
        response = django_client.get(
            reverse('transcriber:media:signed_audio_url', kwargs={'transcription_id': '00000000-0000-0000-0000-000000000000'})
        )
        
        # View returns 500 due to exception handling, not 404
        assert response.status_code == 500
        
    @patch('transcriber.views.media.SecureMediaStorage')
    def test_signed_url_generation_failure(self, mock_storage_class, django_client):
        """Test handling of signed URL generation failure"""
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        
        # Mock storage to return None (failure)
        mock_storage = MagicMock()
        mock_storage.generate_signed_url.return_value = None
        mock_storage_class.return_value = mock_storage
        
        response = django_client.get(
            reverse('transcriber:media:signed_audio_url', kwargs={'transcription_id': transcription.id})
        )
        
        assert response.status_code == 500
        data = json.loads(response.content)
        assert data['error'] == 'Failed to generate secure URL'
        
    def test_signed_url_permission_check_owner(self, django_client):
        """Test owner can access their transcription's signed URL"""
        user = baker.make(User)
        transcription = baker.make('transcriber.Transcription', user=user, status='completed', filename='test.wav', original_audio=create_test_file())
        
        django_client.force_login(user)
        
        with patch('transcriber.views.media.SecureMediaStorage') as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.generate_signed_url.return_value = 'https://signed-url.example.com'
            mock_storage_class.return_value = mock_storage
            
            response = django_client.get(
                reverse('transcriber:media:signed_audio_url', kwargs={'transcription_id': transcription.id})
            )
            
            assert response.status_code == 200
            
    def test_signed_url_permission_check_anonymous(self, django_client):
        """Test anonymous users can access signed URLs (configurable)"""
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        
        with patch('transcriber.views.media.SecureMediaStorage') as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.generate_signed_url.return_value = 'https://signed-url.example.com'
            mock_storage_class.return_value = mock_storage
            
            response = django_client.get(
                reverse('transcriber:media:signed_audio_url', kwargs={'transcription_id': transcription.id})
            )
            
            # Current implementation allows anonymous access
            assert response.status_code == 200


@pytest.mark.django_db
class TestAudioProxyView:
    """Test the audio proxy view"""
    
    @patch('transcriber.views.media.SecureMediaStorage')
    def test_audio_proxy_production_redirect(self, mock_storage_class, django_client):
        """Test audio proxy generates signed URL and redirects in production"""
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        
        # Mock storage
        mock_storage = MagicMock()
        mock_storage.generate_signed_url.return_value = 'https://signed-url.example.com'
        mock_storage_class.return_value = mock_storage
        
        # Mock production settings
        with patch.object(settings, 'DEBUG', False):
            response = django_client.get(
                reverse('transcriber:media:audio_proxy', kwargs={'transcription_id': transcription.id})
            )
            
            assert response.status_code == 200
            assert b'window.location.href=' in response.content
            assert b'https://signed-url.example.com' in response.content
            
    def test_audio_proxy_development_redirect(self, django_client):
        """Test audio proxy in development with local storage"""
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        
        # Mock development settings with local storage
        with patch.object(settings, 'DEBUG', True):
            with patch.object(settings, 'AWS_S3_ENDPOINT_URL', 'http://localhost:9000'):
                response = django_client.get(
                    reverse('transcriber:media:audio_proxy', kwargs={'transcription_id': transcription.id})
                )
                
                # In development, should redirect to file URL
                assert response.status_code == 302
                
    def test_audio_proxy_no_audio_file(self, django_client):
        """Test audio proxy returns 404 when no audio file"""
        transcription = baker.make('transcriber.Transcription', status='pending', filename='test.wav', original_audio=create_test_file())
        transcription.original_audio.name = None
        transcription.save()
        
        response = django_client.get(
            reverse('transcriber:media:audio_proxy', kwargs={'transcription_id': transcription.id})
        )
        
        assert response.status_code == 404
        
    def test_audio_proxy_permission_denied(self, django_client):
        """Test audio proxy permission check"""
        owner = baker.make(User)
        other_user = baker.make(User)
        transcription = baker.make('transcriber.Transcription', user=owner, status='completed', filename='test.wav', original_audio=create_test_file())
        
        # Mock _has_file_permission to deny access
        with patch('transcriber.views.media._has_file_permission', return_value=False):
            django_client.force_login(other_user)
            response = django_client.get(
                reverse('transcriber:media:audio_proxy', kwargs={'transcription_id': transcription.id})
            )
            
            assert response.status_code == 404
            
    @patch('transcriber.views.media.SecureMediaStorage')
    def test_audio_proxy_storage_error(self, mock_storage_class, django_client):
        """Test audio proxy handles storage errors gracefully"""
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        
        # Mock storage to raise exception
        mock_storage = MagicMock()
        mock_storage.generate_signed_url.side_effect = Exception('Storage error')
        mock_storage_class.return_value = mock_storage
        
        response = django_client.get(
            reverse('transcriber:media:audio_proxy', kwargs={'transcription_id': transcription.id})
        )
        
        assert response.status_code == 404


@pytest.mark.django_db
class TestFilePermissions:
    """Test the file permission checking"""
    
    def test_has_file_permission_owner(self, django_client):
        """Test owner has permission to access files"""
        from transcriber.views.media import _has_file_permission
        user = baker.make(User)
        transcription = baker.make('transcriber.Transcription', user=user, status='completed', filename='test.wav', original_audio=create_test_file())
        
        request = MagicMock()
        request.user = user
        
        assert _has_file_permission(request, transcription) is True
        
    def test_has_file_permission_superuser(self, django_client):
        """Test superuser has permission to access any files"""
        from transcriber.views.media import _has_file_permission
        owner = baker.make(User)
        superuser = baker.make(User, is_superuser=True)
        transcription = baker.make('transcriber.Transcription', user=owner, status='completed', filename='test.wav', original_audio=create_test_file())
        
        request = MagicMock()
        request.user = superuser
        
        assert _has_file_permission(request, transcription) is True
        
    def test_has_file_permission_staff(self, django_client):
        """Test staff has permission to access files"""
        from transcriber.views.media import _has_file_permission
        owner = baker.make(User)
        staff = baker.make(User, is_staff=True)
        transcription = baker.make('transcriber.Transcription', user=owner, status='completed', filename='test.wav', original_audio=create_test_file())
        
        request = MagicMock()
        request.user = staff
        
        assert _has_file_permission(request, transcription) is True
        
    def test_has_file_permission_anonymous(self, django_client):
        """Test anonymous users have permission (current implementation)"""
        from transcriber.views.media import _has_file_permission
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        
        request = MagicMock()
        request.user.is_authenticated = False
        
        # Current implementation allows anonymous access
        assert _has_file_permission(request, transcription) is True
        
    def test_has_file_permission_authenticated_other(self, django_client):
        """Test authenticated users can access others' files (current implementation)"""
        from transcriber.views.media import _has_file_permission
        owner = baker.make(User)
        other_user = baker.make(User)
        transcription = baker.make('transcriber.Transcription', user=owner, status='completed', filename='test.wav', original_audio=create_test_file())
        
        request = MagicMock()
        request.user = other_user
        
        # Current implementation allows all authenticated users
        assert _has_file_permission(request, transcription) is True


@pytest.mark.django_db
class TestGetSecureAudioURL:
    """Test the get_secure_audio_url utility function"""
    
    def test_get_secure_audio_url_no_file(self):
        """Test returns None when no audio file"""
        from transcriber.views.media import get_secure_audio_url
        transcription = baker.make('transcriber.Transcription', status='pending', filename='test.wav', original_audio=create_test_file())
        transcription.original_audio.name = None
        transcription.save()
        
        result = get_secure_audio_url(transcription)
        assert result is None
        
    def test_get_secure_audio_url_development(self):
        """Test returns direct URL in development with local storage"""
        from transcriber.views.media import get_secure_audio_url
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        
        with patch.object(settings, 'DEBUG', True):
            with patch.object(settings, 'AWS_S3_ENDPOINT_URL', 'http://localhost:9000'):
                result = get_secure_audio_url(transcription)
                assert result == transcription.original_audio.url
                
    def test_get_secure_audio_url_production(self):
        """Test returns proxy URL in production"""
        from transcriber.views.media import get_secure_audio_url
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        
        with patch.object(settings, 'DEBUG', False):
            result = get_secure_audio_url(transcription)
            assert f'/media/audio/proxy/{transcription.id}/' in result
            
    def test_get_secure_audio_url_exception_handling(self):
        """Test handles exceptions gracefully"""
        from transcriber.views.media import get_secure_audio_url
        transcription = baker.make('transcriber.Transcription', status='completed', filename='test.wav', original_audio=create_test_file())
        
        # Mock URL reversal to raise exception
        with patch('django.urls.reverse', side_effect=Exception('URL error')):
            result = get_secure_audio_url(transcription)
            assert result is None