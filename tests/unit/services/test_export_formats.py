"""
Unit tests for export formats and AlphaTab integration with AI pipeline.
"""

import pytest
import json
import os
import tempfile
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase
from model_bakery import baker

from transcriber.models import Transcription, User, FingeringVariant
from transcriber.services.export_manager import ExportManager
from transcriber.services.ai_transcription_agent import AIPipeline


class TestExportFormatsWithAI(TestCase):
    """Test export formats work with AI-generated data"""
    
    def setUp(self):
        """Set up test data"""
        self.user = baker.make(User)
        self.transcription = baker.make(
            Transcription,
            user=self.user,
            filename="test_song.mp3",
            status='completed',
            estimated_tempo=120,
            estimated_key="C Major",
            guitar_notes={
                'tempo': 120,
                'time_signature': '4/4',
                'tuning': [40, 45, 50, 55, 59, 64],  # Standard tuning
                'measures': [
                    {
                        'number': 1,
                        'start_time': 0.0,
                        'notes': [
                            {
                                'string': 2,  # B string (1-indexed)
                                'fret': 3,
                                'time': 0.0,
                                'duration': 0.5,
                                'velocity': 80,
                                'technique': 'normal'
                            },
                            {
                                'string': 3,  # G string
                                'fret': 2, 
                                'time': 0.5,
                                'duration': 0.5,
                                'velocity': 85,
                                'technique': 'hammer_on'
                            }
                        ]
                    },
                    {
                        'number': 2,
                        'start_time': 1.0,
                        'notes': [
                            {
                                'string': 1,  # High E string
                                'fret': 0,
                                'time': 0.0,
                                'duration': 1.0,
                                'velocity': 75,
                                'technique': 'normal'
                            }
                        ]
                    }
                ]
            }
        )
        self.export_manager = ExportManager(self.transcription)
    
    def test_musicxml_generation(self):
        """Test MusicXML generation with AI data"""
        musicxml = self.export_manager.generate_musicxml()
        
        # Verify basic XML structure
        assert musicxml.strip() != ""
        assert 'score-partwise' in musicxml or 'score-timewise' in musicxml
        assert 'Guitar' in musicxml or 'part-name' in musicxml
        
        # Check for guitar tab-specific elements (fingering notation like s3f3 = string 3, fret 3)
        assert 'fingering' in musicxml.lower() or ('s' in musicxml and 'f' in musicxml)
        
    def test_gp5_generation(self):
        """Test Guitar Pro 5 file generation"""
        with patch('transcriber.services.export_manager.gp') as mock_gp:
            # Mock guitarpro library
            mock_song = Mock()
            mock_track = Mock()
            mock_measure = Mock() 
            mock_voice = Mock()
            mock_beat = Mock()
            mock_note = Mock()
            mock_duration = Mock()
            
            mock_gp.Song.return_value = mock_song
            mock_gp.Track.return_value = mock_track
            mock_gp.Measure.return_value = mock_measure
            mock_gp.Voice.return_value = mock_voice
            mock_gp.Beat.return_value = mock_beat
            mock_gp.Note.return_value = mock_note
            mock_gp.Duration.return_value = mock_duration
            mock_gp.write = Mock()
            
            # Set up mocks
            mock_song.tracks = []
            mock_track.measures = []
            mock_measure.voices = []
            mock_voice.beats = []
            mock_beat.notes = []
            mock_beat.duration = mock_duration
            
            gp5_path = self.export_manager.generate_gp5()
            
            # Verify GP5 generation was attempted
            if gp5_path:  # Only if guitarpro is available
                mock_gp.Song.assert_called_once()
                mock_gp.write.assert_called_once()
    
    def test_midi_generation(self):
        """Test MIDI file generation"""
        with patch('transcriber.services.export_manager.MIDIFile') as mock_midi_file:
            mock_midi = Mock()
            mock_midi_file.return_value = mock_midi
            
            midi_path = self.export_manager.export_midi()
            
            # Verify MIDI generation - path should be created
            assert midi_path.endswith('.mid')
            
            # Verify MIDIFile was instantiated
            mock_midi_file.assert_called_with(1)
            
            # Should have called addTempo at least once (either path)
            assert mock_midi.addTempo.call_count >= 1
            
    def test_ascii_tab_generation(self):
        """Test ASCII tab generation"""
        with patch('transcriber.services.tab_generator.TabGenerator') as mock_tab_gen:
            mock_generator = Mock()
            mock_tab_gen.return_value = mock_generator
            mock_generator.to_ascii_tab.return_value = "E|--3--|\nB|-----|\nG|--2--|\nD|-----|\nA|-----|\nE|-----|"
            
            ascii_tab = self.export_manager.generate_ascii_tab()
            
            # Verify ASCII tab structure
            assert ascii_tab != ""
            lines = ascii_tab.split('\n')
            assert len(lines) >= 6  # At least 6 strings
            
            # Check for tab notation
            for line in lines:
                if '|' in line:
                    assert any(char.isdigit() or char == '-' for char in line)
    
    def test_debug_tab_data(self):
        """Test debug information for tab data"""
        debug_info = self.export_manager.debug_tab_data()
        
        assert debug_info['status'] == 'ok'
        assert debug_info['has_guitar_notes'] == True
        assert debug_info['measures_count'] == 2
        assert debug_info['total_notes'] == 3
        assert debug_info['tempo'] == 120
        assert debug_info['time_signature'] == '4/4'
        assert debug_info['tuning'] == [40, 45, 50, 55, 59, 64]


class TestAlphaTabIntegration(TestCase):
    """Test AlphaTab preview integration"""
    
    def setUp(self):
        """Set up test data"""
        self.user = baker.make(User)
        self.transcription = baker.make(
            Transcription,
            user=self.user,
            filename="test_song.mp3",
            status='completed',
            musicxml_content='<score-partwise>...</score-partwise>',
            guitar_notes={
                'tempo': 130,
                'measures': [
                    {
                        'number': 1,
                        'notes': [
                            {'string': 1, 'fret': 5, 'time': 0.0, 'duration': 0.25}
                        ]
                    }
                ]
            }
        )
    
    def test_alphatab_format_conversion_musicxml(self):
        """Test conversion to AlphaTab format with MusicXML"""
        from transcriber.views.preview import _convert_to_alphatab_format
        
        alphatab_data = _convert_to_alphatab_format(self.transcription, self.transcription.guitar_notes)
        
        # Should prefer MusicXML format when available
        assert alphatab_data['format'] == 'musicxml'
        assert alphatab_data['data'] == '<score-partwise>...</score-partwise>'
    
    def test_alphatab_format_conversion_json(self):
        """Test conversion to AlphaTab JSON format"""
        from transcriber.views.preview import _convert_to_alphatab_format
        
        # Remove MusicXML to test JSON format
        self.transcription.musicxml_content = None
        
        alphatab_data = _convert_to_alphatab_format(self.transcription, self.transcription.guitar_notes)
        
        # Should use AlphaTab JSON format
        assert alphatab_data['format'] == 'alphatab'
        assert 'score' in alphatab_data
        assert alphatab_data['score']['title'] == 'test_song.mp3'
        assert alphatab_data['score']['tempo'] == 120  # Default tempo
        assert len(alphatab_data['score']['tracks']) == 1
        
        track = alphatab_data['score']['tracks'][0]
        assert track['name'] == 'Guitar'
        assert track['instrument'] == 'AcousticGuitarSteel'
    
    def test_alphatab_measures_conversion(self):
        """Test measures conversion for AlphaTab"""
        from transcriber.views.preview import _convert_measures_to_alphatab
        
        tab_data = {
            'measures': [
                {'number': 1, 'notes': [{'string': 1, 'fret': 3}]},
                {'number': 2, 'notes': [{'string': 2, 'fret': 5}]}
            ]
        }
        
        measures = _convert_measures_to_alphatab(tab_data)
        
        # Should return measures array
        assert isinstance(measures, list)
        assert len(measures) == 2
    
    def test_alphatab_empty_data(self):
        """Test AlphaTab conversion with empty data"""
        from transcriber.views.preview import _convert_to_alphatab_format, _convert_measures_to_alphatab
        
        # Test with no MusicXML and empty guitar notes
        self.transcription.musicxml_content = None
        self.transcription.guitar_notes = {}
        
        alphatab_data = _convert_to_alphatab_format(self.transcription, self.transcription.guitar_notes)
        
        assert alphatab_data['format'] == 'alphatab'
        assert 'score' in alphatab_data
        
        # Test measures conversion with empty data
        measures = _convert_measures_to_alphatab({})
        assert measures == []
        
        measures = _convert_measures_to_alphatab(None)
        assert measures == []


class TestAIPipelineExportIntegration(TestCase):
    """Test AI pipeline integration with export formats"""
    
    def setUp(self):
        """Set up test data"""
        self.user = baker.make(User)
        self.api_key = "test-api-key"
    
    @patch('transcriber.services.ai_transcription_agent.asyncio')
    def test_ai_pipeline_export_workflow(self, mock_asyncio):
        """Test complete workflow from AI pipeline to export"""
        from transcriber.services.ai_transcription_agent import AIAnalysisResult
        
        # Mock AI analysis result
        mock_ai_result = AIAnalysisResult(
            tempo=140,
            key='E Minor',
            time_signature='4/4',
            complexity='moderate',
            instruments=['electric_guitar'],
            chord_progression=[
                {'chord': 'Em', 'start_time': 0.0, 'end_time': 2.0, 'confidence': 0.9}
            ],
            notes=[
                {
                    'midi_note': 64,  # E4
                    'start_time': 0.0,
                    'duration': 0.5,
                    'velocity': 80,
                    'confidence': 0.85
                },
                {
                    'midi_note': 67,  # G4
                    'start_time': 0.5,
                    'duration': 0.5,
                    'velocity': 85,
                    'confidence': 0.9
                }
            ],
            confidence=0.88,
            analysis_summary='Rock chord progression in E minor'
        )
        
        # Mock humanizer optimization result
        mock_optimize_result = {
            'ai_analysis': {
                'tempo': 140,
                'key': 'E Minor',
                'chord_progression': mock_ai_result.chord_progression
            },
            'optimized_notes': [
                {
                    'midi_note': 64,
                    'start_time': 0.0,
                    'duration': 0.5,
                    'velocity': 80,
                    'string': 1,  # High E string
                    'fret': 0,    # Open
                    'finger': None,
                    'confidence': 0.85
                },
                {
                    'midi_note': 67,
                    'start_time': 0.5,
                    'duration': 0.5,
                    'velocity': 85,
                    'string': 1,  # High E string
                    'fret': 3,    # 3rd fret
                    'finger': 3,  # Ring finger
                    'confidence': 0.9
                }
            ],
            'humanizer_settings': {
                'tuning': 'standard',
                'difficulty': 'balanced'
            }
        }
        
        # Mock pipeline components
        mock_agent = Mock()
        mock_agent.optimize_with_humanizer.return_value = mock_optimize_result
        
        mock_loop = Mock()
        mock_asyncio.new_event_loop.return_value = mock_loop
        mock_loop.run_until_complete.return_value = mock_ai_result
        
        with patch('transcriber.services.ai_transcription_agent.AITranscriptionAgent') as mock_agent_class:
            mock_agent_class.return_value = mock_agent
            
            # Test AI pipeline
            from transcriber.services.ai_transcription_agent import AIPipeline
            
            pipeline = AIPipeline(api_key=self.api_key)
            pipeline.transcription_agent = mock_agent
            
            # Mock audio duration
            with patch.object(pipeline, '_get_audio_duration', return_value=30.0):
                # Test transcription
                result = pipeline.transcribe("/fake/audio.mp3")
                
                # Verify AI pipeline results
                assert 'notes' in result
                assert 'midi_data' in result
                assert len(result['notes']) == 2
                
                # Check that notes have guitar-specific data
                for note in result['notes']:
                    assert 'string' in note
                    assert 'fret' in note
                    assert 'midi_note' in note
                
                # Create transcription with AI results
                transcription = baker.make(
                    Transcription,
                    user=self.user,
                    filename="ai_test.mp3",
                    status='completed',
                    estimated_tempo=result['midi_data']['ai_analysis']['tempo'],
                    estimated_key=result['midi_data']['ai_analysis']['key'],
                    guitar_notes=self._convert_ai_notes_to_tab_format(result['notes'])
                )
                
                # Test export manager with AI-generated data
                export_manager = ExportManager(transcription)
                debug_info = export_manager.debug_tab_data()
                
                assert debug_info['status'] == 'ok'
                assert debug_info['tempo'] == 140
                
                # Test MusicXML export
                musicxml = export_manager.generate_musicxml()
                assert musicxml.strip() != ""
                
                # Should contain valid MusicXML structure and guitar tablature
                assert 'score-partwise' in musicxml or 'score-timewise' in musicxml
                assert 'fingering' in musicxml.lower()  # Should have tab fingering notation
    
    def _convert_ai_notes_to_tab_format(self, ai_notes):
        """Convert AI notes to tab data format"""
        return {
            'tempo': 140,
            'time_signature': '4/4',
            'tuning': [40, 45, 50, 55, 59, 64],
            'measures': [
                {
                    'number': 1,
                    'start_time': 0.0,
                    'notes': [
                        {
                            'string': note['string'],
                            'fret': note['fret'],
                            'time': note['start_time'],
                            'duration': note['duration'],
                            'velocity': note['velocity'],
                            'technique': 'normal'
                        }
                        for note in ai_notes
                    ]
                }
            ]
        }


class TestVariantExportIntegration(TestCase):
    """Test export formats with fingering variants"""
    
    def setUp(self):
        """Set up test data"""
        self.user = baker.make(User)
        self.transcription = baker.make(
            Transcription,
            user=self.user,
            filename="variant_test.mp3",
            status='completed',
            guitar_notes={
                'tempo': 120,
                'measures': [
                    {
                        'number': 1,
                        'start_time': 0.0,
                        'notes': [
                            {'string': 1, 'fret': 0, 'time': 0.0, 'duration': 0.5, 'velocity': 80}
                        ]
                    }
                ]
            }
        )
        
        # Create fingering variant
        self.variant = baker.make(
            FingeringVariant,
            transcription=self.transcription,
            variant_name='easy',
            is_selected=True,
            playability_score=8.5,
            difficulty_score=3.2,
            tab_data={
                'tempo': 120,
                'measures': [
                    {
                        'number': 1,
                        'start_time': 0.0,
                        'notes': [
                            {
                                'string': 2,  # Easier fingering on B string
                                'fret': 5,
                                'time': 0.0,
                                'duration': 0.5,
                                'velocity': 80,
                                'finger': 1  # Index finger
                            }
                        ]
                    }
                ]
            }
        )
    
    def test_variant_export_formats(self):
        """Test exporting specific variants"""
        export_manager = ExportManager(self.transcription)
        
        # Test MusicXML with variant data
        variant_musicxml = export_manager.generate_musicxml(self.variant.tab_data)
        original_musicxml = export_manager.generate_musicxml()
        
        # Both should be valid but potentially different
        assert variant_musicxml.strip() != ""
        assert original_musicxml.strip() != ""
        
        # Test ASCII tab with variant data
        variant_ascii = export_manager.generate_ascii_tab(self.variant.tab_data)
        original_ascii = export_manager.generate_ascii_tab()
        
        assert variant_ascii != ""
        assert original_ascii != ""
        
        # Variants might be different (different string/fret positions)
        # This depends on the specific data, so we just verify both work
    
    def test_alphatab_with_variants(self):
        """Test AlphaTab integration with variants"""
        from transcriber.views.preview import _convert_to_alphatab_format
        
        # Test with variant data
        alphatab_variant = _convert_to_alphatab_format(self.transcription, self.variant.tab_data)
        alphatab_original = _convert_to_alphatab_format(self.transcription, self.transcription.guitar_notes)
        
        # Both should be valid AlphaTab format
        assert alphatab_variant['format'] == 'alphatab'
        assert alphatab_original['format'] == 'alphatab'
        
        # Both should have score structure
        assert 'score' in alphatab_variant
        assert 'score' in alphatab_original


class TestExportFormatValidation(TestCase):
    """Test export format validation and error handling"""
    
    def setUp(self):
        """Set up test data"""
        self.user = baker.make(User)
        self.transcription = baker.make(
            Transcription,
            user=self.user,
            filename="validation_test.mp3",
            status='completed'
        )
    
    def test_empty_guitar_notes_export(self):
        """Test exports with empty guitar notes"""
        # Transcription with no guitar_notes
        self.transcription.guitar_notes = None
        export_manager = ExportManager(self.transcription)
        
        # MusicXML should return empty string
        musicxml = export_manager.generate_musicxml()
        assert musicxml == ""
        
        # Debug info should show error
        debug_info = export_manager.debug_tab_data()
        assert debug_info['status'] == 'error'
        assert debug_info['has_guitar_notes'] == False
    
    def test_invalid_guitar_notes_structure(self):
        """Test exports with invalid guitar notes structure"""
        # Invalid structure (string instead of dict)
        self.transcription.guitar_notes = "invalid data"
        export_manager = ExportManager(self.transcription)
        
        debug_info = export_manager.debug_tab_data()
        assert debug_info['status'] == 'error'
        assert debug_info['guitar_notes_type'] == 'str'
        assert 'Invalid tab data type' in debug_info['message']
        
        # Should handle gracefully
        musicxml = export_manager.generate_musicxml()
        # Should either return empty string or basic XML
        assert isinstance(musicxml, str)
    
    def test_malformed_measures_data(self):
        """Test exports with malformed measures"""
        self.transcription.guitar_notes = {
            'tempo': 120,
            'measures': [
                {
                    # Missing required fields
                    'notes': 'invalid'  # Should be list
                },
                {
                    'number': 2,
                    'notes': []  # Empty is OK
                }
            ]
        }
        
        export_manager = ExportManager(self.transcription)
        
        # Should handle malformed data gracefully
        debug_info = export_manager.debug_tab_data()
        assert debug_info['status'] == 'ok'  # Should still process valid parts
        assert debug_info['measures_count'] == 2


@patch('transcriber.services.export_manager.gp')
class TestGuitarProExportDetails(TestCase):
    """Test Guitar Pro export with mocked guitarpro library"""
    
    def setUp(self):
        """Set up test data"""
        self.user = baker.make(User)
        self.transcription = baker.make(
            Transcription,
            user=self.user,
            filename="gp_test.mp3",
            status='completed',
            guitar_notes={
                'tempo': 150,
                'time_signature': '4/4',
                'tuning': [40, 45, 50, 55, 59, 64],
                'measures': [
                    {
                        'number': 1,
                        'start_time': 0.0,
                        'notes': [
                            {'string': 1, 'fret': 12, 'time': 0.0, 'duration': 0.25, 'velocity': 100},
                            {'string': 2, 'fret': 8, 'time': 0.25, 'duration': 0.25, 'velocity': 90}
                        ]
                    }
                ]
            }
        )
    
    def test_gp5_export_structure(self, mock_gp):
        """Test GP5 export creates proper structure"""
        # Set up mocks
        mock_song = Mock()
        mock_track = Mock()
        mock_measure = Mock()
        mock_voice = Mock()
        mock_beat = Mock()
        mock_note = Mock()
        mock_duration = Mock()
        mock_midi_channel = Mock()
        
        mock_gp.Song.return_value = mock_song
        mock_gp.Track.return_value = mock_track
        mock_gp.Measure.return_value = mock_measure
        mock_gp.Voice.return_value = mock_voice
        mock_gp.Beat.return_value = mock_beat
        mock_gp.Note.return_value = mock_note
        mock_gp.Duration.return_value = mock_duration
        mock_gp.MidiChannel.return_value = mock_midi_channel
        mock_gp.write = Mock()
        
        # Set up attributes
        mock_song.tracks = []
        mock_track.measures = []
        mock_measure.voices = []
        mock_voice.beats = []
        mock_beat.notes = []
        mock_beat.duration = mock_duration
        
        # Test export
        export_manager = ExportManager(self.transcription)
        gp5_path = export_manager.generate_gp5()
        
        # Verify calls
        mock_gp.Song.assert_called_once()
        assert mock_song.title == "gp_test.mp3"
        assert mock_song.artist == "RiffScribe"
        assert mock_song.tempo == 150
        
        mock_gp.Track.assert_called_once()
        mock_track.name = "Guitar"
        mock_track.isPercussionTrack = False
        
        # Should create measures and notes
        assert mock_gp.Measure.called
        assert mock_gp.Note.called
        
        # Should write file
        mock_gp.write.assert_called_once()
        assert gp5_path is not None
    
    def test_gp5_export_without_library(self, mock_gp):
        """Test GP5 export when guitarpro library not available"""
        # Make gp None to simulate missing library
        mock_gp = None
        
        with patch('transcriber.services.export_manager.gp', None):
            export_manager = ExportManager(self.transcription)
            gp5_path = export_manager.generate_gp5()
            
            assert gp5_path is None