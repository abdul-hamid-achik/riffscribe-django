"""
Unit tests for premium features and business model
"""
import pytest
from unittest.mock import patch, MagicMock
from django.test import RequestFactory
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta

from transcriber.models import Transcription, UserProfile, ConversionEvent, Track
from transcriber.views.export import download_gp5, download_midi, download_ascii_tab
from transcriber.views.business_intelligence import (
    transcription_analytics,
    conversion_funnel_analysis,
    my_transcription_history
)
from transcriber.decorators import premium_required, track_conversion_event
from model_bakery import baker


@pytest.mark.django_db
class TestPremiumFeatures:
    """Test premium feature access control and business logic"""

    @pytest.fixture
    def free_user(self):
        """Create a free tier user"""
        user = baker.make(User)
        profile = baker.make(UserProfile, user=user, subscription_tier='free', can_export=False)
        return user

    @pytest.fixture
    def premium_user(self):
        """Create a premium user"""
        user = baker.make(User)
        profile = baker.make(UserProfile, 
            user=user, 
            subscription_tier='premium',
            can_export=True,
            subscription_expires=timezone.now() + timedelta(days=30)
        )
        return user

    @pytest.fixture
    def sample_transcription(self, premium_user):
        """Create a sample transcription"""
        return baker.make(
            Transcription,
            user=premium_user,
            status='completed',
            filename='test_song.wav',
            accuracy_score=0.92,
            processing_model_version='advanced_v2.0',
            detected_instruments=['guitar', 'bass', 'drums'],
            models_used=['MT3', 'Omnizart', 'CREPE']
        )

    @pytest.fixture
    def request_factory(self):
        return RequestFactory()

    def test_premium_decorator_blocks_free_users(self, free_user, sample_transcription, request_factory):
        """Test that premium decorator blocks free users"""
        request = request_factory.get(f'/transcription/{sample_transcription.id}/export/gp5/')
        request.user = free_user
        request.headers = {}  # No HTMX

        response = download_gp5(request, sample_transcription.id)

        # Should redirect to upgrade page
        assert response.status_code in [302, 402]  # Redirect or Payment Required

    def test_premium_decorator_allows_premium_users(self, premium_user, sample_transcription, request_factory):
        """Test that premium decorator allows premium users"""
        request = request_factory.get(f'/transcription/{sample_transcription.id}/export/gp5/')
        request.user = premium_user
        request.headers = {}

        with patch('transcriber.views.export.generate_premium_export') as mock_task:
            mock_task.delay.return_value = MagicMock(id='task-123')
            with patch('transcriber.views.export.render') as mock_render:
                mock_render.return_value = JsonResponse({'status': 'processing'})
                
                response = download_gp5(request, sample_transcription.id)

        # Should proceed with export generation
        mock_task.delay.assert_called_once()

    def test_conversion_event_tracking(self, free_user, sample_transcription, request_factory):
        """Test that conversion events are properly tracked"""
        request = request_factory.get(f'/transcription/{sample_transcription.id}/export/gp5/')
        request.user = free_user
        request.headers = {}

        # Clear existing events
        ConversionEvent.objects.all().delete()

        response = download_gp5(request, sample_transcription.id)

        # Should create conversion event
        events = ConversionEvent.objects.filter(user=free_user, event_type='attempted_export')
        assert events.count() == 1
        
        event = events.first()
        assert event.transcription == sample_transcription
        assert event.feature_name == 'gp5_export'

    def test_user_can_upload_limits(self, free_user, premium_user):
        """Test upload limits for different user tiers"""
        free_profile = free_user.profile
        premium_profile = premium_user.profile

        # Free user should have limited uploads
        assert free_profile.get_monthly_limit() == 3
        assert free_profile.can_upload() == True  # Initially can upload

        # Simulate using up all uploads
        free_profile.uploads_this_month = 3
        free_profile.save()
        assert free_profile.can_upload() == False

        # Premium user should have unlimited
        assert premium_profile.get_monthly_limit() == 999999
        premium_profile.uploads_this_month = 100
        premium_profile.save()
        assert premium_profile.can_upload() == True

    def test_subscription_expiry(self, premium_user):
        """Test subscription expiry handling"""
        profile = premium_user.profile
        
        # Set subscription to expire yesterday
        profile.subscription_expires = timezone.now() - timedelta(days=1)
        profile.save()

        # Should not be able to export anymore
        assert profile.can_export_files() == False

    def test_update_premium_features(self, free_user):
        """Test automatic feature updates based on subscription tier"""
        profile = free_user.profile

        # Test free tier settings
        profile.update_premium_features()
        assert profile.can_export == False
        assert profile.can_use_commercial == False
        assert profile.can_use_api == False
        assert profile.monthly_upload_limit == 3

        # Upgrade to premium
        profile.subscription_tier = 'premium'
        profile.update_premium_features()
        assert profile.can_export == True
        assert profile.can_use_commercial == False
        assert profile.can_use_api == False
        assert profile.monthly_upload_limit == 999999

        # Upgrade to professional
        profile.subscription_tier = 'professional'
        profile.update_premium_features()
        assert profile.can_export == True
        assert profile.can_use_commercial == True
        assert profile.can_use_api == True


@pytest.mark.django_db 
class TestBusinessIntelligence:
    """Test business intelligence and analytics features"""

    @pytest.fixture
    def admin_user(self):
        """Create admin user"""
        return baker.make(User, is_superuser=True)

    @pytest.fixture
    def sample_data(self):
        """Create sample data for analytics"""
        # Create users
        free_user = baker.make(User)
        baker.make(UserProfile, user=free_user, subscription_tier='free')
        
        premium_user = baker.make(User)
        baker.make(UserProfile, user=premium_user, subscription_tier='premium')

        # Create transcriptions
        transcription1 = baker.make(
            Transcription,
            user=free_user,
            status='completed',
            accuracy_score=0.92,
            detected_instruments=['guitar', 'bass']
        )
        
        transcription2 = baker.make(
            Transcription,
            user=premium_user,
            status='completed',
            accuracy_score=0.88,
            detected_instruments=['guitar', 'drums', 'vocals']
        )

        # Create tracks
        baker.make(Track, transcription=transcription1, instrument_type='guitar', confidence_score=0.9)
        baker.make(Track, transcription=transcription1, instrument_type='bass', confidence_score=0.85)
        
        baker.make(Track, transcription=transcription2, instrument_type='guitar', confidence_score=0.88)
        baker.make(Track, transcription=transcription2, instrument_type='drums', confidence_score=0.82)

        # Create conversion events
        baker.make(ConversionEvent, user=free_user, event_type='viewed_transcription', transcription=transcription1)
        baker.make(ConversionEvent, user=free_user, event_type='attempted_export', transcription=transcription1)
        baker.make(ConversionEvent, user=premium_user, event_type='upgraded_premium')

        return {
            'free_user': free_user,
            'premium_user': premium_user,
            'transcription1': transcription1,
            'transcription2': transcription2
        }

    def test_transcription_analytics_view(self, sample_data, request_factory):
        """Test transcription analytics view"""
        transcription = sample_data['transcription1']
        user = sample_data['free_user']
        
        request = request_factory.get(f'/transcription/{transcription.id}/analytics/')
        request.user = user

        response = transcription_analytics(request, transcription.id)

        assert response.status_code == 200
        
        # Parse JSON response
        import json
        data = json.loads(response.content)
        
        assert 'transcription' in data
        assert 'instruments' in data
        assert 'quality_metrics' in data
        assert 'business_value' in data

        # Verify business value section
        assert 'formats_available' in data['business_value']
        assert 'estimated_time_saved' in data['business_value']

    def test_conversion_funnel_analysis(self, admin_user, sample_data, request_factory):
        """Test conversion funnel analytics for admins"""
        request = request_factory.get('/admin/metrics/conversion/')
        request.user = admin_user

        response = conversion_funnel_analysis(request)

        assert response.status_code == 200
        
        import json
        data = json.loads(response.content)
        
        assert 'funnel_stages' in data
        assert 'conversion_rates' in data
        assert 'revenue_metrics' in data
        assert 'recommendations' in data

        # Verify funnel data
        assert data['funnel_stages']['uploads'] >= 0
        assert data['funnel_stages']['signups'] >= 0

    def test_user_transcription_history(self, sample_data, request_factory):
        """Test user transcription history with insights"""
        user = sample_data['premium_user']
        
        request = request_factory.get('/my/transcriptions/')
        request.user = user

        response = my_transcription_history(request)

        assert response.status_code == 200
        
        import json
        data = json.loads(response.content)
        
        assert 'user_stats' in data
        assert 'recent_transcriptions' in data

        # Verify user stats
        stats = data['user_stats']
        assert 'total_transcriptions' in stats
        assert 'subscription_tier' in stats
        assert 'can_export' in stats

    def test_admin_access_control(self, free_user, request_factory):
        """Test that admin-only views properly restrict access"""
        request = request_factory.get('/admin/metrics/conversion/')
        request.user = free_user

        response = conversion_funnel_analysis(request)

        assert response.status_code == 403  # Forbidden

    def test_monthly_limits_decorator(self, free_user):
        """Test monthly limits decorator functionality"""
        profile = free_user.profile
        
        # Simulate user at limit
        profile.uploads_this_month = 3  # At limit
        profile.monthly_upload_limit = 3
        profile.save()

        from transcriber.decorators import check_monthly_limits
        
        # Create a mock view
        @check_monthly_limits
        def mock_view(request):
            return JsonResponse({'success': True})

        request = RequestFactory().get('/')
        request.user = free_user

        response = mock_view(request)

        # Should block with 429 status
        assert response.status_code == 429
        
        import json
        data = json.loads(response.content)
        assert 'Monthly limit exceeded' in data['error']
