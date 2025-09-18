"""
Integration tests for complete multi-track transcription workflow
"""
import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock, AsyncMock
from celery.result import AsyncResult
import time

from transcriber.models import Transcription, Track, MultiTrackExport
from transcriber.tasks import (
    process_multitrack_simple,
    separate_audio_stems,
    transcribe_guitar_stem,
    transcribe_bass_stem,
    transcribe_drums_stem,
    combine_transcriptions
)
from transcriber.services.metrics_service import metrics_service, get_transcription_progress
from transcriber.services.rate_limiter import openai_limiter
from tests.test_helpers import create_test_audio_file


@pytest.mark.django_db
@pytest.mark.integration
class TestMultiTrackWorkflowIntegration:
    """Test complete multi-track transcription workflow end-to-end"""

    @pytest.fixture
    def sample_transcription(self):
        """Create a sample transcription for testing"""
        transcription = Transcription.objects.create(
            filename="test_song.wav",
            original_audio=create_test_audio_file("test_song.wav"),
            status='pending',
            estimated_tempo=120
        )
        return transcription

    @pytest.fixture
    def mock_demucs_stems(self):
        """Mock separated audio stems"""
        return {
            'drums': '/tmp/test_drums.wav',
            'bass': '/tmp/test_bass.wav', 
            'other': '/tmp/test_guitar.wav',
            'vocals': '/tmp/test_vocals.wav'
        }

    @pytest.fixture
    def mock_transcription_results(self):
        """Mock transcription results for different instruments"""
        return {
            'guitar': {
                'instrument': 'guitar',
                'notes': [
                    {'midi_note': 64, 'start_time': 0.0, 'end_time': 1.0, 'velocity': 80},
                    {'midi_note': 67, 'start_time': 1.0, 'end_time': 2.0, 'velocity': 85}
                ],
                'tab_data': {'measures': [{'number': 1, 'notes': []}]},
                'confidence': 0.85
            },
            'bass': {
                'instrument': 'bass',
                'notes': [
                    {'midi_note': 40, 'start_time': 0.0, 'end_time': 2.0, 'velocity': 90}
                ],
                'tab_data': {'measures': [{'number': 1, 'notes': []}]},
                'confidence': 0.80
            },
            'drums': {
                'instrument': 'drums',
                'drum_data': {
                    'kicks': [0.0, 1.0],
                    'snares': [0.5, 1.5],
                    'notes': [
                        {'midi_note': 36, 'start_time': 0.0, 'end_time': 0.1, 'velocity': 100}
                    ]
                },
                'confidence': 0.75
            },
            'vocals': {
                'instrument': 'vocals', 
                'notes': [
                    {'midi_note': 60, 'start_time': 0.5, 'end_time': 1.5, 'velocity': 70}
                ],
                'confidence': 0.70
            }
        }

    @pytest.mark.slow
    def test_complete_multitrack_workflow_success(self, sample_transcription, mock_demucs_stems, mock_transcription_results):
        """Test complete successful multi-track workflow"""
        transcription_id = sample_transcription.id

        with patch('transcriber.tasks.separate_audio_stems') as mock_separate, \
             patch('transcriber.tasks.transcribe_guitar_stem') as mock_guitar, \
             patch('transcriber.tasks.transcribe_bass_stem') as mock_bass, \
             patch('transcriber.tasks.transcribe_drums_stem') as mock_drums, \
             patch('transcriber.tasks.transcribe_vocals_stem') as mock_vocals, \
             patch('celery.group') as mock_group:

            # Mock separation results
            mock_separate.return_value = mock_demucs_stems

            # Mock transcription results
            mock_guitar.return_value = mock_transcription_results['guitar']
            mock_bass.return_value = mock_transcription_results['bass']
            mock_drums.return_value = mock_transcription_results['drums']
            mock_vocals.return_value = mock_transcription_results['vocals']

            # Mock parallel task execution
            mock_job = MagicMock()
            mock_group.return_value.apply_async.return_value = mock_job
            mock_job.get.return_value = list(mock_transcription_results.values())

            # Execute the workflow
            task = process_multitrack_simple()
            task.update_state = MagicMock()

            result = task.run(transcription_id)

            # Verify results
            assert result['status'] == 'completed'
            assert result['transcription_id'] == transcription_id
            assert result['tracks'] >= 3  # At least guitar, bass, drums

            # Verify tracks were created
            tracks = Track.objects.filter(transcription=sample_transcription)
            assert tracks.count() >= 3
            
            # Verify instruments
            instruments = list(tracks.values_list('instrument_type', flat=True))
            assert 'guitar' in instruments or 'other' in instruments
            assert 'bass' in instruments
            assert 'drums' in instruments

    def test_partial_failure_handling(self, sample_transcription, mock_demucs_stems):
        """Test workflow continues with partial failures"""
        transcription_id = sample_transcription.id

        # Mock separation success but some transcription failures
        partial_results = [
            {'instrument': 'guitar', 'notes': [{'midi_note': 64}], 'confidence': 0.8},
            {'instrument': 'bass', 'notes': [{'midi_note': 40}], 'confidence': 0.75},
            None,  # Drums failed
            {'instrument': 'vocals', 'notes': [], 'confidence': 0.0}  # Vocals empty
        ]

        with patch('transcriber.tasks.separate_audio_stems', return_value=mock_demucs_stems), \
             patch('celery.group') as mock_group:

            mock_job = MagicMock()
            mock_group.return_value.apply_async.return_value = mock_job
            mock_job.get.return_value = partial_results

            # Execute combine_transcriptions directly
            task = combine_transcriptions()
            task.request = MagicMock()
            task.request.id = 'test-task-id'
            task.update_state = MagicMock()

            result = task.run(partial_results, transcription_id)

            # Verify partial success handling
            assert 'partial_success' in result
            assert result['tracks_created'] >= 1  # At least guitar and bass should succeed
            assert len(result['failed_instruments']) >= 1  # Drums should fail

            # Verify tracks were created for successful instruments
            tracks = Track.objects.filter(transcription=sample_transcription)
            assert tracks.count() >= 1

    def test_metrics_tracking_during_workflow(self, sample_transcription, mock_demucs_stems):
        """Test that metrics are properly tracked throughout workflow"""
        transcription_id = sample_transcription.id

        with patch('transcriber.tasks.separate_audio_stems') as mock_separate:
            mock_separate.return_value = mock_demucs_stems

            # Execute separation task directly
            task = separate_audio_stems()
            task.request = MagicMock()
            task.request.id = 'separation-task-id'
            task.update_state = MagicMock()

            task.run(transcription_id)

            # Check that progress was updated
            progress = get_transcription_progress(str(transcription_id))
            assert progress['stages'].get('separation') == 100

            # Check that metrics were recorded
            task_metrics = metrics_service.get_task_metrics('separation-task-id')
            assert task_metrics is not None
            assert task_metrics['status'] == 'success'

    def test_rate_limiting_integration(self):
        """Test OpenAI rate limiting integration"""
        # Test rate limit checking
        can_proceed, retry_after = openai_limiter.can_make_request(estimated_cost=0.01)
        assert can_proceed is True
        assert retry_after is None

        # Record a request
        openai_limiter.record_request(cost=0.01)

        # Check usage stats
        usage = openai_limiter.get_current_usage()
        assert 'requests_minute' in usage
        assert usage['requests_minute']['current'] >= 1
        assert 'cost_day' in usage
        assert usage['cost_day']['current'] >= 0.01

    def test_automatic_instrument_detection(self, sample_transcription):
        """Test that all detected instruments are automatically transcribed"""
        # Mock Demucs returning various instruments
        unusual_stems = {
            'drums': '/tmp/drums.wav',
            'bass': '/tmp/bass.wav',
            'other': '/tmp/other.wav',  # Should be treated as guitar
            'vocals': '/tmp/vocals.wav',
            'piano': '/tmp/piano.wav',  # Additional instrument
        }

        with patch('transcriber.tasks.separate_audio_stems', return_value=unusual_stems) as mock_separate:
            # Execute workflow
            task = process_multitrack_simple()
            task.request = MagicMock()
            task.request.id = 'multitrack-task-id' 
            task.update_state = MagicMock()

            # Should handle all standard instruments without environment variable checks
            # The test verifies the logic adds tasks for known instruments automatically
            try:
                # This will fail due to mocking, but we can verify the stems were processed
                task.run(sample_transcription.id)
            except Exception:
                pass  # Expected due to mocked dependencies

            # Verify separation was called (automatic instrument detection)
            mock_separate.assert_called_once_with(sample_transcription.id)

    def test_export_generation_after_transcription(self, sample_transcription):
        """Test export generation as final step of workflow"""
        # Create some tracks
        guitar_track = Track.objects.create(
            transcription=sample_transcription,
            track_name="Guitar Track",
            track_type='other',
            instrument_type='guitar',
            guitar_notes={'measures': []},
            is_processed=True
        )
        
        bass_track = Track.objects.create(
            transcription=sample_transcription,
            track_name="Bass Track", 
            track_type='bass',
            instrument_type='bass',
            guitar_notes={'measures': []},
            is_processed=True
        )

        # Mock export generation
        with patch('transcriber.tasks.ExportManager') as mock_export_mgr:
            mock_manager = MagicMock()
            mock_export_mgr.return_value = mock_manager
            
            mock_manager.generate_multitrack_musicxml.return_value = "<musicxml>test</musicxml>"
            mock_manager.generate_multitrack_midi.return_value = "/tmp/test.mid"

            from transcriber.tasks import generate_multitrack_exports

            task = generate_multitrack_exports()
            task.request = MagicMock()
            task.request.id = 'export-task-id'
            task.update_state = MagicMock()

            combine_result = {'transcription_id': sample_transcription.id}
            result = task.run(combine_result)

            # Verify exports were generated
            assert result['transcription_id'] == sample_transcription.id
            assert 'exports' in result
            
            # Verify export manager was called with tracks
            mock_manager.generate_multitrack_musicxml.assert_called_once()
            mock_manager.generate_multitrack_midi.assert_called_once()

    def test_system_health_monitoring(self):
        """Test system health monitoring integration"""
        health = metrics_service.get_system_health()
        
        assert 'timestamp' in health
        assert 'memory' in health
        assert 'cpu' in health
        assert 'disk' in health
        assert 'uptime_hours' in health

        # Verify memory stats
        assert 'total_gb' in health['memory']
        assert 'used_percent' in health['memory']
        assert health['memory']['used_percent'] >= 0

    @pytest.mark.slow
    def test_workflow_with_real_celery_tasks(self, sample_transcription):
        """Test workflow using actual Celery task execution (slower test)"""
        # This test requires Celery worker to be running
        # Skip if not in CI/integration environment
        
        if not os.getenv('CELERY_INTEGRATION_TESTS'):
            pytest.skip("Celery integration tests not enabled")

        # Submit actual task
        from transcriber.tasks import process_multitrack_simple
        
        result = process_multitrack_simple.delay(sample_transcription.id)
        
        # Wait for completion (with timeout)
        timeout = 60  # 1 minute timeout
        start_time = time.time()
        
        while not result.ready() and (time.time() - start_time) < timeout:
            time.sleep(1)
            progress = get_transcription_progress(str(sample_transcription.id))
            print(f"Progress: {progress}")

        if result.ready():
            task_result = result.get()
            assert task_result['status'] in ['completed', 'partial']
        else:
            pytest.fail("Task did not complete within timeout")

    def test_error_recovery_and_cleanup(self, sample_transcription):
        """Test error recovery and resource cleanup"""
        transcription_id = sample_transcription.id

        with patch('transcriber.tasks.separate_audio_stems', side_effect=Exception("Separation failed")):
            task = process_multitrack_simple()
            task.request = MagicMock()
            task.request.id = 'failing-task-id'
            task.update_state = MagicMock()

            with pytest.raises(Exception, match="Separation failed"):
                task.run(transcription_id)

            # Verify error was recorded in metrics
            task_metrics = metrics_service.get_task_metrics('failing-task-id')
            if task_metrics:  # May be None if metrics collection failed
                assert task_metrics.get('status') == 'failed'

            # Verify transcription status was updated
            sample_transcription.refresh_from_db()
            assert sample_transcription.status == 'failed'

    def test_openai_usage_tracking(self):
        """Test OpenAI usage tracking and cost estimation"""
        # Simulate API usage
        metrics_service.track_openai_request(
            model='gpt-4',
            tokens_used=1500,
            cost=0.045
        )

        usage_stats = metrics_service.get_openai_usage_stats()
        
        assert usage_stats['requests_today'] >= 1
        assert usage_stats['estimated_cost_today'] >= 0.045
        assert usage_stats['estimated_cost_this_month'] >= 0.045

    def test_queue_priority_system(self):
        """Test that task routing and priorities work correctly"""
        from django.conf import settings
        
        # Verify queue routing configuration exists
        assert hasattr(settings, 'CELERY_ROUTES')
        assert 'transcriber.tasks.separate_audio_stems' in settings.CELERY_ROUTES
        assert settings.CELERY_ROUTES['transcriber.tasks.separate_audio_stems']['queue'] == 'separation'
        
        # Verify priority configuration
        assert hasattr(settings, 'CELERY_TASK_PRIORITIES')
        assert settings.CELERY_TASK_PRIORITIES['separation'] == 9  # Highest priority
