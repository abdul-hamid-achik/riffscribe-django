"""
Unit tests for the AI pipeline
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from transcriber.services.ai_transcription_agent import AIPipeline, AIMultiTrackService
from transcriber.services.ai_transcription_agent import AIAnalysisResult


class TestAIPipeline:
    """Test the AI pipeline"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.api_key = "test-api-key"
        
    def test_pipeline_initialization(self):
        """Test pipeline initializes correctly"""
        with patch('transcriber.services.ai_transcription_agent.AITranscriptionAgent'):
            with patch('transcriber.services.ai_transcription_agent.AIDrumAgent'):
                pipeline = AIPipeline(api_key=self.api_key)
                assert pipeline.api_key == self.api_key
                assert pipeline.enable_drums is True
    
    def test_pipeline_initialization_no_drums(self):
        """Test pipeline without drums"""
        with patch('transcriber.services.ai_transcription_agent.AITranscriptionAgent'):
            pipeline = AIPipeline(api_key=self.api_key, enable_drums=False)
            assert pipeline.enable_drums is False
            assert pipeline.drum_agent is None
    
    def test_pipeline_no_api_key(self):
        """Test pipeline raises error without API key"""
        with pytest.raises(ValueError, match="OpenAI API key is required"):
            AIPipeline(api_key="")
    
    @patch('transcriber.services.ai_transcription_agent.asyncio')
    def test_analyze_audio_success(self, mock_asyncio):
        """Test successful audio analysis"""
        # Mock AI result
        mock_ai_result = AIAnalysisResult(
            tempo=120,
            key='C Major',
            time_signature='4/4',
            complexity='moderate',
            instruments=['guitar'],
            chord_progression=[],
            notes=[],
            confidence=0.8,
            analysis_summary='Test analysis'
        )
        
        # Mock transcription agent
        mock_agent = Mock()
        mock_loop = Mock()
        mock_asyncio.new_event_loop.return_value = mock_loop
        mock_loop.run_until_complete.return_value = mock_ai_result
        
        with patch('transcriber.services.ai_transcription_agent.AITranscriptionAgent') as mock_agent_class:
            mock_agent_class.return_value = mock_agent
            
            pipeline = AIPipeline(api_key=self.api_key)
            pipeline.transcription_agent = mock_agent
            
            with patch.object(pipeline, '_get_audio_duration', return_value=60.0):
                result = pipeline.analyze_audio("/path/to/audio.mp3")
            
            assert result['tempo'] == 120
            assert result['key'] == 'C Major'
            assert result['complexity'] == 'moderate'
            assert result['instruments'] == ['guitar']
            assert 'ai_analysis' in result
    
    def test_analyze_audio_fallback(self):
        """Test audio analysis fallback"""
        with patch('transcriber.services.ai_transcription_agent.AITranscriptionAgent'):
            with patch('transcriber.services.ai_transcription_agent.AIDrumAgent'):
                pipeline = AIPipeline(api_key=self.api_key)
                
                # Mock exception during analysis
                with patch('transcriber.services.ai_transcription_agent.asyncio.new_event_loop') as mock_loop:
                    mock_loop.side_effect = Exception("Analysis failed")
                    
                    with patch.object(pipeline, '_get_audio_duration', return_value=60.0):
                        result = pipeline.analyze_audio("/path/to/audio.mp3")
                    
                    # Should use fallback
                    assert result['tempo'] == 120.0
                    assert result['key'] == 'C Major'
                    assert result['complexity'] == 'moderate'
                    assert result['instruments'] == ['guitar']
    
    @patch('transcriber.services.ai_transcription_agent.asyncio')
    def test_transcribe_with_context(self, mock_asyncio):
        """Test transcription with user context"""
        # Mock AI result with notes
        mock_ai_result = AIAnalysisResult(
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
        
        # Mock optimize_with_humanizer result
        mock_optimize_result = {
            'ai_analysis': {
                'tempo': 120,
                'key': 'C Major',
                'chord_progression': []
            },
            'optimized_notes': [{
                'midi_note': 60,
                'start_time': 0.0,
                'string': 3,
                'fret': 5
            }],
            'humanizer_settings': {}
        }
        
        mock_agent = Mock()
        mock_agent.optimize_with_humanizer.return_value = mock_optimize_result
        
        mock_loop = Mock()
        mock_asyncio.new_event_loop.return_value = mock_loop
        mock_loop.run_until_complete.return_value = mock_ai_result
        
        with patch('transcriber.services.ai_transcription_agent.AITranscriptionAgent'):
            pipeline = AIPipeline(api_key=self.api_key)
            pipeline.transcription_agent = mock_agent
            
            context = {
                'tuning': 'drop_d',
                'difficulty': 'technical'
            }
            
            result = pipeline.transcribe("/path/to/audio.mp3", context=context)
            
            assert 'notes' in result
            assert 'midi_data' in result
            assert 'chord_data' in result
            assert len(result['notes']) == 1
            
            # Check that humanizer was called with context
            mock_agent.optimize_with_humanizer.assert_called_once_with(
                mock_ai_result,
                tuning='drop_d',
                difficulty='technical'
            )
    
    def test_separate_sources(self):
        """Test AI source separation (lightweight)"""
        with patch('transcriber.services.ai_transcription_agent.AITranscriptionAgent'):
            pipeline = AIPipeline(api_key=self.api_key)
            
            result = pipeline.separate_sources("/path/to/audio.mp3")
            
            assert result['original'] == "/path/to/audio.mp3"
            assert 'analysis' in result
    
    @patch('transcriber.services.ai_transcription_agent.asyncio')
    def test_process_drum_track_enabled(self, mock_asyncio):
        """Test drum track processing when enabled"""
        mock_drum_result = {
            'tempo': 120,
            'drum_hits': [{'drum_type': 'kick', 'time': 0.0}],
            'patterns': {}
        }
        
        mock_drum_agent = Mock()
        mock_loop = Mock()
        mock_asyncio.new_event_loop.return_value = mock_loop
        mock_loop.run_until_complete.return_value = mock_drum_result
        
        with patch('transcriber.services.ai_transcription_agent.AITranscriptionAgent'):
            with patch('transcriber.services.ai_transcription_agent.AIDrumAgent'):
                pipeline = AIPipeline(api_key=self.api_key, enable_drums=True)
                pipeline.drum_agent = mock_drum_agent
                
                result = pipeline.process_drum_track("/path/to/drums.mp3")
                
                assert result['tempo'] == 120
                assert len(result['drum_hits']) == 1
    
    def test_process_drum_track_disabled(self):
        """Test drum track processing when disabled"""
        with patch('transcriber.services.ai_transcription_agent.AITranscriptionAgent'):
            pipeline = AIPipeline(api_key=self.api_key, enable_drums=False)
            
            result = pipeline.process_drum_track("/path/to/drums.mp3")
            
            assert 'error' in result
            assert 'not enabled' in result['error']
    
    @patch('transcriber.services.ai_transcription_agent.AudioSegment')
    def test_get_audio_duration(self, mock_audiosegment):
        """Test getting audio duration"""
        mock_audio = Mock()
        mock_audio.__len__.return_value = 60000  # 60 seconds in ms
        mock_audiosegment.from_file.return_value = mock_audio
        
        with patch('transcriber.services.ai_transcription_agent.AITranscriptionAgent'):
            pipeline = AIPipeline(api_key=self.api_key)
            
            duration = pipeline._get_audio_duration("/path/to/audio.mp3")
            
            assert duration == 60.0
    
    def test_generate_beats(self):
        """Test beat generation"""
        with patch('transcriber.services.ai_transcription_agent.AITranscriptionAgent'):
            pipeline = AIPipeline(api_key=self.api_key)
            
            beats = pipeline._generate_beats(120.0, 4.0)  # 120 BPM, 4 seconds
            
            # Should have 8 beats (120 BPM = 2 beats per second * 4 seconds)
            assert len(beats) == 8
            assert beats[0] == 0.0
            assert beats[1] == 0.5
            assert beats[-1] == 3.5
    
    def test_get_pipeline_info(self):
        """Test pipeline info"""
        with patch('transcriber.services.ai_transcription_agent.AITranscriptionAgent'):
            with patch('transcriber.services.ai_transcription_agent.AIDrumAgent'):
                pipeline = AIPipeline(api_key=self.api_key)
                
                info = pipeline.get_pipeline_info()
                
                assert info['type'] == 'ai_pipeline'
                assert info['ai_enabled'] is True
                assert info['drum_enabled'] is True
                assert info['openai_api_configured'] is True
                assert 'openai' in info['dependencies']
                assert info['traditional_ml_models'] is None
                assert info['memory_usage'] == 'low'
                assert info['build_time'] == 'fast'


class TestAIMultiTrackService:
    """Test the AI multi-track service"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.api_key = "test-api-key"
    
    def test_multitrack_initialization(self):
        """Test multi-track service initializes"""
        with patch('transcriber.services.ai_transcription_agent.AIPipeline'):
            service = AIMultiTrackService(api_key=self.api_key)
            assert service.api_key == self.api_key
    
    def test_map_instrument_to_track_type(self):
        """Test instrument to track type mapping"""
        with patch('transcriber.services.ai_transcription_agent.AIPipeline'):
            service = AIMultiTrackService(api_key=self.api_key)
            
            assert service._map_instrument_to_track_type('guitar') == 'other'
            assert service._map_instrument_to_track_type('electric_guitar') == 'other'
            assert service._map_instrument_to_track_type('bass') == 'bass'
            assert service._map_instrument_to_track_type('drums') == 'drums'
            assert service._map_instrument_to_track_type('vocals') == 'vocals'
            assert service._map_instrument_to_track_type('unknown') == 'other'
    
    @patch('transcriber.services.ai_transcription_agent.Track')
    def test_process_transcription(self, mock_track_model):
        """Test processing transcription with AI multi-track"""
        # Mock transcription object
        mock_transcription = Mock()
        mock_transcription.filename = "test.mp3"
        mock_transcription.original_audio.path = "/path/to/audio.mp3"
        
        # Mock track creation
        mock_track = Mock()
        mock_track_model.objects.create.return_value = mock_track
        
        # Mock pipeline analysis
        mock_pipeline = Mock()
        mock_analysis = {
            'instruments': ['guitar', 'drums', 'bass'],
            'tempo': 120
        }
        mock_pipeline.analyze_audio.return_value = mock_analysis
        
        # Mock transcription results
        mock_transcription_result = {
            'notes': [{'midi_note': 60}],
            'midi_data': {'tempo': 120},
            'chord_data': []
        }
        mock_pipeline.transcribe.return_value = mock_transcription_result
        
        # Mock drum results
        mock_drum_result = {
            'tempo': 120,
            'drum_hits': [{'drum_type': 'kick'}],
            'drum_tab': 'BD |o---|'
        }
        mock_pipeline.process_drum_track.return_value = mock_drum_result
        
        with patch('transcriber.services.ai_transcription_agent.AIPipeline') as mock_pipeline_class:
            mock_pipeline_class.return_value = mock_pipeline
            
            service = AIMultiTrackService(api_key=self.api_key)
            service.pipeline = mock_pipeline
            
            tracks = service.process_transcription(mock_transcription)
            
            # Should create 3 tracks (guitar, drums, bass)
            assert mock_track_model.objects.create.call_count == 3
            assert len(tracks) == 3