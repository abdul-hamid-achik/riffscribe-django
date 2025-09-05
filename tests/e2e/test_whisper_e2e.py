import pytest
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import Mock, patch
import json
import tempfile

from transcriber.models import Transcription


class TestWhisperEndToEndIntegration(TransactionTestCase):
    """End-to-end integration tests for Whisper AI features"""
    
    def setUp(self):
        """Set up test data"""
        # Create a minimal audio file for testing
        self.audio_data = b'fake audio content for testing'
        self.audio_file = SimpleUploadedFile(
            'test_song.mp3',
            self.audio_data,
            content_type='audio/mpeg'
        )
    
    @patch('transcriber.tasks.process_transcription.delay')
    def test_upload_and_process_with_whisper_enabled(self, mock_task_delay):
        """Test the full upload and processing workflow with Whisper enabled"""
        
        # Mock the Celery task
        mock_task_delay.return_value.id = 'test-task-id'
        
        # Upload audio file
        response = self.client.post(reverse('transcriber:upload'), {
            'audio_file': self.audio_file
        })
        
        # Should redirect to detail page
        assert response.status_code == 302
        
        # Verify transcription was created
        transcription = Transcription.objects.get(filename='test_song.mp3')
        assert transcription.status == 'pending'
        
        # Verify the processing task was queued
        mock_task_delay.assert_called_once_with(transcription.id)
    
    @patch('transcriber.ml_pipeline.WhisperService')
    def test_status_endpoint_shows_whisper_progress(self, mock_whisper_service):
        """Test that status endpoint shows Whisper-enhanced progress"""
        
        # Create a processing transcription
        transcription = Transcription.objects.create(
            filename='test_song.mp3',
            status='processing'
        )
        
        # Mock a task with Whisper progress
        with patch('transcriber.views.current_task') as mock_current_task:
            mock_current_task.return_value = Mock(
                state='PROGRESS',
                info={'step': 'Enhanced with Whisper AI...'}
            )
            
            response = self.client.get(
                reverse('transcriber:status', kwargs={'pk': transcription.pk})
            )
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'Enhanced with Whisper AI' in content or 'AI-Enhanced' in content
    
    @patch('transcriber.ml_pipeline.WhisperService')
    def test_detail_page_shows_whisper_analysis(self, mock_whisper_service):
        """Test that detail page displays Whisper analysis results"""
        
        # Create completed transcription with Whisper analysis
        whisper_analysis = {
            'status': 'success',
            'analysis': 'Jazz guitar in Bb major with complex chord progressions',
            'musical_elements': {
                'chords': ['Bbmaj7', 'Em7b5', 'A7', 'Dm7'],
                'tempo': 95,
                'key': 'Bb major',
                'time_signature': '4/4'
            },
            'chord_progressions': ['Bbmaj7-Em7b5-A7-Dm7'],
            'musical_description': 'Sophisticated jazz arrangement with advanced harmony'
        }
        
        transcription = Transcription.objects.create(
            filename='jazz_song.mp3',
            status='completed',
            whisper_analysis=whisper_analysis,
            duration=180.0,
            estimated_tempo=95,
            estimated_key='Bb major'
        )
        
        response = self.client.get(
            reverse('transcriber:detail', kwargs={'pk': transcription.pk})
        )
        
        assert response.status_code == 200
        content = response.content.decode()
        
        # Check for Whisper enhancement badge
        assert 'AI-Enhanced Transcription' in content
        
        # Check for chord progression information
        assert 'chord progressions detected' in content or 'chord' in content.lower()
        
        # Check for musical description
        assert 'jazz arrangement' in content.lower() or transcription.whisper_analysis['musical_description'] in content
    
    def test_detail_page_without_whisper_analysis(self):
        """Test that detail page works normally without Whisper analysis"""
        
        # Create transcription without Whisper data
        transcription = Transcription.objects.create(
            filename='basic_song.mp3',
            status='completed',
            duration=120.0,
            estimated_tempo=120,
            estimated_key='C major'
        )
        
        response = self.client.get(
            reverse('transcriber:detail', kwargs={'pk': transcription.pk})
        )
        
        assert response.status_code == 200
        content = response.content.decode()
        
        # Should not show Whisper enhancement badge
        assert 'AI-Enhanced Transcription' not in content
    
    @patch('transcriber.tasks.MLPipeline')
    def test_full_workflow_with_whisper_mock(self, mock_ml_pipeline):
        """Test complete workflow from upload to completion with mocked Whisper"""
        
        # Mock the ML Pipeline with comprehensive Whisper results
        mock_pipeline_instance = Mock()
        mock_pipeline_instance.whisper_service = Mock()
        
        # Mock analysis with Whisper enhancement
        mock_pipeline_instance.analyze_audio.return_value = {
            'duration': 150.0,
            'sample_rate': 44100,
            'channels': 2,
            'tempo': 108,
            'key': 'F# minor',
            'complexity': 'complex',
            'instruments': ['electric_guitar', 'bass', 'drums'],
            'whisper_analysis': {
                'status': 'success',
                'analysis': 'Progressive rock song with intricate guitar work',
                'musical_elements': {
                    'chords': ['F#m', 'A', 'B', 'C#m', 'D', 'E'],
                    'tempo': 108,
                    'key': 'F# minor',
                    'time_signature': '7/8'
                }
            }
        }
        
        # Mock transcription with chord detection
        mock_pipeline_instance.separate_sources.return_value = {
            'guitar': '/tmp/guitar_track.wav'
        }
        mock_pipeline_instance.transcribe.return_value = {
            'notes': [
                {'pitch': 66, 'start': 0.0, 'end': 0.5, 'velocity': 90},
                {'pitch': 69, 'start': 0.5, 'end': 1.0, 'velocity': 85}
            ],
            'midi_data': {'tracks': [{'notes': []}]},
            'whisper_chords': {
                'chord_progressions': ['F#m-A-B-C#m'],
                'individual_notes': ['F#', 'A', 'B', 'C#'],
                'segments': [
                    {'start': 0.0, 'end': 4.0, 'text': 'F# minor chord progression'}
                ]
            }
        }
        
        mock_ml_pipeline.return_value = mock_pipeline_instance
        
        # Mock other components
        with patch('transcriber.tasks.TabGenerator') as mock_tab_gen, \
             patch('transcriber.tasks.ExportManager') as mock_export_mgr, \
             patch('transcriber.tasks.VariantGenerator') as mock_variant_gen:
            
            mock_tab_gen.return_value.generate_optimized_tabs.return_value = {
                'measures': [
                    {'frets': [2, 4, 4, 2, 2, 2], 'duration': 1.0}
                ]
            }
            
            mock_export_mgr.return_value.generate_musicxml.return_value = '<musicxml>test</musicxml>'
            mock_export_mgr.return_value.generate_gp5.return_value = '/tmp/test.gp5'
            
            mock_variant_gen.return_value.generate_all_variants.return_value = [
                Mock(variant_name='easy', playability_score=75)
            ]
            
            # Create transcription and simulate processing
            transcription = Transcription.objects.create(
                filename='prog_rock.mp3',
                status='pending'
            )
            
            # Mock file attachment
            with patch.object(transcription, 'original_audio') as mock_audio:
                mock_audio.path = '/tmp/prog_rock.mp3'
                
                # Import and run the task function directly
                from transcriber.tasks import process_transcription
                
                mock_task = Mock()
                result = process_transcription(mock_task, transcription.id)
        
        # Verify successful processing
        assert result['status'] == 'success'
        assert result['duration'] == 150.0
        
        # Refresh and verify transcription
        transcription.refresh_from_db()
        assert transcription.status == 'completed'
        assert transcription.estimated_tempo == 108
        assert transcription.estimated_key == 'F# minor'
        assert transcription.complexity == 'complex'
        
        # Verify Whisper analysis was stored
        assert transcription.whisper_analysis is not None
        assert transcription.whisper_analysis['status'] == 'success'
        assert 'Progressive rock' in transcription.whisper_analysis['analysis']
        assert 'F#m' in transcription.whisper_analysis['musical_elements']['chords']
        assert transcription.whisper_analysis['musical_elements']['time_signature'] == '7/8'
    
    @patch('transcriber.ml_pipeline.WhisperService')
    def test_whisper_error_handling_in_workflow(self, mock_whisper_service):
        """Test that the workflow handles Whisper errors gracefully"""
        
        # Create transcription that will encounter Whisper error
        transcription = Transcription.objects.create(
            filename='error_test.mp3',
            status='processing'
        )
        
        # Mock Whisper service to raise an exception
        mock_service_instance = Mock()
        mock_service_instance.analyze_music.side_effect = Exception("Whisper API error")
        mock_whisper_service.return_value = mock_service_instance
        
        with patch('transcriber.ml_pipeline.MLPipeline') as mock_pipeline, \
             patch('transcriber.ml_pipeline.logger') as mock_logger:
            
            mock_pipeline_instance = Mock()
            mock_pipeline_instance.whisper_service = mock_service_instance
            mock_pipeline.return_value = mock_pipeline_instance
            
            # This should handle the error and continue processing
            from transcriber.ml_pipeline import MLPipeline
            pipeline = MLPipeline(use_gpu=False)
            
            # The analyze_audio method should catch and log Whisper errors
            with patch('transcriber.ml_pipeline.os.path.exists', return_value=True), \
                 patch('transcriber.ml_pipeline.librosa.load', return_value=([0.1, 0.2], 22050)), \
                 patch('transcriber.ml_pipeline.librosa.beat.tempo', return_value=(120.0, [0, 1])):
                
                result = pipeline.analyze_audio('/fake/path.mp3')
            
            # Should complete without Whisper data but not crash
            assert 'duration' in result
            assert 'whisper_analysis' not in result
            
            # Should have logged the error
            mock_logger.warning.assert_called()
    
    def test_settings_configuration_impact(self):
        """Test how different Whisper settings affect the workflow"""
        
        test_settings = [
            # (USE_WHISPER, WHISPER_ENABLE_CHORD_DETECTION, OPENAI_API_KEY)
            (True, True, 'valid-key'),
            (True, False, 'valid-key'),
            (False, True, 'valid-key'),
            (True, True, ''),
        ]
        
        for use_whisper, enable_chords, api_key in test_settings:
            with patch('django.conf.settings') as mock_settings:
                mock_settings.USE_WHISPER = use_whisper
                mock_settings.WHISPER_ENABLE_CHORD_DETECTION = enable_chords
                mock_settings.OPENAI_API_KEY = api_key
                mock_settings.WHISPER_MODEL = 'whisper-1'
                
                from transcriber.ml_pipeline import MLPipeline
                pipeline = MLPipeline(use_gpu=False)
                
                # Verify Whisper service is created only when appropriate
                if use_whisper and api_key:
                    assert pipeline.whisper_service is not None
                else:
                    assert pipeline.whisper_service is None