"""
Unit tests for the new advanced transcription tasks
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from model_bakery import baker

from transcriber.tasks import (
    process_transcription_advanced,
    generate_premium_export,
    generate_variants_advanced,
    cleanup_old_transcriptions,
    update_usage_analytics
)
from transcriber.models import Transcription, Track, TabExport, UserProfile, ConversionEvent
from transcriber.services.advanced_transcription_service import AdvancedTranscriptionResult
from tests.test_helpers import create_test_audio_file


@pytest.mark.django_db
class TestAdvancedTasks:
    """Test new advanced transcription tasks"""

    @pytest.fixture
    def sample_transcription(self):
        """Create a sample transcription for testing"""
        return baker.make(
            Transcription,
            filename="test_song.wav",
            original_audio=create_test_audio_file("test_song.wav"),
            status='pending'
        )

    @pytest.fixture
    def premium_user(self):
        """Create a premium user"""
        user = baker.make('auth.User')
        baker.make(UserProfile, user=user, subscription_tier='premium', can_export=True)
        return user

    @pytest.fixture
    def mock_advanced_result(self):
        """Mock advanced transcription result"""
        return AdvancedTranscriptionResult(
            tracks={
                'guitar': [
                    {'midi_note': 64, 'start_time': 0.0, 'end_time': 1.0, 'velocity': 80, 'confidence': 0.9}
                ],
                'bass': [
                    {'midi_note': 40, 'start_time': 0.0, 'end_time': 2.0, 'velocity': 90, 'confidence': 0.85}
                ]
            },
            tempo=120.0,
            key='C Major',
            time_signature='4/4',
            complexity='moderate',
            detected_instruments=['guitar', 'bass'],
            confidence_scores={'guitar': 0.9, 'bass': 0.85},
            overall_confidence=0.875,
            accuracy_score=0.92,
            models_used={'guitar': 'MT3', 'bass': 'MT3'},
            processing_times={'mt3': 2.5, 'total': 3.0},
            total_processing_time=3.0,
            mt3_result=None,
            omnizart_results={},
            crepe_result=None,
            chord_progression=[],
            beat_tracking=[],
            duration=60.0,
            sample_rate=44100,
            service_version='2.0.0',
            timestamp='2024-01-01T12:00:00'
        )

    @patch('transcriber.tasks.get_advanced_service')
    @patch('transcriber.services.metrics_service.start_task_metrics')
    @patch('transcriber.services.metrics_service.complete_task_metrics')
    @patch('transcriber.services.metrics_service.update_progress')
    def test_process_transcription_advanced_success(self, mock_progress, mock_complete, mock_start, 
                                                   mock_service, sample_transcription, mock_advanced_result):
        """Test successful advanced transcription processing"""
        # Setup mocks
        mock_advanced_service = MagicMock()
        mock_service.return_value = mock_advanced_service
        
        # Mock the async transcription method
        async def mock_transcribe(*args, **kwargs):
            return mock_advanced_result
        
        mock_advanced_service.transcribe_audio_advanced = mock_transcribe

        # Create task instance
        task = process_transcription_advanced()
        task.request = MagicMock()
        task.request.id = 'test-task-id'
        task.request.retries = 0
        task.update_state = MagicMock()

        # Mock asyncio components
        with patch('asyncio.new_event_loop') as mock_loop_factory:
            mock_loop = MagicMock()
            mock_loop_factory.return_value = mock_loop
            mock_loop.run_until_complete.return_value = mock_advanced_result

            # Execute task
            result = task.run(str(sample_transcription.id), accuracy_mode='maximum')

        # Verify success
        assert result['status'] == 'success'
        assert result['accuracy_score'] == 0.92
        assert len(result['instruments_detected']) == 2

        # Verify transcription was updated
        sample_transcription.refresh_from_db()
        assert sample_transcription.status == 'completed'
        assert sample_transcription.accuracy_score == 0.92
        assert sample_transcription.processing_model_version == 'advanced_v2.0'

        # Verify tracks were created
        tracks = Track.objects.filter(transcription=sample_transcription)
        assert tracks.count() == 2
        
        # Verify metrics tracking
        mock_start.assert_called_once()
        mock_complete.assert_called_once()

    @patch('transcriber.tasks.ExportManager')
    @patch('transcriber.services.metrics_service.start_task_metrics')
    @patch('transcriber.services.metrics_service.complete_task_metrics')
    def test_generate_premium_export_success(self, mock_complete, mock_start, mock_export_mgr,
                                           sample_transcription, premium_user):
        """Test premium export generation"""
        # Setup mocks
        mock_manager = MagicMock()
        mock_export_mgr.return_value = mock_manager
        mock_manager.export_gp5.return_value = '/tmp/test.gp5'

        # Mock file operations
        with patch('os.path.exists', return_value=True), \
             patch('os.path.getsize', return_value=1024), \
             patch('os.remove'), \
             patch('builtins.open', mock_create_file_context(b'mock gp5 content')):

            # Create task instance
            task = generate_premium_export()
            task.request = MagicMock()
            task.request.id = 'export-task-id'
            task.update_state = MagicMock()

            # Execute
            result = task.run(str(sample_transcription.id), 'gp5', premium_user.id)

        # Verify success
        assert result['status'] == 'success'
        assert result['format'] == 'gp5'

        # Verify export record was created
        exports = TabExport.objects.filter(transcription=sample_transcription, format='gp5')
        assert exports.count() == 1

        # Verify conversion event was tracked
        events = ConversionEvent.objects.filter(
            user=premium_user,
            event_type='exported_file',
            feature_name='gp5'
        )
        assert events.count() == 1

    def test_generate_premium_export_permission_denied(self, sample_transcription):
        """Test export fails for users without permission"""
        # Create free user
        free_user = baker.make('auth.User')
        baker.make(UserProfile, user=free_user, subscription_tier='free', can_export=False)

        task = generate_premium_export()
        task.request = MagicMock()
        task.request.id = 'export-task-id'
        task.update_state = MagicMock()

        # Should raise permission error
        result = task.run(str(sample_transcription.id), 'gp5', free_user.id)
        
        assert result['status'] == 'error'
        assert 'permission' in result['message'].lower()

    @patch('transcriber.tasks.VariantGenerator')
    def test_generate_variants_advanced(self, mock_variant_gen, sample_transcription, premium_user):
        """Test advanced variant generation"""
        # Setup mocks
        mock_generator = MagicMock()
        mock_variant_gen.return_value = mock_generator
        
        mock_variants = [MagicMock(), MagicMock()]  # 2 variants
        mock_generator.generate_all_variants.return_value = mock_variants

        # Create task instance
        task = generate_variants_advanced()
        task.request = MagicMock()
        task.request.id = 'variant-task-id'

        # Execute
        result = task.run(str(sample_transcription.id), premium_user.id)

        # Verify success
        assert result['status'] == 'success'
        assert result['variants_count'] == 2

        # Verify conversion event was tracked
        events = ConversionEvent.objects.filter(
            user=premium_user,
            event_type='generated_variants'
        )
        assert events.count() == 1

    def test_cleanup_old_transcriptions(self):
        """Test cleanup of old transcriptions"""
        # Create old transcription (35 days ago)
        from django.utils import timezone
        from datetime import timedelta
        
        old_date = timezone.now() - timedelta(days=35)
        
        old_transcription = baker.make(
            Transcription,
            status='completed',
            created_at=old_date
        )
        
        # Create recent transcription (should not be deleted)
        recent_transcription = baker.make(
            Transcription,
            status='completed'
        )

        # Execute cleanup
        result = cleanup_old_transcriptions()

        # Verify old transcription was deleted
        assert not Transcription.objects.filter(id=old_transcription.id).exists()
        assert Transcription.objects.filter(id=recent_transcription.id).exists()

        # Verify result
        assert result['transcriptions_cleaned'] >= 1

    def test_update_usage_analytics(self, premium_user):
        """Test usage analytics update task"""
        # Create transcription for today
        transcription = baker.make(
            Transcription,
            user=premium_user,
            status='completed',
            accuracy_score=0.9
        )

        # Create conversion events
        baker.make(ConversionEvent, user=premium_user, event_type='attempted_export')
        baker.make(ConversionEvent, user=premium_user, event_type='upgraded_premium')

        # Execute analytics update
        result = update_usage_analytics()

        # Verify analytics were updated
        from transcriber.models import UsageAnalytics
        analytics = UsageAnalytics.objects.filter(user=premium_user).first()
        
        assert analytics is not None
        assert analytics.transcriptions_created >= 1
        assert analytics.exports_attempted >= 1


# Helper functions for tests

def mock_create_file_context(content):
    """Create a mock file context manager"""
    from unittest.mock import mock_open
    return mock_open(read_data=content)


@pytest.mark.django_db
class TestRateLimitingIntegration:
    """Test rate limiting integration with tasks"""

    def test_rate_limit_checking_in_tasks(self, sample_transcription):
        """Test that tasks check rate limits before processing"""
        with patch('transcriber.services.rate_limiter.check_openai_rate_limit') as mock_check:
            mock_check.return_value = (False, 60)  # Rate limited, retry in 60s

            task = process_transcription_advanced()
            task.request = MagicMock()
            task.request.id = 'rate-limited-task'
            task.request.retries = 0
            task.retry = MagicMock(side_effect=Exception("Retry called"))

            # Should call retry due to rate limiting
            with pytest.raises(Exception, match="Retry called"):
                task.run(str(sample_transcription.id))

            # Verify rate limit was checked
            mock_check.assert_called_once()
            task.retry.assert_called_once()

    def test_openai_usage_recording(self, sample_transcription, mock_advanced_result):
        """Test that OpenAI usage is properly recorded"""
        with patch('transcriber.services.rate_limiter.check_openai_rate_limit', return_value=(True, None)), \
             patch('transcriber.services.rate_limiter.record_openai_request') as mock_record, \
             patch('transcriber.tasks.get_advanced_service') as mock_service:

            # Mock service
            mock_advanced_service = MagicMock()
            mock_service.return_value = mock_advanced_service
            
            async def mock_transcribe(*args, **kwargs):
                return mock_advanced_result
            mock_advanced_service.transcribe_audio_advanced = mock_transcribe

            # Mock asyncio
            with patch('asyncio.new_event_loop') as mock_loop_factory:
                mock_loop = MagicMock()
                mock_loop_factory.return_value = mock_loop
                mock_loop.run_until_complete.return_value = mock_advanced_result

                task = process_transcription_advanced()
                task.request = MagicMock()
                task.request.id = 'usage-tracking-task'
                task.request.retries = 0
                task.update_state = MagicMock()

                try:
                    task.run(str(sample_transcription.id))
                except:
                    pass  # May fail due to mocking, but usage should still be recorded

            # Verify OpenAI usage was recorded
            mock_record.assert_called_once()

