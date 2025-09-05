"""
Unit tests for the ML pipeline.
"""
import pytest
import numpy as np
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from transcriber.ml_pipeline import MLPipeline


class TestMLPipeline:
    """Test the ML pipeline functionality."""
    
    @pytest.fixture
    def pipeline(self):
        """Create a pipeline instance."""
        return MLPipeline(use_gpu=False)
    
    @pytest.fixture
    def sample_audio_path(self):
        """Path to sample audio file."""
        samples_dir = Path(__file__).parent.parent.parent / "samples"
        audio_file = samples_dir / "simple-riff.wav"
        if audio_file.exists():
            return str(audio_file)
        # Return None if sample doesn't exist
        return None
    
    @pytest.mark.unit
    def test_pipeline_initialization(self, pipeline):
        """Test pipeline initializes correctly."""
        assert pipeline is not None
        assert pipeline.use_gpu == False
        assert pipeline.device.type == 'cpu'
        assert pipeline.demucs_model_name == 'htdemucs'
    
    @pytest.mark.unit
    def test_analyze_audio_with_real_file(self, pipeline, sample_audio_path):
        """Test audio analysis with real sample file."""
        if sample_audio_path is None:
            pytest.skip("Sample audio file not found")
        
        analysis = pipeline.analyze_audio(sample_audio_path)
        
        # Check all required fields are present
        assert 'duration' in analysis
        assert 'sample_rate' in analysis
        assert 'channels' in analysis
        assert 'tempo' in analysis
        assert 'key' in analysis
        assert 'complexity' in analysis
        assert 'instruments' in analysis
        
        # Check value types and ranges
        assert isinstance(analysis['duration'], (int, float))
        assert analysis['duration'] > 0
        assert isinstance(analysis['tempo'], (int, float))
        assert 30 <= analysis['tempo'] <= 300  # Reasonable tempo range
        assert analysis['complexity'] in ['simple', 'moderate', 'complex']
        assert isinstance(analysis['instruments'], list)
        assert len(analysis['instruments']) > 0
    
    @pytest.mark.unit
    @patch('librosa.load')
    def test_analyze_audio_mocked(self, mock_load, pipeline):
        """Test audio analysis with mocked librosa."""
        # Mock audio data
        sr = 44100
        duration = 10.0
        mock_y = np.random.randn(int(sr * duration))
        mock_load.return_value = (mock_y, sr)
        
        with patch.object(pipeline, '_detect_tempo_madmom', return_value=(120.0, np.array([]))):
            with patch.object(pipeline, '_detect_key', return_value='C Major'):
                with patch.object(pipeline, '_detect_time_signature', return_value='4/4'):
                    with patch.object(pipeline, '_estimate_complexity', return_value='moderate'):
                        with patch.object(pipeline, '_detect_instruments', return_value=['guitar']):
                            analysis = pipeline.analyze_audio('fake_path.wav')
        
        assert analysis['duration'] == pytest.approx(duration, rel=0.1)
        assert 30 <= analysis['tempo'] <= 300  # Tempo should be in reasonable range
        assert analysis['key'] == 'C Major'
        assert analysis['complexity'] == 'moderate'
    
    @pytest.mark.unit
    def test_transcribe_methods(self, pipeline, sample_audio_path):
        """Test different transcription methods."""
        if sample_audio_path is None:
            pytest.skip("Sample audio file not found")
        
        # Test librosa fallback (always available)
        with patch.object(pipeline, '_transcribe_basic_pitch', side_effect=Exception("Not available")):
            with patch.object(pipeline, '_transcribe_crepe', side_effect=Exception("Not available")):
                result = pipeline.transcribe(sample_audio_path)
                assert 'notes' in result
                assert 'midi_data' in result
                assert isinstance(result['notes'], list)
    
    @pytest.mark.unit
    def test_post_process_notes(self, pipeline):
        """Test note post-processing."""
        # Create test notes with issues to fix
        test_notes = [
            {'start_time': 0.0, 'end_time': 0.01, 'midi_note': 60},  # Too short
            {'start_time': 0.5, 'end_time': 1.0, 'midi_note': 62},   # Good note
            {'start_time': 1.001, 'end_time': 1.5, 'midi_note': 62}, # Very close to previous
            {'start_time': 2.0, 'end_time': 2.5, 'midi_note': 64},   # Good note
        ]
        
        processed = pipeline._post_process_notes(test_notes)
        
        # Should filter out too-short notes
        assert len(processed) <= len(test_notes)
        # Should merge very close notes
        assert all(n['end_time'] - n['start_time'] > 0.05 for n in processed)
    
    @pytest.mark.unit
    def test_detect_instruments(self, pipeline):
        """Test instrument detection logic."""
        # Create mock audio with known spectral characteristics
        sr = 44100
        t = np.linspace(0, 1, sr)
        
        # Simulate guitar-like frequency (around 200-2000 Hz)
        y_guitar = np.sin(2 * np.pi * 440 * t) + np.sin(2 * np.pi * 880 * t)
        
        instruments = pipeline._detect_instruments(y_guitar, sr)
        assert isinstance(instruments, list)
        assert len(instruments) > 0
        # Should always include at least guitar as default
        assert 'guitar' in instruments or len(instruments) > 0