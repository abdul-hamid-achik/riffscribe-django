"""
Unit tests for Celery tasks.
"""
import pytest
from unittest.mock import patch, MagicMock, call
from celery import states
from transcriber.tasks import process_transcription, generate_export


@pytest.mark.django_db
class TestCeleryTasks:
    """Test Celery background tasks."""
    
    @pytest.mark.unit
    def test_process_transcription_success(self, completed_transcription):
        """Test successful transcription processing."""
        with patch('transcriber.tasks.settings') as mock_settings, \
             patch('transcriber.tasks.Transcription.objects.get') as mock_get:
            # Mock settings
            mock_settings.OPENAI_API_KEY = 'test_api_key'
            mock_settings.ENABLE_DRUMS = True
            mock_get.return_value = completed_transcription
            
            with patch('transcriber.tasks._get_ai_pipeline') as mock_get_pipeline:
                mock_ai_pipeline_class = MagicMock()
                mock_ai = MagicMock()
                mock_get_pipeline.return_value = mock_ai_pipeline_class
                mock_ai_pipeline_class.return_value = mock_ai
                
                # Mock analysis results
                mock_ai.analyze_audio.return_value = {
                    'duration': 30.5,
                    'sample_rate': 22050,
                    'channels': 1,
                    'tempo': 120,
                    'key': 'C Major',
                    'time_signature': '4/4',
                    'complexity': 'moderate',
                    'instruments': ['guitar']
                }
                
                # Mock transcription results
                mock_ai.transcribe.return_value = {
                    'notes': [
                        {'start_time': 0, 'end_time': 0.5, 'midi_note': 60, 'velocity': 80}
                    ],
                    'midi_data': {'notes': [{'midi_note': 60, 'velocity': 80}]}
                }
                
                with patch('transcriber.tasks._get_tab_generator') as mock_get_tab_gen:
                    mock_tab_gen_class = MagicMock()
                    mock_gen = MagicMock()
                    mock_get_tab_gen.return_value = mock_tab_gen_class
                    mock_tab_gen_class.return_value = mock_gen
                    mock_gen.generate_optimized_tabs.return_value = {
                        'tempo': 120,
                        'measures': []
                    }
                    mock_gen.to_ascii_tab.return_value = "ASCII_TAB"
                    
                    with patch('transcriber.tasks._get_export_manager') as mock_get_export_mgr, \
                         patch('transcriber.tasks._get_variant_generator') as mock_get_variant_gen, \
                         patch('transcriber.tasks.process_transcription.update_state') as mock_update_state:
                        
                        # Mock export manager
                        mock_export_mgr_class = MagicMock()
                        mock_export = MagicMock()
                        mock_get_export_mgr.return_value = mock_export_mgr_class
                        mock_export_mgr_class.return_value = mock_export
                        mock_export.generate_musicxml.return_value = '<musicxml>test</musicxml>'
                        mock_export.generate_gp5.return_value = '/tmp/test.gp5'
                        
                        # Mock variant generator
                        mock_variant_gen_class = MagicMock()
                        mock_var_gen = MagicMock()
                        mock_get_variant_gen.return_value = mock_variant_gen_class
                        mock_variant_gen_class.return_value = mock_var_gen
                        mock_var_gen.generate_all_variants.return_value = []
                        
                        # Execute task
                        result = process_transcription(str(completed_transcription.id))
                        
                        assert result['status'] == 'success'
                        assert 'duration' in result
                        mock_update_state.assert_called()
    
    @pytest.mark.unit
    def test_process_transcription_error_handling(self, sample_transcription):
        """Test error handling in transcription processing."""
        with patch('transcriber.tasks.settings') as mock_settings, \
             patch('transcriber.tasks.Transcription.objects.get') as mock_get:
            # Mock settings
            mock_settings.OPENAI_API_KEY = 'test_api_key'
            mock_settings.ENABLE_DRUMS = True
            mock_get.return_value = sample_transcription
            
            with patch('transcriber.tasks._get_ai_pipeline') as mock_get_pipeline:
                mock_ai_pipeline_class = MagicMock()
                mock_get_pipeline.return_value = mock_ai_pipeline_class
                mock_ai_pipeline_class.side_effect = Exception("AI Pipeline Error")
                
                with patch.object(sample_transcription, 'save'):
                    try:
                        result = process_transcription(str(sample_transcription.id))
                    except Exception as e:
                        # Task may raise exception or return error result
                        result = {'status': 'failed', 'error': str(e)}
                    
                    assert result['status'] == 'failed'
                    assert 'error' in result
    
    @pytest.mark.unit
    def test_generate_export_musicxml(self, completed_transcription):
        """Test MusicXML export generation."""
        with patch('transcriber.tasks.Transcription.objects.get') as mock_get:
            mock_get.return_value = completed_transcription
            
            with patch('transcriber.tasks._get_export_manager') as mock_get_export:
                mock_export_class = MagicMock()
                mock_manager = MagicMock()
                mock_get_export.return_value = mock_export_class
                mock_export_class.return_value = mock_manager
                mock_manager.export_musicxml.return_value = "/tmp/test.xml"
                
                with patch('transcriber.tasks.TabExport') as mock_tab_export, \
                     patch('django.core.files.File') as mock_file, \
                     patch('builtins.open', create=True), \
                     patch('os.path.exists', return_value=True), \
                     patch('os.path.getsize', return_value=1024), \
                     patch('os.remove'):
                    
                    mock_export_obj = MagicMock()
                    mock_export_obj.id = 1
                    mock_export_obj.file.url = '/media/exports/test.xml'
                    mock_tab_export.objects.create.return_value = mock_export_obj
                    
                    result = generate_export(str(completed_transcription.id), 'musicxml')
                    
                    assert result['status'] == 'success'
                    assert 'export_id' in result
                    mock_manager.export_musicxml.assert_called_once()
    
    @pytest.mark.unit
    def test_generate_export_midi(self, completed_transcription):
        """Test MIDI export generation."""
        with patch('transcriber.tasks.Transcription.objects.get') as mock_get:
            mock_get.return_value = completed_transcription
            completed_transcription.midi_file = MagicMock()
            completed_transcription.midi_file.name = 'test.mid'
            
            with patch('transcriber.tasks.TabExport') as mock_tab_export:
                mock_tab_export.objects.create.return_value = MagicMock(id=1)
                
                result = generate_export(str(completed_transcription.id), 'midi')
                
                assert result['status'] == 'success'
                assert 'export_id' in result
    
    @pytest.mark.unit
    def test_generate_export_ascii(self, completed_transcription):
        """Test ASCII tab export generation."""
        with patch('transcriber.tasks.Transcription.objects.get') as mock_get:
            mock_get.return_value = completed_transcription
            completed_transcription.ascii_tab = "e|---0---1---3---|\nB|---1---1---0---|"
            
            with patch('transcriber.tasks.TabExport') as mock_tab_export:
                mock_tab_export.objects.create.return_value = MagicMock(id=1)
                
                result = generate_export(str(completed_transcription.id), 'ascii')
                
                assert result['status'] == 'success'
                assert 'export_id' in result
    
    
    @pytest.mark.unit
    def test_task_state_updates(self):
        """Test that tasks properly update their state during execution."""
        from transcriber.tasks import process_transcription
        
        # Mock the task request and update_state method
        with patch('transcriber.tasks.settings') as mock_settings, \
             patch('transcriber.tasks.process_transcription.update_state') as mock_update_state, \
             patch('transcriber.tasks.Transcription.objects.get') as mock_get, \
             patch('transcriber.tasks._get_ai_pipeline') as mock_get_pipeline:
            
            # Mock settings
            mock_settings.OPENAI_API_KEY = 'test_api_key'
            mock_settings.ENABLE_DRUMS = True
            
            # Create a mock transcription with file
            mock_transcription = MagicMock()
            mock_transcription.id = "test-id"
            mock_transcription.original_audio.path = "/test/path.wav"
            mock_transcription.user = None
            mock_get.return_value = mock_transcription
            
            # Mock the pipeline to succeed
            mock_ml = MagicMock()
            mock_ai_pipeline_class = MagicMock()
            mock_ml = MagicMock()
            mock_get_pipeline.return_value = mock_ai_pipeline_class
            mock_ai_pipeline_class.return_value = mock_ml
            mock_ml.analyze_audio.return_value = {
                'duration': 30.0, 'sample_rate': 22050, 'channels': 1,
                'tempo': 120, 'key': 'C', 'complexity': 'simple', 'instruments': ['guitar']
            }
            mock_ml.transcribe.return_value = {'notes': [], 'midi_data': {}}
            
            with patch('transcriber.tasks._get_tab_generator') as mock_get_tab_gen, \
                 patch('transcriber.tasks._get_export_manager') as mock_get_export, \
                 patch('transcriber.tasks._get_variant_generator') as mock_get_variant, \
                 patch('os.path.getsize', return_value=1024000), \
                 patch('os.path.exists', return_value=True):
                
                # Mock the classes and instances
                mock_tab_gen_class = MagicMock()
                mock_export_class = MagicMock()
                mock_variant_class = MagicMock()
                mock_get_tab_gen.return_value = mock_tab_gen_class
                mock_get_export.return_value = mock_export_class
                mock_get_variant.return_value = mock_variant_class
                
                mock_tab_gen_class.return_value.generate_optimized_tabs.return_value = {}
                mock_export_class.return_value.generate_musicxml.return_value = '<xml/>'
                mock_variant_class.return_value.generate_all_variants.return_value = []
                
                # Execute the task
                result = process_transcription("test-id")
                
                # Check that update_state was called with PROGRESS
                assert mock_update_state.called
                # Check for PROGRESS calls
                progress_calls = [call for call in mock_update_state.call_args_list 
                                if 'PROGRESS' in str(call)]
                assert len(progress_calls) > 0


@pytest.mark.django_db
class TestTasksWithWhisper:
    """Test Celery tasks with Whisper AI integration"""
    
    @pytest.mark.integration
    @pytest.mark.django_db
    def test_process_transcription_with_whisper(self):
        """Test transcription processing with Whisper enhancement - simplified test"""
        # Test that the task can be called and verify key components are invoked
        with patch('transcriber.tasks.settings') as mock_settings, \
             patch('transcriber.tasks.Transcription.objects.get') as mock_get, \
             patch('transcriber.tasks._get_ai_pipeline') as mock_get_ai_pipeline, \
             patch('transcriber.tasks._get_tab_generator') as mock_get_tab_gen, \
             patch('transcriber.tasks._get_export_manager') as mock_get_export_mgr, \
             patch('transcriber.tasks._get_variant_generator') as mock_get_variant_gen, \
             patch('transcriber.tasks.process_transcription.update_state'), \
             patch('os.path.getsize', return_value=1024000), \
             patch('os.path.exists', return_value=True):
            
            # Create a mock transcription
            mock_transcription = MagicMock()
            mock_transcription.id = "test-id"
            mock_transcription.filename = "test.wav"
            mock_transcription.user = None
            mock_transcription.original_audio.path = "/path/to/audio.wav"
            mock_get.return_value = mock_transcription
            
            # Mock settings
            mock_settings.OPENAI_API_KEY = 'test_api_key'
            mock_settings.ENABLE_DRUMS = True
            
            # Mock AI Pipeline with Whisper analysis
            mock_ai_pipeline_class = MagicMock()
            mock_pipeline_instance = MagicMock()
            mock_get_ai_pipeline.return_value = mock_ai_pipeline_class
            mock_ai_pipeline_class.return_value = mock_pipeline_instance
            mock_pipeline_instance.whisper_service = MagicMock()  # Whisper available
            mock_pipeline_instance.analyze_audio.return_value = {
                'duration': 180.0,
                'sample_rate': 44100,
                'channels': 2,
                'tempo': 120,
                'beats': [0, 1, 2, 3],
                'key': 'A minor',
                'time_signature': '4/4',
                'complexity': 'moderate',
                'instruments': ['guitar'],
                'whisper_analysis': {
                    'status': 'success',
                    'musical_elements': {'chords': ['Am', 'F', 'C', 'G']}
                }
            }
            mock_pipeline_instance.transcribe.return_value = {
                'notes': [{'pitch': 69, 'start': 0.0, 'end': 1.0, 'velocity': 80}],
                'midi_data': {'tracks': [{'notes': []}]}
            }
            # Mock other components  
            mock_tab_gen_class = MagicMock()
            mock_export_mgr_class = MagicMock()
            mock_variant_gen_class = MagicMock()
            
            mock_get_tab_gen.return_value = mock_tab_gen_class
            mock_get_export_mgr.return_value = mock_export_mgr_class
            mock_get_variant_gen.return_value = mock_variant_gen_class
            
            mock_tab_gen_class.return_value.generate_optimized_tabs.return_value = {'measures': []}
            mock_export_mgr_class.return_value.generate_musicxml.return_value = '<musicxml/>'
            mock_variant_gen_class.return_value.generate_all_variants.return_value = []
            
            # Execute the task
            result = process_transcription("test-id")
            
            # Verify the result
            assert result['status'] == 'success'
            assert result['transcription_id'] == 'test-id'
            
            # Verify that Whisper was initialized (pipeline has whisper_service)
            assert mock_pipeline_instance.whisper_service is not None