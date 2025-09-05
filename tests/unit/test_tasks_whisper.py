import pytest
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase
import uuid
import json

from transcriber.models import Transcription
from transcriber.tasks import process_transcription


class TestTasksWhisperIntegration(TestCase):
    """Test Celery tasks with Whisper AI integration"""
    
    def setUp(self):
        """Set up test data"""
        self.transcription = Transcription.objects.create(
            filename='test_song.mp3',
            status='pending'
        )
    
    @patch('transcriber.tasks.MLPipeline')
    @patch('transcriber.tasks.TabGenerator')
    @patch('transcriber.tasks.ExportManager')
    @patch('transcriber.tasks.VariantGenerator')
    def test_process_transcription_with_whisper_success(
        self, 
        mock_variant_gen, 
        mock_export_mgr, 
        mock_tab_gen, 
        mock_ml_pipeline
    ):
        """Test successful transcription processing with Whisper enhancement"""
        
        # Mock ML Pipeline with Whisper analysis
        mock_pipeline_instance = Mock()
        mock_pipeline_instance.whisper_service = Mock()  # Indicate Whisper is available
        mock_pipeline_instance.analyze_audio.return_value = {
            'duration': 180.0,
            'sample_rate': 22050,
            'channels': 1,
            'tempo': 120,
            'key': 'A minor',
            'complexity': 'moderate',
            'instruments': ['guitar', 'bass'],
            'whisper_analysis': {
                'status': 'success',
                'analysis': 'Guitar song in A minor with chord progression Am-F-C-G',
                'musical_elements': {
                    'chords': ['Am', 'F', 'C', 'G'],
                    'tempo': 120,
                    'key': 'A minor'
                }
            }
        }
        
        mock_pipeline_instance.separate_sources.return_value = {
            'guitar': '/path/to/guitar_track.wav'
        }
        
        mock_pipeline_instance.transcribe.return_value = {
            'notes': [
                {'pitch': 69, 'start': 0.0, 'end': 1.0, 'velocity': 80},
                {'pitch': 72, 'start': 1.0, 'end': 2.0, 'velocity': 75}
            ],
            'midi_data': {'tracks': [{'notes': []}]},
            'whisper_chords': {
                'chord_progressions': ['Am-F-C-G'],
                'segments': [
                    {'start': 0.0, 'end': 4.0, 'text': 'Am chord progression'}
                ]
            }
        }
        
        mock_ml_pipeline.return_value = mock_pipeline_instance
        
        # Mock Tab Generator
        mock_tab_instance = Mock()
        mock_tab_instance.generate_optimized_tabs.return_value = {
            'measures': [
                {'frets': [0, 2, 2, 1, 0, 0], 'duration': 1.0}
            ]
        }
        mock_tab_gen.return_value = mock_tab_instance
        
        # Mock Export Manager
        mock_export_instance = Mock()
        mock_export_instance.generate_musicxml.return_value = '<musicxml>content</musicxml>'
        mock_export_instance.generate_gp5.return_value = '/path/to/file.gp5'
        mock_export_mgr.return_value = mock_export_instance
        
        # Mock Variant Generator
        mock_variant_instance = Mock()
        mock_variant_instance.generate_all_variants.return_value = [
            Mock(variant_name='easy', playability_score=85),
            Mock(variant_name='balanced', playability_score=70)
        ]
        mock_variant_gen.return_value = mock_variant_instance
        
        # Mock file path
        with patch.object(self.transcription, 'original_audio') as mock_audio:
            mock_audio.path = '/path/to/audio.mp3'
            
            # Mock task update_state
            mock_task = Mock()
            
            # Execute the task directly (bypass Celery for testing)
            result = process_transcription.run(self.transcription.id)
        
        # Verify the result
        assert result['status'] == 'success'
        assert result['transcription_id'] == str(self.transcription.id)
        assert result['duration'] == 180.0
        
        # Refresh transcription from database
        self.transcription.refresh_from_db()
        
        # Verify transcription was updated with analysis results
        assert self.transcription.status == 'completed'
        assert self.transcription.duration == 180.0
        assert self.transcription.estimated_tempo == 120
        assert self.transcription.estimated_key == 'A minor'
        assert self.transcription.complexity == 'moderate'
        assert 'guitar' in self.transcription.detected_instruments
        
        # Verify Whisper analysis was stored
        assert self.transcription.whisper_analysis is not None
        assert self.transcription.whisper_analysis['status'] == 'success'
        assert 'Am' in self.transcription.whisper_analysis['musical_elements']['chords']
        
        # Verify task progress updates included Whisper status
        progress_calls = mock_task.update_state.call_args_list
        whisper_calls = [call for call in progress_calls 
                        if call[1].get('meta', {}).get('step', '').lower().find('whisper') != -1]
        assert len(whisper_calls) > 0
    
    @patch('transcriber.tasks.MLPipeline')
    @patch('transcriber.tasks.TabGenerator')
    @patch('transcriber.tasks.ExportManager')
    @patch('transcriber.tasks.VariantGenerator')
    def test_process_transcription_whisper_fallback(
        self, 
        mock_variant_gen, 
        mock_export_mgr, 
        mock_tab_gen, 
        mock_ml_pipeline
    ):
        """Test transcription processing when Whisper fails but basic processing succeeds"""
        
        # Mock ML Pipeline with failed Whisper but successful basic analysis
        mock_pipeline_instance = Mock()
        mock_pipeline_instance.whisper_service = Mock()
        mock_pipeline_instance.analyze_audio.return_value = {
            'duration': 120.0,
            'sample_rate': 22050,
            'channels': 1,
            'tempo': 100,
            'key': 'C major',
            'complexity': 'simple',
            'instruments': ['guitar'],
            # No whisper_analysis field - indicates Whisper failed
        }
        
        mock_pipeline_instance.separate_sources.return_value = {}
        mock_pipeline_instance.transcribe.return_value = {
            'notes': [{'pitch': 60, 'start': 0.0, 'end': 1.0, 'velocity': 80}],
            'midi_data': {'tracks': [{'notes': []}]},
            # No whisper_chords field - indicates chord detection failed
        }
        
        mock_ml_pipeline.return_value = mock_pipeline_instance
        
        # Mock other components
        mock_tab_instance = Mock()
        mock_tab_instance.generate_optimized_tabs.return_value = {'measures': []}
        mock_tab_gen.return_value = mock_tab_instance
        
        mock_export_instance = Mock()
        mock_export_instance.generate_musicxml.return_value = '<musicxml/>'
        mock_export_instance.generate_gp5.return_value = None
        mock_export_mgr.return_value = mock_export_instance
        
        mock_variant_instance = Mock()
        mock_variant_instance.generate_all_variants.return_value = []
        mock_variant_gen.return_value = mock_variant_instance
        
        with patch.object(self.transcription, 'original_audio') as mock_audio:
            mock_audio.path = '/path/to/audio.mp3'
            
            mock_task = Mock()
            result = process_transcription.run(self.transcription.id)
        
        # Verify processing completed despite Whisper failure
        assert result['status'] == 'success'
        
        self.transcription.refresh_from_db()
        assert self.transcription.status == 'completed'
        assert self.transcription.whisper_analysis is None  # Should not be stored if failed
    
    @patch('transcriber.tasks.MLPipeline')
    def test_process_transcription_task_progress_whisper_steps(self, mock_ml_pipeline):
        """Test that task progress includes Whisper-specific steps"""
        
        mock_pipeline_instance = Mock()
        mock_pipeline_instance.whisper_service = Mock()  # Whisper available
        mock_pipeline_instance.analyze_audio.return_value = {
            'duration': 60.0, 'sample_rate': 22050, 'channels': 1,
            'tempo': 90, 'key': 'G major', 'complexity': 'simple',
            'instruments': ['guitar'],
            'whisper_analysis': {'status': 'success', 'analysis': 'Test'}
        }
        mock_pipeline_instance.separate_sources.return_value = {}
        mock_pipeline_instance.transcribe.return_value = {
            'notes': [], 'midi_data': {'tracks': []},
            'whisper_chords': {'chord_progressions': []}
        }
        
        mock_ml_pipeline.return_value = mock_pipeline_instance
        
        with patch.object(self.transcription, 'original_audio') as mock_audio, \
             patch('transcriber.tasks.TabGenerator') as mock_tab_gen, \
             patch('transcriber.tasks.ExportManager') as mock_export_mgr, \
             patch('transcriber.tasks.VariantGenerator') as mock_variant_gen:
            
            mock_audio.path = '/path/to/audio.mp3'
            
            # Mock all the generators to return minimal data
            mock_tab_gen.return_value.generate_optimized_tabs.return_value = {'measures': []}
            mock_export_mgr.return_value.generate_musicxml.return_value = '<xml/>'
            mock_export_mgr.return_value.generate_gp5.return_value = None
            mock_variant_gen.return_value.generate_all_variants.return_value = []
            
            mock_task = Mock()
            process_transcription.run(self.transcription.id)
        
        # Verify specific Whisper progress steps were called
        progress_calls = mock_task.update_state.call_args_list
        step_messages = [call[1]['meta']['step'] for call in progress_calls if 'meta' in call[1]]
        
        # Should include Whisper-specific messages
        whisper_steps = [msg for msg in step_messages if 'whisper' in msg.lower() or 'ai' in msg.lower()]
        assert len(whisper_steps) >= 1  # At least one Whisper-related progress message
    
    @patch('transcriber.tasks.MLPipeline')
    def test_process_transcription_without_whisper(self, mock_ml_pipeline):
        """Test transcription processing when Whisper is not available"""
        
        # Mock ML Pipeline without Whisper
        mock_pipeline_instance = Mock()
        mock_pipeline_instance.whisper_service = None  # No Whisper service
        mock_pipeline_instance.analyze_audio.return_value = {
            'duration': 90.0, 'sample_rate': 22050, 'channels': 1,
            'tempo': 110, 'key': 'D major', 'complexity': 'moderate',
            'instruments': ['guitar']
            # No whisper_analysis field
        }
        mock_pipeline_instance.separate_sources.return_value = {}
        mock_pipeline_instance.transcribe.return_value = {
            'notes': [], 'midi_data': {'tracks': []}
            # No whisper_chords field
        }
        
        mock_ml_pipeline.return_value = mock_pipeline_instance
        
        with patch.object(self.transcription, 'original_audio') as mock_audio, \
             patch('transcriber.tasks.TabGenerator') as mock_tab_gen, \
             patch('transcriber.tasks.ExportManager') as mock_export_mgr, \
             patch('transcriber.tasks.VariantGenerator') as mock_variant_gen:
            
            mock_audio.path = '/path/to/audio.mp3'
            
            # Mock generators
            mock_tab_gen.return_value.generate_optimized_tabs.return_value = {'measures': []}
            mock_export_mgr.return_value.generate_musicxml.return_value = '<xml/>'
            mock_export_mgr.return_value.generate_gp5.return_value = None
            mock_variant_gen.return_value.generate_all_variants.return_value = []
            
            mock_task = Mock()
            result = process_transcription.run(self.transcription.id)
        
        # Verify processing works without Whisper
        assert result['status'] == 'success'
        
        self.transcription.refresh_from_db()
        assert self.transcription.status == 'completed'
        assert self.transcription.whisper_analysis is None
        
        # Verify no Whisper-specific progress messages
        progress_calls = mock_task.update_state.call_args_list
        step_messages = [call[1]['meta']['step'] for call in progress_calls if 'meta' in call[1]]
        whisper_steps = [msg for msg in step_messages if 'whisper' in msg.lower()]
        assert len(whisper_steps) == 0
    
    def test_transcription_model_whisper_field(self):
        """Test that Transcription model properly handles whisper_analysis field"""
        
        # Test creating with Whisper data
        whisper_data = {
            'status': 'success',
            'analysis': 'Rock song in E minor',
            'musical_elements': {
                'chords': ['Em', 'C', 'G', 'D'],
                'tempo': 140,
                'key': 'E minor'
            }
        }
        
        transcription = Transcription.objects.create(
            filename='test_with_whisper.mp3',
            whisper_analysis=whisper_data
        )
        
        # Verify data is stored and retrieved correctly
        transcription.refresh_from_db()
        assert transcription.whisper_analysis['status'] == 'success'
        assert 'Em' in transcription.whisper_analysis['musical_elements']['chords']
        
        # Test creating without Whisper data
        basic_transcription = Transcription.objects.create(
            filename='test_without_whisper.mp3'
        )
        
        basic_transcription.refresh_from_db()
        assert basic_transcription.whisper_analysis is None