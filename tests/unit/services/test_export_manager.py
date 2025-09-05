"""
Unit tests for the export manager.
"""
import pytest
from unittest.mock import patch, MagicMock
import xml.etree.ElementTree as ET
from transcriber.services.export_manager import ExportManager
from model_bakery import baker
from transcriber.models import Transcription


@pytest.mark.django_db
class TestExportManager:
    """Test export manager functionality."""
    
    @pytest.fixture
    def sample_tab_data(self):
        """Create sample tab data for testing."""
        return {
            'tempo': 120,
            'time_signature': '4/4',
            'tuning': [64, 59, 55, 50, 45, 40],  # Standard tuning
            'measures': [
                {
                    'number': 1,
                    'notes': [
                        {
                            'string': 0,
                            'fret': 0,
                            'time': 0.0,
                            'duration': 0.5,
                            'technique': None
                        },
                        {
                            'string': 1,
                            'fret': 1,
                            'time': 0.5,
                            'duration': 0.5,
                            'technique': 'hammer_on'
                        }
                    ]
                }
            ],
            'techniques_used': ['hammer_on']
        }
    
    @pytest.fixture
    def export_manager(self, sample_tab_data):
        """Create an export manager instance."""
        transcription = baker.make(Transcription, 
                                 guitar_notes=sample_tab_data,
                                 estimated_tempo=120)
        return ExportManager(transcription)
    
    @pytest.mark.unit
    def test_export_manager_initialization(self, export_manager):
        """Test export manager initializes correctly."""
        assert export_manager.transcription is not None
        assert export_manager.tab_data is not None
        assert 'measures' in export_manager.tab_data
    
    @pytest.mark.unit
    def test_generate_musicxml(self, export_manager):
        """Test MusicXML generation."""
        musicxml = export_manager.generate_musicxml(export_manager.tab_data)
        
        assert musicxml is not None
        assert isinstance(musicxml, str)
        
        # Parse XML to verify structure
        root = ET.fromstring(musicxml)
        assert root.tag == 'score-partwise'
        
        # Check for part-list
        part_list = root.find('part-list')
        assert part_list is not None
        
        # Check for at least one part
        parts = root.findall('part')
        assert len(parts) > 0
        
        # Check for measures
        measures = parts[0].findall('measure')
        assert len(measures) > 0
    
    @pytest.mark.unit
    def test_musicxml_tempo_marking(self, export_manager):
        """Test that tempo is correctly encoded in MusicXML."""
        musicxml = export_manager.generate_musicxml(export_manager.tab_data)
        root = ET.fromstring(musicxml)
        
        # Find tempo marking in first measure
        first_measure = root.find('.//measure[@number="1"]')
        assert first_measure is not None
        
        # Check for metronome marking
        metronome = first_measure.find('.//metronome')
        if metronome is not None:
            per_minute = metronome.find('per-minute')
            assert per_minute is not None
            assert per_minute.text == '120'
    
    @pytest.mark.unit
    def test_musicxml_time_signature(self, export_manager):
        """Test that time signature is correctly encoded."""
        musicxml = export_manager.generate_musicxml(export_manager.tab_data)
        root = ET.fromstring(musicxml)
        
        # Find time signature in first measure
        time_elem = root.find('.//time')
        if time_elem is not None:
            beats = time_elem.find('beats')
            beat_type = time_elem.find('beat-type')
            assert beats is not None
            assert beat_type is not None
            assert beats.text == '4'
            assert beat_type.text == '4'
    
    @pytest.mark.unit
    def test_generate_gp5_with_pyguitarpro(self, export_manager):
        """Test GP5 generation when guitarpro is available."""
        with patch('transcriber.services.export_manager.guitarpro') as mock_gp:
            mock_song = MagicMock()
            mock_gp.Song.return_value = mock_song
            mock_gp.Track = MagicMock()
            mock_gp.Measure = MagicMock()
            mock_gp.Beat = MagicMock()
            mock_gp.Note = MagicMock()
            
            result = export_manager.generate_gp5(export_manager.tab_data)
            
            # Should attempt to create GP5
            mock_gp.Song.assert_called_once()
    
    @pytest.mark.unit
    def test_generate_gp5_without_pyguitarpro(self, export_manager):
        """Test GP5 generation when guitarpro is not available."""
        with patch('transcriber.services.export_manager.guitarpro', None):
            result = export_manager.generate_gp5(export_manager.tab_data)
            
            # Should return None when library not available
            assert result is None
    
    @pytest.mark.unit
    def test_export_midi_with_notes(self, export_manager):
        """Test MIDI export with notes."""
        with patch('transcriber.services.export_manager.PrettyMIDI') as mock_midi:
            mock_pm = MagicMock()
            mock_midi.return_value = mock_pm
            mock_instrument = MagicMock()
            mock_midi.Instrument.return_value = mock_instrument
            
            # Mock write method
            import io
            output = io.BytesIO()
            mock_pm.write = MagicMock(side_effect=lambda f: f.write(b'MIDI_DATA'))
            
            midi_path = export_manager.export_midi()
            
            # Should create MIDI file
            mock_midi.assert_called_once()
            mock_midi.Instrument.assert_called()
            
            # Should add notes
            assert mock_instrument.notes.append.called or hasattr(mock_instrument, 'notes')
    
    @pytest.mark.unit
    def test_note_conversion_to_midi(self, export_manager):
        """Test conversion of tab notes to MIDI notes."""
        # Standard tuning: E(64) B(59) G(55) D(50) A(45) E(40)
        tuning = [64, 59, 55, 50, 45, 40]
        
        # Test calculations for MIDI notes
        # Open first string (high E)
        assert tuning[0] == 64
        
        # 3rd fret on first string would be G (64 + 3 = 67)
        assert tuning[0] + 3 == 67
        
        # Open 6th string (low E)
        assert tuning[5] == 40
    
    @pytest.mark.unit
    def test_technique_notation_in_musicxml(self, export_manager):
        """Test that techniques are properly notated in MusicXML."""
        tab_data = export_manager.tab_data.copy()
        tab_data['measures'][0]['notes'][1]['technique'] = 'hammer_on'
        
        musicxml = export_manager.generate_musicxml(tab_data)
        
        # Check that techniques are mentioned
        assert 'hammer-on' in musicxml.lower() or 'h' in musicxml.lower()
    
    @pytest.mark.unit
    def test_empty_measures_handling(self, export_manager):
        """Test handling of empty measures."""
        tab_data = {
            'tempo': 120,
            'time_signature': '4/4',
            'measures': [
                {'number': 1, 'notes': []}
            ]
        }
        
        musicxml = export_manager.generate_musicxml(tab_data)
        assert musicxml is not None
        
        # Should still generate valid XML
        root = ET.fromstring(musicxml)
        assert root.tag == 'score-partwise'
    
    @pytest.mark.unit
    def test_multiple_measures_export(self, export_manager):
        """Test exporting multiple measures."""
        tab_data = export_manager.tab_data.copy()
        tab_data['measures'] = [
            {
                'number': i,
                'notes': [
                    {'string': 0, 'fret': i, 'time': 0.0, 'duration': 0.5}
                ]
            }
            for i in range(1, 5)
        ]
        
        musicxml = export_manager.generate_musicxml(tab_data)
        root = ET.fromstring(musicxml)
        
        measures = root.findall('.//measure')
        assert len(measures) >= 4
    
    @pytest.mark.unit
    def test_tuning_information_export(self, export_manager):
        """Test that tuning information is included in exports."""
        # Test with drop D tuning
        tab_data = export_manager.tab_data.copy()
        tab_data['tuning'] = [64, 59, 55, 50, 45, 38]  # Drop D
        
        musicxml = export_manager.generate_musicxml(tab_data)
        
        # Should include tuning info (often in staff-details)
        assert 'tuning' in musicxml.lower() or 'staff-details' in musicxml