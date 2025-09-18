"""
Unit tests for the advanced transcription service with MT3, Omnizart, and CREPE
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from transcriber.services.advanced_transcription_service import (
    AdvancedTranscriptionService,
    AdvancedTranscriptionResult
)
from transcriber.services.mt3_service import MT3TranscriptionResult
from transcriber.services.omnizart_service import OmnizartResult  
from transcriber.services.crepe_service import CREPEResult


@pytest.mark.asyncio
class TestAdvancedTranscriptionService:
    """Test advanced transcription service functionality"""

    @pytest.fixture
    def service(self):
        """Create service instance with mocked dependencies"""
        with patch('transcriber.services.advanced_transcription_service.get_mt3_service'), \
             patch('transcriber.services.advanced_transcription_service.get_omnizart_service'), \
             patch('transcriber.services.advanced_transcription_service.get_crepe_service'):
            return AdvancedTranscriptionService()

    @pytest.fixture
    def mock_mt3_result(self):
        """Mock MT3 transcription result"""
        return MT3TranscriptionResult(
            tracks={
                'guitar': [
                    {'midi_note': 64, 'start_time': 0.0, 'end_time': 1.0, 'duration': 1.0, 'velocity': 80, 'confidence': 0.9}
                ],
                'bass': [
                    {'midi_note': 40, 'start_time': 0.0, 'end_time': 2.0, 'duration': 2.0, 'velocity': 90, 'confidence': 0.85}
                ]
            },
            tempo=120.0,
            time_signature='4/4',
            key_signature='C Major',
            confidence_scores={'guitar': 0.9, 'bass': 0.85},
            total_confidence=0.875,
            processing_time=2.5,
            model_version='mt3_v1'
        )

    @pytest.fixture
    def mock_omnizart_results(self):
        """Mock Omnizart results"""
        return {
            'guitar': OmnizartResult(
                instrument='guitar',
                notes=[
                    {'midi_note': 64, 'start_time': 0.0, 'end_time': 1.0, 'duration': 1.0, 'velocity': 85, 'confidence': 0.88}
                ],
                chords=None,
                beats=None,
                confidence=0.88,
                model_used='omnizart_guitar',
                processing_time=1.8
            ),
            'vocal': OmnizartResult(
                instrument='vocal',
                notes=[
                    {'midi_note': 60, 'start_time': 0.5, 'end_time': 1.5, 'duration': 1.0, 'velocity': 70, 'confidence': 0.82}
                ],
                chords=None,
                beats=None,
                confidence=0.82,
                model_used='omnizart_vocal',
                processing_time=1.5
            )
        }

    @pytest.fixture
    def mock_crepe_result(self):
        """Mock CREPE pitch detection result"""
        return CREPEResult(
            pitches=[261.63, 329.63],  # C4, E4
            confidences=[0.95, 0.92],
            times=[0.0, 1.0],
            notes=[
                {'midi_note': 60, 'start_time': 0.0, 'end_time': 1.0, 'frequency': 261.63, 'confidence': 0.95}
            ],
            average_confidence=0.935,
            processing_time=0.8
        )

    async def test_transcribe_audio_advanced_maximum_mode(self, service, mock_mt3_result, mock_omnizart_results, mock_crepe_result):
        """Test advanced transcription with maximum accuracy mode"""
        # Mock the service methods
        service.mt3_service.transcribe_multitrack = AsyncMock(return_value=mock_mt3_result)
        service.omnizart_service.transcribe_all_instruments = AsyncMock(return_value=mock_omnizart_results)
        service.crepe_service.detect_pitch_with_onsets = AsyncMock(return_value=mock_crepe_result)
        
        # Mock audio metadata
        with patch.object(service, '_get_audio_metadata', return_value={'duration': 60.0, 'sample_rate': 44100}):
            result = await service.transcribe_audio_advanced(
                'test_audio.wav',
                accuracy_mode='maximum',
                use_all_models=True
            )

        # Verify result structure
        assert isinstance(result, AdvancedTranscriptionResult)
        assert 'guitar' in result.tracks
        assert 'bass' in result.tracks
        assert result.overall_confidence > 0.8
        assert result.accuracy_score > 0.0
        assert result.service_version == '2.0.0'
        assert len(result.models_used) > 0

        # Verify all services were called
        service.mt3_service.transcribe_multitrack.assert_called_once()
        service.omnizart_service.transcribe_all_instruments.assert_called_once()
        service.crepe_service.detect_pitch_with_onsets.assert_called_once()

    async def test_transcribe_audio_fast_mode(self, service, mock_mt3_result):
        """Test fast mode uses only MT3"""
        service.mt3_service.transcribe_multitrack = AsyncMock(return_value=mock_mt3_result)
        service.omnizart_service.transcribe_all_instruments = AsyncMock()
        service.crepe_service.detect_pitch_with_onsets = AsyncMock()
        
        with patch.object(service, '_get_audio_metadata', return_value={'duration': 60.0, 'sample_rate': 44100}):
            result = await service.transcribe_audio_advanced(
                'test_audio.wav',
                accuracy_mode='fast',
                use_all_models=False
            )

        # Verify only MT3 was used
        service.mt3_service.transcribe_multitrack.assert_called_once()
        service.omnizart_service.transcribe_all_instruments.assert_not_called()
        service.crepe_service.detect_pitch_with_onsets.assert_not_called()

        # Verify result
        assert isinstance(result, AdvancedTranscriptionResult)
        assert len(result.tracks) == 2  # guitar and bass from mock

    async def test_merge_omnizart_results(self, service, mock_omnizart_results):
        """Test merging Omnizart results with MT3"""
        mt3_tracks = {
            'guitar': [
                {'midi_note': 64, 'start_time': 0.0, 'end_time': 1.0, 'confidence': 0.9}
            ]
        }
        mt3_confidence = {'guitar': 0.9}

        merged_tracks, merged_confidence = await service._merge_omnizart_results(
            mt3_tracks, mt3_confidence, mock_omnizart_results
        )

        # Verify guitar track was enhanced
        assert 'guitar' in merged_tracks
        assert 'vocal' in merged_tracks  # New instrument from Omnizart
        
        # Verify confidence was updated (weighted average)
        assert merged_confidence['guitar'] != mt3_confidence['guitar']
        assert 'vocal' in merged_confidence

    async def test_combine_note_lists(self, service):
        """Test intelligent note combination from different models"""
        notes1 = [
            {'midi_note': 64, 'start_time': 0.0, 'end_time': 1.0, 'confidence': 0.9}
        ]
        notes2 = [
            {'midi_note': 64, 'start_time': 0.05, 'end_time': 1.05, 'confidence': 0.95},  # Similar note
            {'midi_note': 67, 'start_time': 2.0, 'end_time': 3.0, 'confidence': 0.8}   # Unique note
        ]

        combined = await service._combine_note_lists(notes1, notes2, mt3_weight=0.5, omnizart_weight=0.5)

        # Should have 2 notes: merged first note + unique second note
        assert len(combined) == 2
        assert combined[0]['midi_note'] == 64  # Merged note
        assert combined[1]['midi_note'] == 67  # Unique Omnizart note

    async def test_crepe_pitch_refinement(self, service, mock_crepe_result):
        """Test CREPE pitch refinement of existing notes"""
        tracks = {
            'guitar': [
                {'midi_note': 64, 'start_time': 0.0, 'end_time': 1.0, 'confidence': 0.8}
            ]
        }

        refined_tracks = await service._refine_with_crepe(tracks, mock_crepe_result)

        # Verify refinement was applied
        assert 'guitar' in refined_tracks
        assert len(refined_tracks['guitar']) > 0

    def test_calculate_accuracy_score(self, service):
        """Test accuracy score calculation"""
        tracks = {
            'guitar': [{'midi_note': 64}],
            'bass': [{'midi_note': 40}]
        }
        confidence_scores = {'guitar': 0.9, 'bass': 0.8}
        metadata = {'complexity': 'moderate'}

        accuracy = service._calculate_accuracy_score(tracks, confidence_scores, metadata)

        assert 0.0 <= accuracy <= 1.0
        assert accuracy > 0.5  # Should be reasonably high with good inputs

    async def test_single_instrument_transcription(self, service, mock_omnizart_results):
        """Test single instrument transcription with specialized models"""
        # Mock MT3 result
        mt3_result = MagicMock()
        mt3_result.tracks = {'guitar': [{'midi_note': 64}]}
        mt3_result.confidence_scores = {'guitar': 0.85}
        
        service.mt3_service.transcribe_multitrack = AsyncMock(return_value=mt3_result)
        service.omnizart_service.transcribe_instrument = AsyncMock(
            return_value=mock_omnizart_results['guitar']
        )

        result = await service.transcribe_single_instrument('test.wav', 'guitar')

        # Verify both models were used
        service.mt3_service.transcribe_multitrack.assert_called_once()
        service.omnizart_service.transcribe_instrument.assert_called_once_with('test.wav', 'guitar')

        # Verify result structure
        assert 'notes' in result
        assert 'confidence' in result
        assert 'models_used' in result

    async def test_error_handling(self, service):
        """Test error handling in transcription process"""
        # Mock MT3 to fail
        service.mt3_service.transcribe_multitrack = AsyncMock(
            side_effect=Exception("MT3 model failed")
        )

        with pytest.raises(Exception, match="MT3 model failed"):
            await service.transcribe_audio_advanced('test.wav')

    def test_get_service_info(self, service):
        """Test service information retrieval"""
        info = service.get_service_info()

        assert 'version' in info
        assert 'models' in info
        assert 'supported_instruments' in info
        assert 'accuracy_modes' in info
        assert 'expected_accuracy' in info

        # Verify supported modes
        assert 'fast' in info['accuracy_modes']
        assert 'balanced' in info['accuracy_modes']
        assert 'maximum' in info['accuracy_modes']

    async def test_progress_tracking_integration(self, service):
        """Test that progress is properly tracked during transcription"""
        # Mock the service methods to return immediately
        service.mt3_service.transcribe_multitrack = AsyncMock(return_value=MagicMock(
            tracks={'guitar': []},
            confidence_scores={'guitar': 0.8},
            tempo=120,
            time_signature='4/4',
            key_signature='C Major'
        ))
        
        with patch('transcriber.services.advanced_transcription_service.update_progress') as mock_progress:
            with patch.object(service, '_get_audio_metadata', return_value={'duration': 60.0, 'sample_rate': 44100}):
                try:
                    await service.transcribe_audio_advanced(
                        'test.wav',
                        transcription_id='test-123',
                        use_all_models=False
                    )
                except:
                    pass  # Ignore errors, we're testing progress tracking

            # Verify progress was tracked
            mock_progress.assert_called()

    async def test_metadata_extraction(self, service, mock_mt3_result, mock_omnizart_results):
        """Test enhanced metadata extraction from multiple sources"""
        # Add chord data to Omnizart results
        mock_omnizart_results['chord'] = OmnizartResult(
            instrument='chord',
            notes=[],
            chords=[{'time': 0.0, 'chord': 'C'}, {'time': 2.0, 'chord': 'G'}],
            beats=None,
            confidence=0.9,
            model_used='omnizart_chord',
            processing_time=1.0
        )

        metadata = await service._extract_enhanced_metadata(
            mock_mt3_result, mock_omnizart_results, None
        )

        assert 'tempo' in metadata
        assert 'key' in metadata
        assert 'time_signature' in metadata
        assert 'complexity' in metadata
        assert 'chords' in metadata
        assert len(metadata['chords']) == 2

