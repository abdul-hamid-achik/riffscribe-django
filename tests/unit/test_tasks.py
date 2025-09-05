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
        with patch('transcriber.tasks.Transcription.objects.get') as mock_get:
            mock_get.return_value = completed_transcription
            
            with patch('transcriber.tasks.MLPipeline') as mock_pipeline:
                mock_ml = MagicMock()
                mock_pipeline.return_value = mock_ml
                
                # Mock analysis results
                mock_ml.analyze_audio.return_value = {
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
                mock_ml.transcribe.return_value = {
                    'notes': [
                        {'start_time': 0, 'end_time': 0.5, 'midi_note': 60, 'velocity': 80}
                    ],
                    'midi_data': {'notes': [{'midi_note': 60, 'velocity': 80}]}
                }
                
                with patch('transcriber.tasks.TabGenerator') as mock_tab_gen:
                    mock_gen = MagicMock()
                    mock_tab_gen.return_value = mock_gen
                    mock_gen.generate_optimized_tabs.return_value = {
                        'tempo': 120,
                        'measures': []
                    }
                    mock_gen.to_ascii_tab.return_value = "ASCII_TAB"
                    
                    with patch('transcriber.tasks.ExportManager') as mock_export_mgr, \
                         patch('transcriber.tasks.VariantGenerator') as mock_variant_gen, \
                         patch('transcriber.tasks.process_transcription.update_state') as mock_update_state:
                        
                        # Mock export manager
                        mock_export = MagicMock()
                        mock_export_mgr.return_value = mock_export
                        mock_export.generate_musicxml.return_value = '<musicxml>test</musicxml>'
                        mock_export.generate_gp5.return_value = '/tmp/test.gp5'
                        
                        # Mock variant generator
                        mock_var_gen = MagicMock()
                        mock_variant_gen.return_value = mock_var_gen
                        mock_var_gen.generate_all_variants.return_value = []
                        
                        # Execute task
                        result = process_transcription(str(completed_transcription.id))
                        
                        assert result['status'] == 'success'
                        assert 'duration' in result
                        mock_update_state.assert_called()
    
    @pytest.mark.unit
    def test_process_transcription_error_handling(self, sample_transcription):
        """Test error handling in transcription processing."""
        with patch('transcriber.tasks.Transcription.objects.get') as mock_get:
            mock_get.return_value = sample_transcription
            
            with patch('transcriber.tasks.MLPipeline') as mock_pipeline:
                mock_pipeline.side_effect = Exception("ML Pipeline Error")
                
                with patch.object(sample_transcription, 'save'):
                    result = process_transcription(str(sample_transcription.id))
                    
                    assert result['status'] == 'failed'
                    assert 'error' in result
                    assert sample_transcription.status == 'failed'
    
    @pytest.mark.unit
    def test_generate_export_musicxml(self, completed_transcription):
        """Test MusicXML export generation."""
        with patch('transcriber.tasks.Transcription.objects.get') as mock_get:
            mock_get.return_value = completed_transcription
            
            with patch('transcriber.tasks.ExportManager') as mock_export:
                mock_manager = MagicMock()
                mock_export.return_value = mock_manager
                mock_manager.generate_musicxml.return_value = "<musicxml>content</musicxml>"
                
                with patch('transcriber.tasks.TabExport') as mock_tab_export:
                    mock_tab_export.objects.create.return_value = MagicMock(id=1)
                    
                    result = generate_export(str(completed_transcription.id), 'musicxml')
                    
                    assert result['status'] == 'completed'
                    assert result['format'] == 'musicxml'
                    mock_manager.generate_musicxml.assert_called_once()
    
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
                
                assert result['status'] == 'completed'
                assert result['format'] == 'midi'
    
    @pytest.mark.unit
    def test_generate_export_ascii(self, completed_transcription):
        """Test ASCII tab export generation."""
        with patch('transcriber.tasks.Transcription.objects.get') as mock_get:
            mock_get.return_value = completed_transcription
            completed_transcription.ascii_tab = "e|---0---1---3---|\nB|---1---1---0---|"
            
            with patch('transcriber.tasks.TabExport') as mock_tab_export:
                mock_tab_export.objects.create.return_value = MagicMock(id=1)
                
                result = generate_export(str(completed_transcription.id), 'ascii')
                
                assert result['status'] == 'completed'
                assert result['format'] == 'ascii'
    
    
    @pytest.mark.unit
    def test_task_state_updates(self):
        """Test that tasks properly update their state during execution."""
        from transcriber.tasks import process_transcription
        
        with patch('transcriber.tasks.logger') as mock_task:
            mock_task.update_state = MagicMock()
            
            with patch('transcriber.tasks.Transcription.objects.get') as mock_get:
                mock_transcription = MagicMock()
                mock_transcription.id = "test-id"
                mock_transcription.original_audio.path = "/test/path.wav"
                mock_get.return_value = mock_transcription
                
                with patch('transcriber.tasks.MLPipeline'):
                    # This should fail but we want to check state updates
                    try:
                        process_transcription("test-id")
                    except:
                        pass
                    
                    # Check that update_state was called with PROGRESS
                    calls = mock_task.method_calls
                    assert any('PROGRESS' in str(call) for call in calls)


@pytest.mark.django_db
class TestTasksWithWhisper:
    """Test Celery tasks with Whisper AI integration"""
    
    @pytest.mark.integration
    @pytest.mark.django_db
    def test_process_transcription_with_whisper(self):
        """Test transcription processing with Whisper enhancement"""
        from model_bakery import baker
        from transcriber.models import Transcription
        
        transcription = baker.make(Transcription, filename='test_song.mp3', status='pending')
        
        with patch('transcriber.tasks.MLPipeline') as mock_ml_pipeline, \
             patch('transcriber.tasks.TabGenerator') as mock_tab_gen, \
             patch('transcriber.tasks.ExportManager') as mock_export_mgr, \
             patch('transcriber.tasks.VariantGenerator') as mock_variant_gen:
            
            # Mock ML Pipeline with Whisper analysis
            mock_pipeline_instance = MagicMock()
            mock_pipeline_instance.whisper_service = MagicMock()  # Whisper available
            mock_pipeline_instance.analyze_audio.return_value = {
                'duration': 180.0,
                'tempo': 120,
                'key': 'A minor',
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
            mock_ml_pipeline.return_value = mock_pipeline_instance
            
            # Mock other components
            mock_tab_gen.return_value.generate_optimized_tabs.return_value = {'measures': []}
            mock_export_mgr.return_value.generate_musicxml.return_value = '<musicxml/>'
            mock_variant_gen.return_value.generate_all_variants.return_value = []
            
            # Mock file path
            with patch.object(transcription, 'original_audio') as mock_audio:
                mock_audio.path = '/path/to/audio.mp3'
                
                # Execute the task
                result = process_transcription.run(transcription.id)
            
            # Verify the result
            assert result['status'] == 'success'
            assert result['transcription_id'] == str(transcription.id)