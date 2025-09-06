"""
Unit tests for the AI transcription agent
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from transcriber.services.ai_transcription_agent import (
    AITranscriptionAgent, AIDrumAgent, AIAnalysisResult
)
from transcriber.services.humanizer_service import Note


class TestAITranscriptionAgent:
    """Test the AI transcription agent"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.api_key = "test-api-key"
        
    def test_agent_initialization_with_api_key(self):
        """Test agent initializes with API key"""
        agent = AITranscriptionAgent(api_key=self.api_key)
        assert agent.api_key == self.api_key
        assert agent.max_file_size == 25 * 1024 * 1024
        
    def test_agent_initialization_without_api_key(self):
        """Test agent raises error without API key"""
        with pytest.raises(ValueError, match="OpenAI API key is required"):
            AITranscriptionAgent(api_key="")
    
    @patch('transcriber.services.ai_transcription_agent.os.path.getsize')
    async def test_prepare_audio_small_file(self, mock_getsize):
        """Test audio preparation for small files"""
        mock_getsize.return_value = 1024 * 1024  # 1MB
        
        agent = AITranscriptionAgent(api_key=self.api_key)
        audio_path = "/path/to/audio.mp3"
        
        result = await agent._prepare_audio(audio_path)
        assert result == audio_path  # Should return unchanged
        
    @patch('transcriber.services.ai_transcription_agent.os.path.getsize')
    async def test_prepare_audio_large_file(self, mock_getsize):
        """Test audio preparation for large files"""
        mock_getsize.return_value = 30 * 1024 * 1024  # 30MB
        
        agent = AITranscriptionAgent(api_key=self.api_key)
        
        with patch.object(agent, '_compress_audio', new_callable=AsyncMock) as mock_compress:
            mock_compress.return_value = "/path/to/compressed.mp3"
            
            result = await agent._prepare_audio("/path/to/audio.wav")
            
            mock_compress.assert_called_once()
            assert result == "/path/to/compressed.mp3"
    
    @patch('builtins.open', create=True)
    @patch('transcriber.services.ai_transcription_agent.OpenAI')
    async def test_whisper_transcribe(self, mock_openai, mock_open):
        """Test Whisper transcription"""
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.text = "Test transcription"
        mock_response.segments = [{"start": 0.0, "end": 5.0, "text": "Test"}]
        mock_response.language = "en"
        mock_response.duration = 5.0
        
        mock_client = Mock()
        mock_client.audio.transcriptions.create.return_value = mock_response
        mock_openai.return_value = mock_client
        
        mock_file = Mock()
        mock_open.return_value.__enter__.return_value = mock_file
        
        agent = AITranscriptionAgent(api_key=self.api_key)
        agent.client = mock_client
        
        result = await agent._whisper_transcribe("/path/to/audio.mp3")
        
        assert result['text'] == "Test transcription"
        assert result['language'] == "en"
        assert result['duration'] == 5.0
        assert len(result['segments']) == 1
    
    def test_combine_analysis_results(self):
        """Test combining Whisper and GPT-4 analysis"""
        agent = AITranscriptionAgent(api_key=self.api_key)
        
        whisper_result = {
            'text': 'Test transcription',
            'duration': 5.0
        }
        
        musical_analysis = {
            'tempo': 120,
            'key': 'C Major',
            'time_signature': '4/4',
            'complexity': 'moderate',
            'instruments': ['guitar'],
            'chord_progression': [],
            'notes': [
                {'midi_note': 60, 'start_time': 0.0, 'end_time': 1.0, 'velocity': 80}
            ],
            'confidence': 0.8,
            'analysis_summary': 'Test analysis'
        }
        
        result = agent._combine_analysis_results(whisper_result, musical_analysis)
        
        assert isinstance(result, AIAnalysisResult)
        assert result.tempo == 120
        assert result.key == 'C Major'
        assert result.complexity == 'moderate'
        assert len(result.notes) == 1
        assert result.confidence == 0.8
    
    def test_combine_analysis_invalid_notes(self):
        """Test combining analysis with invalid note data"""
        agent = AITranscriptionAgent(api_key=self.api_key)
        
        whisper_result = {'text': 'Test'}
        musical_analysis = {
            'tempo': 120,
            'notes': [
                {'midi_note': 'invalid', 'start_time': 0.0},  # Invalid midi_note
                {'midi_note': 60, 'start_time': 0.0, 'end_time': 1.0, 'velocity': 80}  # Valid
            ],
            'key': 'C Major'
        }
        
        result = agent._combine_analysis_results(whisper_result, musical_analysis)
        
        # Should skip invalid note and include valid one
        assert len(result.notes) == 1
        assert result.notes[0]['midi_note'] == 60
    
    def test_fallback_analysis(self):
        """Test fallback analysis when AI fails"""
        agent = AITranscriptionAgent(api_key=self.api_key)
        
        result = agent._fallback_analysis("Error text")
        
        assert result['tempo'] == 120
        assert result['key'] == 'C Major'
        assert result['complexity'] == 'moderate'
        assert result['instruments'] == ['guitar']
        assert result['confidence'] == 0.5
        assert 'Error text' in result['analysis_summary']


class TestAIDrumAgent:
    """Test the AI drum agent"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.api_key = "test-api-key"
        
    def test_drum_agent_initialization(self):
        """Test drum agent initializes correctly"""
        agent = AIDrumAgent(api_key=self.api_key)
        assert agent.api_key == self.api_key
        
    def test_drum_agent_no_api_key(self):
        """Test drum agent raises error without API key"""
        with pytest.raises(ValueError, match="OpenAI API key is required"):
            AIDrumAgent(api_key="")
    
    def test_generate_drum_tab(self):
        """Test drum tab generation"""
        agent = AIDrumAgent(api_key=self.api_key)
        
        drum_data = {
            'tempo': 140,
            'drum_hits': [
                {'drum_type': 'kick', 'time': 0.0, 'velocity': 0.8},
                {'drum_type': 'snare', 'time': 0.5, 'velocity': 0.7}
            ]
        }
        
        tab = agent._generate_drum_tab(drum_data)
        
        assert 'Tempo: 140 BPM' in tab
        assert 'Time: 4/4' in tab
        assert 'HH |' in tab
        assert 'SD |' in tab
        assert 'BD |' in tab
    
    def test_generate_drum_tab_empty(self):
        """Test drum tab generation with no hits"""
        agent = AIDrumAgent(api_key=self.api_key)
        
        drum_data = {'tempo': 120, 'drum_hits': []}
        
        tab = agent._generate_drum_tab(drum_data)
        
        assert 'Tempo: 120 BPM' in tab
        assert 'No drum hits detected' in tab
    
    def test_fallback_drum_analysis(self):
        """Test fallback drum analysis"""
        agent = AIDrumAgent(api_key=self.api_key)
        
        result = agent._fallback_drum_analysis()
        
        assert result['tempo'] == 120
        assert result['time_signature'] == '4/4'
        assert result['drum_hits'] == []
        assert 'error' in result
        assert result['patterns']['main_pattern'] == 'unknown'


class TestAITranscriptionIntegration:
    """Integration tests for AI transcription"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.api_key = "test-api-key"
    
    @patch('transcriber.services.ai_transcription_agent.HumanizerService')
    def test_optimize_with_humanizer_success(self, mock_humanizer_class):
        """Test successful humanizer optimization"""
        # Mock humanizer
        mock_humanizer = Mock()
        mock_choice = Mock()
        mock_choice.string = 3
        mock_choice.fret = 5
        mock_choice.finger = 2
        mock_humanizer.optimize_sequence.return_value = [mock_choice]
        mock_humanizer_class.return_value = mock_humanizer
        
        agent = AITranscriptionAgent(api_key=self.api_key)
        
        # Create AI result
        ai_result = AIAnalysisResult(
            tempo=120,
            key='C Major',
            time_signature='4/4',
            complexity='moderate',
            instruments=['guitar'],
            chord_progression=[],
            notes=[{
                'midi_note': 60,
                'start_time': 0.0,
                'duration': 1.0,
                'velocity': 80,
                'confidence': 0.8
            }],
            confidence=0.8,
            analysis_summary='Test'
        )
        
        result = agent.optimize_with_humanizer(ai_result)
        
        assert 'ai_analysis' in result
        assert 'optimized_notes' in result
        assert 'humanizer_settings' in result
        assert len(result['optimized_notes']) == 1
        assert result['optimized_notes'][0]['string'] == 3
        assert result['optimized_notes'][0]['fret'] == 5
        assert result['optimized_notes'][0]['finger'] == 2
    
    @patch('transcriber.services.ai_transcription_agent.HumanizerService')
    def test_optimize_with_humanizer_failure(self, mock_humanizer_class):
        """Test humanizer optimization failure fallback"""
        # Mock humanizer to raise exception
        mock_humanizer_class.side_effect = Exception("Humanizer failed")
        
        agent = AITranscriptionAgent(api_key=self.api_key)
        
        ai_result = AIAnalysisResult(
            tempo=120,
            key='C Major', 
            time_signature='4/4',
            complexity='moderate',
            instruments=['guitar'],
            chord_progression=[],
            notes=[{
                'midi_note': 60,
                'start_time': 0.0,
                'duration': 1.0,
                'velocity': 80
            }],
            confidence=0.8,
            analysis_summary='Test'
        )
        
        result = agent.optimize_with_humanizer(ai_result)
        
        # Should fallback to unoptimized notes
        assert 'ai_analysis' in result
        assert 'optimized_notes' in result
        assert 'error' in result['humanizer_settings']
        assert len(result['optimized_notes']) == 1