"""
Integration test suite for Whisper AI functionality
This test combines multiple components to verify end-to-end integration
"""

import pytest
from unittest.mock import Mock, patch
from django.test import TestCase
import json

from transcriber.services.whisper_service import WhisperService
from transcriber.services.ml_pipeline import MLPipeline
from transcriber.models import Transcription


class TestWhisperIntegrationSuite(TestCase):
    """Comprehensive integration tests for Whisper AI features"""
    
    def test_whisper_service_ml_pipeline_integration(self):
        """Test WhisperService integration with MLPipeline"""
        
        with patch('transcriber.services.whisper_service.openai') as mock_openai, \
             patch('django.conf.settings') as mock_settings:
            
            # Configure settings for Whisper
            mock_settings.USE_WHISPER = True
            mock_settings.OPENAI_API_KEY = 'test-key'
            mock_settings.WHISPER_MODEL = 'whisper-1'
            mock_settings.WHISPER_ENABLE_CHORD_DETECTION = True
            
            # Mock OpenAI client
            mock_client = Mock()
            mock_openai.OpenAI.return_value = mock_client
            
            # Mock transcription response
            mock_response = Mock()
            mock_response.text = "Guitar riff in E minor with power chords"
            mock_response.segments = [
                {'start': 0.0, 'end': 2.0, 'text': 'Em power chord'},
                {'start': 2.0, 'end': 4.0, 'text': 'G major chord'}
            ]
            mock_client.audio.transcriptions.create.return_value = mock_response
            
            # Create ML pipeline with Whisper
            pipeline = MLPipeline(use_gpu=False)
            
            # Verify Whisper service was initialized
            assert pipeline.whisper_service is not None
            assert pipeline.whisper_service.client is not None
            
            # Test that Whisper service methods work through pipeline
            with patch('builtins.open', create=True), \
                 patch('transcriber.services.ml_pipeline.os.path.exists', return_value=True):
                
                # Test music analysis
                result = pipeline.whisper_service.analyze_music('test.mp3')
                assert result['status'] == 'success'
                assert 'E minor' in result['analysis']
                
                # Test chord detection
                chord_result = pipeline.whisper_service.detect_chords_and_notes('test.mp3')
                assert chord_result['status'] == 'success'
                assert len(chord_result['segments']) == 2
    
    def test_model_whisper_field_serialization(self):
        """Test that Transcription model properly handles Whisper JSON data"""
        
        # Complex Whisper analysis data
        complex_whisper_data = {
            'status': 'success',
            'analysis': 'Complex jazz fusion piece with extended harmonies',
            'musical_elements': {
                'chords': ['Cmaj9', 'Am11', 'F#m7b5', 'B7alt'],
                'tempo': 132,
                'key': 'C major',
                'time_signature': '7/8',
                'techniques': ['sweep_picking', 'tapping', 'legato'],
                'scales': ['C major', 'A natural minor', 'F# locrian']
            },
            'chord_progressions': [
                'Cmaj9-Am11-F#m7b5-B7alt',
                'Cmaj9-Am11-Dm7-G7'
            ],
            'segments': [
                {
                    'start': 0.0,
                    'end': 8.0,
                    'text': 'Jazz fusion intro with complex chords',
                    'confidence': 0.95
                }
            ],
            'metadata': {
                'model_version': 'whisper-1',
                'processing_time': 15.3,
                'audio_duration': 180.0
            }
        }
        
        # Create transcription with complex Whisper data
        transcription = Transcription.objects.create(
            filename='jazz_fusion.mp3',
            status='completed',
            whisper_analysis=complex_whisper_data,
            duration=180.0,
            estimated_tempo=132,
            estimated_key='C major'
        )
        
        # Verify data persistence and retrieval
        transcription.refresh_from_db()
        
        # Test nested structure access
        assert transcription.whisper_analysis['status'] == 'success'
        assert 'Cmaj9' in transcription.whisper_analysis['musical_elements']['chords']
        assert transcription.whisper_analysis['musical_elements']['time_signature'] == '7/8'
        assert 'sweep_picking' in transcription.whisper_analysis['musical_elements']['techniques']
        assert len(transcription.whisper_analysis['chord_progressions']) == 2
        assert transcription.whisper_analysis['metadata']['processing_time'] == 15.3
        
        # Test querying by Whisper data
        transcriptions_with_jazz = Transcription.objects.filter(
            whisper_analysis__analysis__icontains='jazz'
        )
        assert transcription in transcriptions_with_jazz
        
        # Test updating Whisper data
        updated_analysis = transcription.whisper_analysis.copy()
        updated_analysis['metadata']['updated'] = True
        transcription.whisper_analysis = updated_analysis
        transcription.save()
        
        transcription.refresh_from_db()
        assert transcription.whisper_analysis['metadata']['updated'] is True
    
    def test_whisper_error_recovery_integration(self):
        """Test error recovery across the full Whisper integration"""
        
        with patch('transcriber.services.whisper_service.openai') as mock_openai, \
             patch('django.conf.settings') as mock_settings:
            
            mock_settings.USE_WHISPER = True
            mock_settings.OPENAI_API_KEY = 'test-key'
            mock_settings.WHISPER_MODEL = 'whisper-1'
            
            # Mock OpenAI client to fail
            mock_client = Mock()
            mock_client.audio.transcriptions.create.side_effect = Exception("API timeout")
            mock_openai.OpenAI.return_value = mock_client
            
            # Create pipeline
            pipeline = MLPipeline(use_gpu=False)
            
            # Test that errors are handled gracefully
            with patch('builtins.open', create=True):
                result = pipeline.whisper_service.transcribe_audio('test.mp3')
                assert result['status'] == 'error'
                assert 'API timeout' in result['error']
                
                # Test music analysis error handling
                music_result = pipeline.whisper_service.analyze_music('test.mp3')
                assert music_result['status'] == 'error'
    
    def test_whisper_configuration_validation(self):
        """Test different Whisper configuration scenarios"""
        
        configurations = [
            # (USE_WHISPER, API_KEY, expected_service)
            (True, 'sk-valid-key', True),
            (True, '', False),
            (True, None, False),
            (False, 'sk-valid-key', False),
        ]
        
        for use_whisper, api_key, should_have_service in configurations:
            with patch('django.conf.settings') as mock_settings:
                mock_settings.USE_WHISPER = use_whisper
                mock_settings.OPENAI_API_KEY = api_key
                mock_settings.WHISPER_MODEL = 'whisper-1'
                
                pipeline = MLPipeline(use_gpu=False)
                
                if should_have_service:
                    assert pipeline.whisper_service is not None
                else:
                    assert pipeline.whisper_service is None
    
    def test_whisper_analysis_extraction_accuracy(self):
        """Test accuracy of musical element extraction from Whisper text"""
        
        service = WhisperService(api_key=None)  # No actual API calls needed
        
        # Test various musical text formats
        test_cases = [
            {
                'text': "The song is in A minor at 120 BPM with chords Am, F, C, G in 4/4 time",
                'expected_chords': ['Am', 'F', 'C', 'G'],
                'expected_tempo': 120,
                'expected_key': 'A minor',
                'expected_time_sig': '4/4'
            },
            {
                'text': "Jazz progression: Cmaj7 - Am7 - Dm7 - G7, approximately 95 beats per minute",
                'expected_chords': ['Cmaj7', 'Am7', 'Dm7', 'G7'],
                'expected_tempo': 95,
                'expected_key': None,
                'expected_time_sig': None
            },
            {
                'text': "Heavy metal in D# minor, tempo around 140, power chords D#5 - B5 - F#5",
                'expected_chords': ['D#5', 'B5', 'F#5'],
                'expected_tempo': 140,
                'expected_key': 'D# minor',
                'expected_time_sig': None
            }
        ]
        
        for case in test_cases:
            result = service._extract_musical_elements(case['text'])
            
            # Check chords
            for expected_chord in case['expected_chords']:
                assert expected_chord in result['chords'], f"Expected chord {expected_chord} not found in {result['chords']}"
            
            # Check tempo
            if case['expected_tempo']:
                assert result['tempo'] == case['expected_tempo']
            
            # Check key
            if case['expected_key']:
                assert result['key'] == case['expected_key']
            
            # Check time signature
            if case['expected_time_sig']:
                assert result['time_signature'] == case['expected_time_sig']
    
    def test_full_pipeline_data_flow(self):
        """Test complete data flow from Whisper through to storage"""
        
        # This test verifies that Whisper data flows correctly through the entire pipeline
        
        with patch('transcriber.services.whisper_service.openai') as mock_openai, \
             patch('django.conf.settings') as mock_settings:
            
            # Configure settings
            mock_settings.USE_WHISPER = True
            mock_settings.OPENAI_API_KEY = 'test-key'
            mock_settings.WHISPER_ENABLE_CHORD_DETECTION = True
            
            # Mock OpenAI responses
            mock_client = Mock()
            
            # Response for music analysis
            analysis_response = Mock()
            analysis_response.text = "Progressive rock in F# minor, 7/8 time, 108 BPM, chords F#m-A-B-C#m-D-E"
            analysis_response.segments = []
            
            # Response for chord detection  
            chord_response = Mock()
            chord_response.text = "F#m chord progression with complex rhythmic patterns"
            chord_response.segments = [
                {'start': 0.0, 'end': 4.0, 'text': 'F# minor chord'},
                {'start': 4.0, 'end': 8.0, 'text': 'A major transition'}
            ]
            
            # Configure mock to return different responses for different calls
            mock_client.audio.transcriptions.create.side_effect = [
                analysis_response,  # First call for analysis
                chord_response      # Second call for chord detection
            ]
            
            mock_openai.OpenAI.return_value = mock_client
            
            # Create pipeline and test analysis
            pipeline = MLPipeline(use_gpu=False)
            
            with patch('builtins.open', create=True), \
                 patch('transcriber.services.ml_pipeline.os.path.exists', return_value=True), \
                 patch('transcriber.services.ml_pipeline.librosa.load', return_value=([0.1, 0.2], 22050)), \
                 patch('transcriber.services.ml_pipeline.librosa.beat.tempo', return_value=(108.0, [0, 1])):
                
                # Test analysis
                analysis_result = pipeline.analyze_audio('test.mp3')
                
                # Verify Whisper analysis was included
                assert 'whisper_analysis' in analysis_result
                assert analysis_result['whisper_analysis']['status'] == 'success'
                assert 'Progressive rock' in analysis_result['whisper_analysis']['analysis']
                
                # Test transcription with context
                context = {
                    'tempo': 108,
                    'key': 'F# minor',
                    'detected_instruments': ['guitar']
                }
                
                with patch('transcriber.services.ml_pipeline.basic_pitch.predict', return_value=([[0.9]], [0], [0.9])):
                    transcription_result = pipeline.transcribe('test.mp3', context=context)
                
                # Verify chord detection was included
                assert 'whisper_chords' in transcription_result
                assert transcription_result['whisper_chords']['status'] == 'success'
                assert len(transcription_result['whisper_chords']['segments']) == 2
            
            # Verify both analysis and chord detection were called
            assert mock_client.audio.transcriptions.create.call_count == 2