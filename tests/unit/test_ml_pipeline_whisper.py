import pytest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import json
from django.test import TestCase

from transcriber.services.ml_pipeline import MLPipeline


class TestMLPipelineWhisperIntegration(TestCase):
    """Test ML Pipeline with Whisper AI integration"""
    
    @pytest.fixture
    def sample_audio_file(self):
        """Create temporary audio file for testing"""
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
            f.write(b'fake audio data')
            return f.name
    
    @patch('transcriber.services.ml_pipeline.WhisperService')
    def test_pipeline_init_with_whisper(self, mock_whisper_service):
        """Test ML pipeline initialization with Whisper enabled"""
        mock_service_instance = Mock()
        mock_whisper_service.return_value = mock_service_instance
        
        with patch('django.conf.settings') as mock_settings:
            mock_settings.USE_WHISPER = True
            mock_settings.OPENAI_API_KEY = 'test-key'
            mock_settings.WHISPER_MODEL = 'whisper-1'
            
            pipeline = MLPipeline(use_gpu=False)
            
            assert pipeline.whisper_service == mock_service_instance
            mock_whisper_service.assert_called_once_with(api_key='test-key', model='whisper-1')
    
    @patch('transcriber.services.ml_pipeline.WhisperService')
    def test_pipeline_init_without_whisper(self, mock_whisper_service):
        """Test ML pipeline initialization with Whisper disabled"""
        with patch('django.conf.settings') as mock_settings:
            mock_settings.USE_WHISPER = False
            
            pipeline = MLPipeline(use_gpu=False)
            
            assert pipeline.whisper_service is None
            mock_whisper_service.assert_not_called()
    
    @patch('transcriber.services.ml_pipeline.WhisperService')
    @patch('transcriber.services.ml_pipeline.librosa')
    def test_analyze_audio_with_whisper(self, mock_librosa, mock_whisper_service, sample_audio_file):
        """Test audio analysis with Whisper enhancement"""
        # Mock librosa
        mock_librosa.load.return_value = ([0.1, 0.2, 0.3], 22050)
        mock_librosa.beat.tempo.return_value = (120.0, [0, 1, 2])
        
        # Mock Whisper service
        mock_service_instance = Mock()
        mock_service_instance.analyze_music.return_value = {
            'status': 'success',
            'analysis': 'Guitar in A minor, 120 BPM, chord progression Am-F-C-G',
            'musical_elements': {
                'chords': ['Am', 'F', 'C', 'G'],
                'tempo': 120,
                'key': 'A minor',
                'time_signature': '4/4'
            }
        }
        mock_whisper_service.return_value = mock_service_instance
        
        with patch('django.conf.settings') as mock_settings:
            mock_settings.USE_WHISPER = True
            mock_settings.OPENAI_API_KEY = 'test-key'
            mock_settings.WHISPER_MODEL = 'whisper-1'
            
            pipeline = MLPipeline(use_gpu=False)
            
            with patch('transcriber.services.ml_pipeline.os.path.exists', return_value=True):
                result = pipeline.analyze_audio(sample_audio_file)
            
            # Verify Whisper was called
            mock_service_instance.analyze_music.assert_called_once_with(sample_audio_file)
            
            # Verify results include Whisper analysis
            assert 'whisper_analysis' in result
            assert result['whisper_analysis']['status'] == 'success'
            assert 'Am' in result['whisper_analysis']['musical_elements']['chords']
            assert result['whisper_analysis']['musical_elements']['tempo'] == 120
    
    @patch('transcriber.services.ml_pipeline.WhisperService')
    @patch('transcriber.services.ml_pipeline.librosa')
    def test_analyze_audio_whisper_fallback(self, mock_librosa, mock_whisper_service, sample_audio_file):
        """Test audio analysis with Whisper failure fallback"""
        # Mock librosa
        mock_librosa.load.return_value = ([0.1, 0.2, 0.3], 22050)
        mock_librosa.beat.tempo.return_value = (120.0, [0, 1, 2])
        
        # Mock Whisper service to fail
        mock_service_instance = Mock()
        mock_service_instance.analyze_music.return_value = {
            'status': 'error',
            'error': 'API timeout'
        }
        mock_whisper_service.return_value = mock_service_instance
        
        with patch('django.conf.settings') as mock_settings:
            mock_settings.USE_WHISPER = True
            mock_settings.OPENAI_API_KEY = 'test-key'
            
            pipeline = MLPipeline(use_gpu=False)
            
            with patch('transcriber.services.ml_pipeline.os.path.exists', return_value=True), \
                 patch('transcriber.services.ml_pipeline.logger') as mock_logger:
                
                result = pipeline.analyze_audio(sample_audio_file)
            
            # Verify error was logged
            mock_logger.warning.assert_called_once()
            
            # Verify analysis still completed with basic results
            assert 'duration' in result
            assert 'tempo' in result
            assert 'whisper_analysis' not in result  # Should be excluded on failure
    
    @patch('transcriber.services.ml_pipeline.WhisperService')
    @patch('transcriber.services.ml_pipeline.basic_pitch')
    def test_transcribe_with_whisper_context(self, mock_basic_pitch, mock_whisper_service, sample_audio_file):
        """Test transcription with Whisper context enhancement"""
        # Mock basic_pitch
        mock_basic_pitch.predict.return_value = (
            [[0.9, 0.8, 0.7]],  # pitch predictions
            [0, 1, 2],  # onset predictions  
            [0.9, 0.8, 0.7]  # contour predictions
        )
        
        # Mock Whisper service
        mock_service_instance = Mock()
        mock_service_instance.detect_chords_and_notes.return_value = {
            'status': 'success',
            'chord_progressions': ['Am-F-C-G'],
            'individual_notes': ['A', 'F', 'C', 'G'],
            'segments': [
                {'start': 0.0, 'end': 2.0, 'text': 'Am chord'},
                {'start': 2.0, 'end': 4.0, 'text': 'F major chord'}
            ]
        }
        mock_whisper_service.return_value = mock_service_instance
        
        with patch('django.conf.settings') as mock_settings:
            mock_settings.USE_WHISPER = True
            mock_settings.WHISPER_ENABLE_CHORD_DETECTION = True
            mock_settings.OPENAI_API_KEY = 'test-key'
            
            pipeline = MLPipeline(use_gpu=False)
            
            context = {
                'tempo': 120,
                'key': 'A minor',
                'detected_instruments': ['guitar']
            }
            
            with patch('transcriber.services.ml_pipeline.os.path.exists', return_value=True), \
                 patch('transcriber.services.ml_pipeline.librosa.load', return_value=([0.1, 0.2], 22050)):
                
                result = pipeline.transcribe(sample_audio_file, context=context)
            
            # Verify Whisper was called for chord detection
            mock_service_instance.detect_chords_and_notes.assert_called_once_with(sample_audio_file)
            
            # Verify results include both basic pitch and Whisper data
            assert 'notes' in result
            assert 'midi_data' in result
            assert 'whisper_chords' in result
            assert len(result['whisper_chords']['chord_progressions']) > 0
    
    @patch('transcriber.ml_pipeline.WhisperService')
    @patch('transcriber.ml_pipeline.basic_pitch')
    def test_transcribe_whisper_chord_detection_disabled(self, mock_basic_pitch, mock_whisper_service, sample_audio_file):
        """Test transcription with Whisper chord detection disabled"""
        # Mock basic_pitch
        mock_basic_pitch.predict.return_value = (
            [[0.9, 0.8, 0.7]],
            [0, 1, 2],
            [0.9, 0.8, 0.7]
        )
        
        mock_service_instance = Mock()
        mock_whisper_service.return_value = mock_service_instance
        
        with patch('django.conf.settings') as mock_settings:
            mock_settings.USE_WHISPER = True
            mock_settings.WHISPER_ENABLE_CHORD_DETECTION = False
            mock_settings.OPENAI_API_KEY = 'test-key'
            
            pipeline = MLPipeline(use_gpu=False)
            
            with patch('transcriber.services.ml_pipeline.os.path.exists', return_value=True), \
                 patch('transcriber.services.ml_pipeline.librosa.load', return_value=([0.1, 0.2], 22050)):
                
                result = pipeline.transcribe(sample_audio_file)
            
            # Verify Whisper chord detection was not called
            mock_service_instance.detect_chords_and_notes.assert_not_called()
            
            # Verify basic transcription still works
            assert 'notes' in result
            assert 'midi_data' in result
            assert 'whisper_chords' not in result
    
    @patch('transcriber.ml_pipeline.WhisperService')
    def test_whisper_enhancement_with_invalid_audio(self, mock_whisper_service):
        """Test Whisper enhancement with invalid audio file"""
        mock_service_instance = Mock()
        mock_service_instance.analyze_music.side_effect = Exception("File not found")
        mock_whisper_service.return_value = mock_service_instance
        
        with patch('django.conf.settings') as mock_settings:
            mock_settings.USE_WHISPER = True
            mock_settings.OPENAI_API_KEY = 'test-key'
            
            pipeline = MLPipeline(use_gpu=False)
            
            with patch('transcriber.services.ml_pipeline.logger') as mock_logger, \
                 patch('transcriber.services.ml_pipeline.os.path.exists', return_value=False):
                
                # Should handle the error gracefully
                result = pipeline.analyze_audio('nonexistent.mp3')
                
                # Verify error handling
                assert result is not None
                mock_logger.error.assert_called()
    
    @patch('transcriber.ml_pipeline.WhisperService')
    def test_whisper_integration_settings_validation(self, mock_whisper_service):
        """Test Whisper integration with various settings configurations"""
        test_cases = [
            # (USE_WHISPER, OPENAI_API_KEY, expected_whisper_service)
            (True, 'valid-key', True),
            (True, '', False),
            (True, None, False),
            (False, 'valid-key', False),
        ]
        
        for use_whisper, api_key, expect_service in test_cases:
            with patch('django.conf.settings') as mock_settings:
                mock_settings.USE_WHISPER = use_whisper
                mock_settings.OPENAI_API_KEY = api_key
                mock_settings.WHISPER_MODEL = 'whisper-1'
                
                pipeline = MLPipeline(use_gpu=False)
                
                if expect_service:
                    assert pipeline.whisper_service is not None
                else:
                    assert pipeline.whisper_service is None