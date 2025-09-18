"""
Unit tests for multi-track transcription tasks
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from transcriber.tasks import (
    separate_audio_stems,
    transcribe_guitar_stem,
    transcribe_bass_stem,
    transcribe_drums_stem,
    transcribe_vocals_stem,
    combine_transcriptions,
    generate_multitrack_exports,
    process_multitrack_simple
)


class TestMultiTrackTasks:
    """Test multi-track transcription task functions"""

    @pytest.fixture
    def mock_transcription(self):
        """Mock transcription object"""
        transcription = MagicMock()
        transcription.id = 1
        transcription.original_audio.path = "/fake/path/audio.wav"
        transcription.separated_stems = {}
        return transcription

    @pytest.fixture
    def mock_stems(self):
        """Mock separated audio stems"""
        return {
            'drums': '/tmp/drums.wav',
            'bass': '/tmp/bass.wav',
            'other': '/tmp/guitar.wav',
            'vocals': '/tmp/vocals.wav'
        }

    @pytest.fixture
    def mock_transcription_result(self):
        """Mock transcription result"""
        return {
            'instrument': 'guitar',
            'notes': [
                {'midi_note': 64, 'start_time': 0.0, 'end_time': 1.0, 'velocity': 80}
            ],
            'tab_data': {'measures': []},
            'confidence': 0.8
        }

    @patch('transcriber.models.Transcription.objects.get')
    @patch('transcriber.tasks.DemucsTool')
    @patch('asyncio.new_event_loop')
    def test_separate_audio_stems(self, mock_loop, mock_demucs_class, mock_get, mock_transcription, mock_stems):
        """Test audio stem separation"""
        # Setup mocks
        mock_get.return_value = mock_transcription
        mock_demucs = MagicMock()
        mock_demucs_class.return_value = mock_demucs

        # Mock async loop
        mock_event_loop = MagicMock()
        mock_loop.return_value = mock_event_loop
        mock_event_loop.run_until_complete.return_value = mock_stems

        # Create task instance
        task = separate_audio_stems()
        task.update_state = MagicMock()

        # Execute
        result = task.run(1)

        # Verify
        assert result == mock_stems
        mock_demucs.separate.assert_called_once()
        mock_transcription.save.assert_called_once()

    @patch('transcriber.models.Transcription.objects.get')
    @patch('transcriber.tasks.BasicPitchTool')
    @patch('transcriber.tasks._get_tab_generator')
    @patch('asyncio.new_event_loop')
    def test_transcribe_guitar_stem(self, mock_loop, mock_tab_gen, mock_bp_class, mock_get,
                                  mock_transcription, mock_transcription_result):
        """Test guitar stem transcription"""
        # Setup mocks
        mock_get.return_value = mock_transcription
        mock_bp = MagicMock()
        mock_bp_class.return_value = mock_bp

        # Mock async loop
        mock_event_loop = MagicMock()
        mock_loop.return_value = mock_event_loop
        mock_event_loop.run_until_complete.return_value = {
            'notes': mock_transcription_result['notes'],
            'confidence': 0.8
        }

        # Mock tab generator
        mock_tab_gen_class = MagicMock()
        mock_tab_gen.return_value = mock_tab_gen_class
        mock_tab_gen_instance = MagicMock()
        mock_tab_gen_class.return_value = mock_tab_gen_instance
        mock_tab_gen_instance.generate_optimized_tabs.return_value = {'measures': []}

        # Create task instance
        task = transcribe_guitar_stem()
        task.update_state = MagicMock()

        # Execute
        result = task.run('/tmp/guitar.wav', 1)

        # Verify
        assert result['instrument'] == 'guitar'
        assert result['notes'] == mock_transcription_result['notes']
        assert 'tab_data' in result
        mock_bp.transcribe.assert_called_once()

    @patch('transcriber.models.Transcription.objects.get')
    @patch('transcriber.models.Track.objects.create')
    def test_combine_transcriptions(self, mock_track_create, mock_get, mock_transcription):
        """Test combining transcription results"""
        # Setup mocks
        mock_get.return_value = mock_transcription
        mock_track = MagicMock()
        mock_track.id = 1
        mock_track_create.return_value = mock_track

        # Mock transcription results
        results = [
            {'instrument': 'guitar', 'tab_data': {'measures': []}, 'confidence': 0.8},
            {'instrument': 'bass', 'tab_data': {'measures': []}, 'confidence': 0.7}
        ]

        # Create task instance
        task = combine_transcriptions()
        task.update_state = MagicMock()

        # Execute
        result = task.run(results, 1)

        # Verify
        assert result['transcription_id'] == 1
        assert result['tracks_created'] == 2
        assert 'guitar' in result['instruments']
        assert 'bass' in result['instruments']
        assert mock_track_create.call_count == 2

    @patch('transcriber.models.Transcription.objects.get')
    @patch('transcriber.models.Track.objects.filter')
    @patch('transcriber.tasks._get_export_manager')
    def test_generate_multitrack_exports(self, mock_export_mgr, mock_track_filter, mock_get, mock_transcription):
        """Test multi-track export generation"""
        # Setup mocks
        mock_get.return_value = mock_transcription
        mock_tracks = [MagicMock(), MagicMock()]
        mock_track_filter.return_value = mock_tracks

        mock_export_manager_class = MagicMock()
        mock_export_mgr.return_value = mock_export_manager_class
        mock_export_manager = MagicMock()
        mock_export_manager_class.return_value = mock_export_manager

        mock_export_manager.generate_multitrack_musicxml.return_value = "<musicxml/>"
        mock_export_manager.generate_multitrack_midi.return_value = "/tmp/multi.mid"

        # Create task instance
        task = generate_multitrack_exports()
        task.update_state = MagicMock()

        combine_result = {'transcription_id': 1}

        # Execute
        result = task.run(combine_result)

        # Verify
        assert result['transcription_id'] == 1
        assert 'exports' in result
        mock_export_manager.generate_multitrack_musicxml.assert_called_once_with(mock_tracks)
        mock_export_manager.generate_multitrack_midi.assert_called_once_with(mock_tracks)

    @patch('transcriber.models.Transcription.objects.get')
    @patch('transcriber.tasks.separate_audio_stems')
    @patch('transcriber.tasks.transcribe_guitar_stem')
    @patch('transcriber.tasks.transcribe_bass_stem')
    @patch('transcriber.tasks.combine_transcriptions')
    @patch('transcriber.tasks.generate_multitrack_exports')
    @patch('celery.group')
    def test_process_multitrack_simple(self, mock_group, mock_gen_exports, mock_combine,
                                     mock_transcribe_bass, mock_transcribe_guitar,
                                     mock_separate, mock_get, mock_transcription, mock_stems):
        """Test simple multi-track processing workflow"""
        # Setup mocks
        mock_get.return_value = mock_transcription
        mock_separate.return_value = mock_stems

        # Mock parallel task execution
        mock_job = MagicMock()
        mock_group.return_value.apply_async.return_value = mock_job
        mock_job.get.return_value = [
            {'instrument': 'guitar', 'confidence': 0.8},
            {'instrument': 'bass', 'confidence': 0.7}
        ]

        mock_combine.return_value = {'tracks_created': 2, 'instruments': ['guitar', 'bass']}
        mock_gen_exports.return_value = {'exports': {'musicxml': 1000, 'midi': '/tmp/file.mid'}}

        # Create task instance
        task = process_multitrack_simple()
        task.update_state = MagicMock()

        # Execute
        result = task.run(1)

        # Verify
        assert result['transcription_id'] == 1
        assert result['status'] == 'completed'
        assert result['tracks'] == 2
        mock_separate.assert_called_once_with(1)
        mock_combine.assert_called_once()
        mock_gen_exports.assert_called_once()

    def test_stem_transcription_error_handling(self, mock_transcription):
        """Test error handling in stem transcription tasks"""
        with patch('transcriber.models.Transcription.objects.get', side_effect=Exception("DB Error")):
            task = transcribe_guitar_stem()

            with pytest.raises(Exception, match="DB Error"):
                task.run('/fake/path.wav', 1)

    @patch('transcriber.models.Transcription.objects.get')
    def test_empty_stems_handling(self, mock_get, mock_transcription):
        """Test handling when no stems are available"""
        mock_get.return_value = mock_transcription

        task = process_multitrack_simple()
        task.update_state = MagicMock()

        with patch('transcriber.tasks.separate_audio_stems') as mock_separate:
            mock_separate.return_value = {}  # No stems

            with patch('transcriber.tasks.combine_transcriptions') as mock_combine:
                mock_combine.return_value = {'tracks_created': 0, 'instruments': []}

                with patch('transcriber.tasks.generate_multitrack_exports') as mock_exports:
                    mock_exports.return_value = {'exports': {}}

                    result = task.run(1)

                    assert result['tracks'] == 0
                    assert result['exports'] == []