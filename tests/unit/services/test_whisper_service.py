import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import json
import tempfile

from transcriber.services.whisper_service import WhisperService


class TestWhisperService:
    """Test Whisper AI service integration"""
    
    @pytest.fixture
    def whisper_service(self):
        """Create WhisperService instance with mocked OpenAI client"""
        with patch('transcriber.services.whisper_service.openai'):
            service = WhisperService(api_key='test-key', model='whisper-1')
            return service
    
    @pytest.fixture
    def sample_audio_file(self):
        """Create temporary audio file for testing"""
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
            f.write(b'fake audio data')
            return f.name
    
    def test_init_with_api_key(self):
        """Test WhisperService initialization with API key"""
        with patch('transcriber.services.whisper_service.openai') as mock_openai:
            service = WhisperService(api_key='test-key')
            assert service.model == 'whisper-1'
            assert service.client is not None
            mock_openai.OpenAI.assert_called_once_with(api_key='test-key')
    
    def test_init_without_api_key(self):
        """Test WhisperService initialization without API key"""
        service = WhisperService(api_key=None)
        assert service.client is None
        assert service.model == 'whisper-1'
    
    @patch('builtins.open', new_callable=MagicMock)
    def test_transcribe_audio_success(self, mock_open, whisper_service, sample_audio_file):
        """Test successful audio transcription"""
        # Mock the transcription response
        mock_response = Mock()
        mock_response.text = "This is a guitar solo in A minor"
        mock_response.segments = [
            {'start': 0.0, 'end': 2.0, 'text': 'This is a guitar solo'},
            {'start': 2.0, 'end': 4.0, 'text': 'in A minor'}
        ]
        
        whisper_service.client.audio.transcriptions.create = Mock(return_value=mock_response)
        
        result = whisper_service.transcribe_audio(sample_audio_file)
        
        assert result['text'] == "This is a guitar solo in A minor"
        assert len(result['segments']) == 2
        assert result['segments'][0]['text'] == 'This is a guitar solo'
        assert result['text'] == "This is a guitar solo in A minor"
    
    @patch('builtins.open', new_callable=MagicMock)
    def test_transcribe_audio_with_language(self, mock_open, whisper_service, sample_audio_file):
        """Test audio transcription with language parameter"""
        mock_response = Mock()
        mock_response.text = "Guitarra española"
        mock_response.segments = []
        
        whisper_service.client.audio.transcriptions.create = Mock(return_value=mock_response)
        
        result = whisper_service.transcribe_audio(sample_audio_file, language='es')
        
        whisper_service.client.audio.transcriptions.create.assert_called_once()
        call_args = whisper_service.client.audio.transcriptions.create.call_args
        assert call_args[1]['language'] == 'es'
    
    @patch('builtins.open', new_callable=MagicMock)
    def test_transcribe_audio_failure(self, mock_open, whisper_service, sample_audio_file):
        """Test audio transcription failure handling"""
        whisper_service.client.audio.transcriptions.create = Mock(
            side_effect=Exception("API Error")
        )
        
        result = whisper_service.transcribe_audio(sample_audio_file)
        
        assert result['status'] == 'error'
        assert 'API Error' in result['error']
        assert result['text'] == ''
    
    @patch('builtins.open', new_callable=MagicMock)
    def test_analyze_music(self, mock_open, whisper_service, sample_audio_file):
        """Test music analysis with Whisper"""
        mock_response = Mock()
        mock_response.text = """
        Guitar solo in A minor, tempo around 120 BPM.
        Chord progression: Am - F - C - G
        Playing techniques include bending and vibrato.
        """
        mock_response.segments = []
        
        whisper_service.client.audio.transcriptions.create = Mock(return_value=mock_response)
        
        result = whisper_service.analyze_music(sample_audio_file)
        
        assert result['status'] == 'success'
        assert 'A minor' in result['analysis']
        assert '120 BPM' in result['analysis']
        assert 'Am - F - C - G' in result['analysis']
        
        # Check that music-specific prompt was used
        call_args = whisper_service.client.audio.transcriptions.create.call_args
        assert 'tempo' in call_args[1]['prompt'].lower()
        assert 'chord' in call_args[1]['prompt'].lower()
    
    @patch('builtins.open', new_callable=MagicMock)
    def test_detect_chords_and_notes(self, mock_open, whisper_service, sample_audio_file):
        """Test chord and note detection"""
        mock_response = Mock()
        mock_response.text = """
        [0:00-0:04] Am chord strummed
        [0:04-0:08] F major chord, followed by single notes E, F, G
        [0:08-0:12] C major chord with bass note on 3rd fret
        [0:12-0:16] G major chord, quick transition
        """
        mock_response.segments = [
            {'start': 0.0, 'end': 4.0, 'text': 'Am chord strummed'},
            {'start': 4.0, 'end': 8.0, 'text': 'F major chord, followed by single notes E, F, G'},
            {'start': 8.0, 'end': 12.0, 'text': 'C major chord with bass note on 3rd fret'},
            {'start': 12.0, 'end': 16.0, 'text': 'G major chord, quick transition'}
        ]
        
        whisper_service.client.audio.transcriptions.create = Mock(return_value=mock_response)
        
        result = whisper_service.detect_chords_and_notes(sample_audio_file)
        
        assert result['status'] == 'success'
        assert len(result['segments']) == 4
        assert 'Am' in result['segments'][0]['text']
        assert result['segments'][1]['start'] == 4.0
        assert result['segments'][1]['end'] == 8.0
        
        # Verify chord progressions were extracted
        assert len(result['chord_progressions']) > 0
        assert 'Am' in result['chord_progressions'][0]
        
        # Verify individual notes were extracted
        assert 'E' in result['individual_notes']
        assert 'F' in result['individual_notes']
        assert 'G' in result['individual_notes']
    
    def test_extract_musical_elements(self, whisper_service):
        """Test extraction of musical elements from text"""
        text = """
        The song starts with an Am chord, transitions to F major.
        Then plays notes E, F#, G, and A.
        Tempo is approximately 120 BPM in 4/4 time.
        The key signature appears to be A minor.
        """
        
        result = whisper_service._extract_musical_elements(text)
        
        # Check chords
        assert 'Am' in result['chords']
        assert 'F' in result['chords']
        
        # Check notes
        assert 'E' in result['notes']
        assert 'F#' in result['notes']
        assert 'G' in result['notes']
        assert 'A' in result['notes']
        
        # Check tempo
        assert result['tempo'] == 120
        
        # Check time signature
        assert result['time_signature'] == '4/4'
        
        # Check key
        assert result['key'] == 'A minor'
    
    def test_extract_chord_progressions(self, whisper_service):
        """Test chord progression extraction"""
        segments = [
            {'start': 0.0, 'end': 4.0, 'text': 'Am chord strummed'},
            {'start': 4.0, 'end': 8.0, 'text': 'F major chord'},
            {'start': 8.0, 'end': 12.0, 'text': 'C chord with variation'},
            {'start': 12.0, 'end': 16.0, 'text': 'Back to G major'}
        ]
        
        progressions = whisper_service._extract_chord_progressions(segments)
        
        assert len(progressions) > 0
        assert 'Am' in progressions[0]
        assert 'F' in progressions[0]
        assert 'C' in progressions[0]
        assert 'G' in progressions[0]
    
    def test_no_client_fallback(self, whisper_service):
        """Test behavior when no client is configured"""
        whisper_service.client = None
        
        result = whisper_service.transcribe_audio('dummy.wav')
        assert result['status'] == 'error'
        assert 'not configured' in result['error']
        
        result = whisper_service.analyze_music('dummy.wav')
        assert result['status'] == 'error'
        assert 'not configured' in result['error']
        
        result = whisper_service.detect_chords_and_notes('dummy.wav')
        assert result['status'] == 'error'
        assert 'not configured' in result['error']
    
    def test_temperature_parameter(self, whisper_service):
        """Test temperature parameter in transcription"""
        with patch('builtins.open', new_callable=MagicMock):
            mock_response = Mock()
            mock_response.text = "Test"
            mock_response.segments = []
            
            whisper_service.client.audio.transcriptions.create = Mock(return_value=mock_response)
            
            # Test with custom temperature
            whisper_service.transcribe_audio('dummy.wav', temperature=0.5)
            
            call_args = whisper_service.client.audio.transcriptions.create.call_args
            assert call_args is not None
            assert call_args[1]['temperature'] == 0.5
            
            # Test with default temperature
            whisper_service.transcribe_audio('dummy.wav')
            call_args = whisper_service.client.audio.transcriptions.create.call_args
            assert call_args[1]['temperature'] == 0.0