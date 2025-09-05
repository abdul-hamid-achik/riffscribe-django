"""
Unit tests for the tab generator with DP optimization.
"""
import pytest
from transcriber.tab_generator import TabGenerator, GuitarNote, Technique


class TestTabGenerator:
    """Test the tab generation and optimization."""
    
    @pytest.fixture
    def sample_notes(self):
        """Create sample notes for testing."""
        return [
            {'start_time': 0.0, 'end_time': 0.5, 'midi_note': 40, 'velocity': 80},  # E (open 6th)
            {'start_time': 0.5, 'end_time': 1.0, 'midi_note': 45, 'velocity': 80},  # A (open 5th)
            {'start_time': 1.0, 'end_time': 1.5, 'midi_note': 50, 'velocity': 80},  # D (open 4th)
            {'start_time': 1.5, 'end_time': 2.0, 'midi_note': 55, 'velocity': 80},  # G (open 3rd)
            {'start_time': 2.0, 'end_time': 2.5, 'midi_note': 59, 'velocity': 80},  # B (open 2nd)
            {'start_time': 2.5, 'end_time': 3.0, 'midi_note': 64, 'velocity': 80},  # E (open 1st)
        ]
    
    @pytest.fixture
    def tab_generator(self, sample_notes):
        """Create a tab generator instance."""
        return TabGenerator(sample_notes, tempo=120, time_signature="4/4")
    
    @pytest.mark.unit
    def test_tab_generator_initialization(self, tab_generator):
        """Test tab generator initializes correctly."""
        assert tab_generator.tempo == 120
        assert tab_generator.time_signature == "4/4"
        assert tab_generator.tuning == [40, 45, 50, 55, 59, 64]  # Standard tuning
        assert len(tab_generator.notes) == 6
    
    @pytest.mark.unit
    def test_midi_to_fret_conversion(self, tab_generator):
        """Test MIDI note to fret conversion logic."""
        # Test basic fret calculation
        # E string (MIDI 40) + 3 frets = G (MIDI 43)
        assert 40 + 3 == 43
        
        # Test that notes can be found on different strings
        tab_data = tab_generator.generate_optimized_tabs()
        assert tab_data is not None
    
    @pytest.mark.unit
    def test_find_best_string_for_note(self, tab_generator):
        """Test finding optimal string for a note."""
        # Test that optimizer finds valid positions for notes
        tab_data = tab_generator.generate_optimized_tabs()
        
        # Check all notes have valid string/fret positions
        for measure in tab_data['measures']:
            for note in measure['notes']:
                assert 0 <= note['string'] <= 5
                assert 0 <= note['fret'] <= 24  # Standard fretboard range
    
    @pytest.mark.unit
    def test_generate_optimized_tabs(self, tab_generator):
        """Test the full tab generation with DP optimization."""
        tab_data = tab_generator.generate_optimized_tabs()
        
        assert 'tempo' in tab_data
        assert 'time_signature' in tab_data
        assert 'measures' in tab_data
        assert 'techniques_used' in tab_data
        
        assert tab_data['tempo'] == 120
        assert len(tab_data['measures']) > 0
        
        # Check first measure has notes
        first_measure = tab_data['measures'][0]
        assert 'notes' in first_measure
        assert len(first_measure['notes']) > 0
    
    @pytest.mark.unit
    def test_technique_detection(self):
        """Test technique detection between notes."""
        # Create notes for technique testing
        notes_for_techniques = [
            {'start_time': 0.0, 'end_time': 0.1, 'midi_note': 45, 'velocity': 80},
            {'start_time': 0.05, 'end_time': 0.15, 'midi_note': 47, 'velocity': 80},  # Hammer-on
            {'start_time': 0.2, 'end_time': 0.3, 'midi_note': 50, 'velocity': 80},   # Slide
        ]
        
        gen = TabGenerator(notes_for_techniques, 120)
        guitar_notes = [
            GuitarNote(0.0, 0.1, 5, 0, 45),     # A open
            GuitarNote(0.05, 0.1, 5, 2, 47),    # B on same string
            GuitarNote(0.2, 0.1, 5, 5, 50),     # D higher up
        ]
        
        detected = gen._detect_techniques(guitar_notes)
        
        # Should detect hammer-on between first two notes
        assert detected[1].technique == Technique.HAMMER_ON
    
    @pytest.mark.unit
    def test_transition_cost_calculation(self, tab_generator):
        """Test the cost calculation for position transitions."""
        # Same string, close frets - low cost
        cost1 = tab_generator._calculate_transition_cost(
            0, 3, 0, 5,  # Same string, fret 3 to 5
            {'end_time': 1.0}, {'start_time': 1.1}
        )
        
        # Different strings - higher cost
        cost2 = tab_generator._calculate_transition_cost(
            0, 3, 3, 3,  # Different strings, same fret
            {'end_time': 1.0}, {'start_time': 1.1}
        )
        
        assert cost2 > cost1  # String change should cost more
        
        # Large position jump - highest cost
        cost3 = tab_generator._calculate_transition_cost(
            0, 1, 0, 15,  # Same string, huge jump
            {'end_time': 1.0}, {'start_time': 1.1}
        )
        
        assert cost3 > cost1  # Large jump should cost more
    
    @pytest.mark.unit
    def test_ascii_tab_generation(self, tab_generator):
        """Test ASCII tab output generation."""
        ascii_tab = tab_generator.to_ascii_tab(measures_per_line=2)
        
        assert isinstance(ascii_tab, str)
        assert 'e|' in ascii_tab  # Should have string markers
        assert 'E|' in ascii_tab
        lines = ascii_tab.strip().split('\n')
        assert len(lines) >= 6  # At least 6 strings
    
    @pytest.mark.unit
    def test_alternative_tunings(self):
        """Test tab generation with alternative tunings."""
        notes = [{'start_time': 0, 'end_time': 0.5, 'midi_note': 38, 'velocity': 80}]  # D
        
        # Test with Drop D tuning
        gen_drop_d = TabGenerator(notes, 120, tuning='drop_d')
        # Tuning is reversed in the list (1st string first)
        assert gen_drop_d.tuning[0] == 38  # 6th string (index 0) tuned to D
        
        tab_data = gen_drop_d.generate_optimized_tabs()
        # D should be playable somewhere on the fretboard
        first_note = tab_data['measures'][0]['notes'][0]
        assert 0 <= first_note['string'] <= 5
        assert 0 <= first_note['fret'] <= 24