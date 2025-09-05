"""
Unit tests for the fingering optimizer
"""

import pytest
from unittest.mock import Mock, patch
from transcriber.services.fingering_optimizer import (
    FingeringOptimizer, OptimizationWeights, FINGERING_PRESETS,
    Note, FretChoice, STANDARD_TUNING
)


class TestFingeringOptimizer:
    """Test the FingeringOptimizer class"""
    
    def test_optimizer_initialization(self):
        """Test optimizer initializes with correct defaults"""
        optimizer = FingeringOptimizer()
        assert optimizer.tuning == STANDARD_TUNING
        assert optimizer.num_strings == 6
        assert optimizer.max_fret == 24
        assert optimizer.weights == FINGERING_PRESETS["balanced"]
        
    def test_custom_tuning_initialization(self):
        """Test optimizer with custom tuning"""
        drop_d_tuning = [38, 45, 50, 55, 59, 64]  # Drop D
        optimizer = FingeringOptimizer(tuning=drop_d_tuning)
        assert optimizer.tuning == drop_d_tuning
        
    def test_get_possible_positions_middle_c(self):
        """Test finding positions for middle C (MIDI 60)"""
        optimizer = FingeringOptimizer()
        positions = optimizer.get_possible_positions(60)
        
        # Middle C can be played on multiple strings
        expected_positions = [
            (1, 20),  # String 1 (high E), fret 20
            (2, 15),  # String 2 (B), fret 15
            (3, 10),  # String 3 (G), fret 10
            (4, 5),   # String 4 (D), fret 5
            (5, 0),   # String 5 (A), fret 0 would be 45, so this should be fret 15 for C
        ]
        
        # Check we have the right number of positions
        assert len(positions) >= 3
        
        # Check positions are within valid range
        for pos in positions:
            assert 1 <= pos.string <= 6
            assert 0 <= pos.fret <= 24
            assert pos.midi_note == 60
            
    def test_get_possible_positions_open_string(self):
        """Test finding positions for open string notes"""
        optimizer = FingeringOptimizer()
        
        # Test E2 (MIDI 40) - lowest open string
        positions = optimizer.get_possible_positions(40)
        assert any(pos.string == 6 and pos.fret == 0 for pos in positions)
        
        # Test high E (MIDI 64) - highest open string
        positions = optimizer.get_possible_positions(64)
        assert any(pos.string == 1 and pos.fret == 0 for pos in positions)
        
    def test_position_window_calculation(self):
        """Test position window mapping"""
        optimizer = FingeringOptimizer()
        
        assert optimizer.get_position_window(0) == 0   # Open position
        assert optimizer.get_position_window(3) == 1   # First position
        assert optimizer.get_position_window(7) == 2   # Fifth position
        assert optimizer.get_position_window(12) == 3  # Seventh/ninth position
        assert optimizer.get_position_window(20) == 4  # Higher positions
        
    def test_local_cost_open_string(self):
        """Test local cost calculation for open strings"""
        weights = OptimizationWeights(w_open=2.0)
        optimizer = FingeringOptimizer(weights=weights)
        
        open_string = FretChoice(string=1, fret=0, midi_note=64)
        cost = optimizer.local_cost(open_string)
        
        # Open string should have negative cost (bonus)
        assert cost < 0
        
    def test_local_cost_high_fret(self):
        """Test local cost calculation for high frets"""
        weights = OptimizationWeights(w_high=2.0)
        optimizer = FingeringOptimizer(weights=weights)
        
        high_fret = FretChoice(string=1, fret=20, midi_note=84)
        low_fret = FretChoice(string=3, fret=5, midi_note=55)
        
        high_cost = optimizer.local_cost(high_fret)
        low_cost = optimizer.local_cost(low_fret)
        
        # High fret should have higher cost
        assert high_cost > low_cost
        
    def test_transition_cost_same_string(self):
        """Test transition cost for same string movement"""
        weights = OptimizationWeights(w_jump=4.0, w_same=1.0)
        optimizer = FingeringOptimizer(weights=weights)
        
        pos1 = FretChoice(string=3, fret=5, midi_note=55)
        pos2 = FretChoice(string=3, fret=7, midi_note=57)
        
        cost = optimizer.transition_cost(pos1, pos2)
        
        # Should have jump cost minus same string bonus
        expected_jump = 2 * weights.w_jump  # 2 fret jump
        expected_bonus = weights.w_same
        assert cost == pytest.approx(expected_jump - expected_bonus, rel=0.1)
        
    def test_transition_cost_string_change(self):
        """Test transition cost for string changes"""
        weights = OptimizationWeights(w_string=3.0)
        optimizer = FingeringOptimizer(weights=weights)
        
        pos1 = FretChoice(string=3, fret=5, midi_note=55)
        pos2 = FretChoice(string=1, fret=5, midi_note=69)
        
        cost = optimizer.transition_cost(pos1, pos2)
        
        # Should include string change penalty
        assert cost > 0
        assert weights.w_string * 2 <= cost  # At least 2 string distance
        
    def test_chord_cost_within_span(self):
        """Test chord cost for playable chord"""
        weights = OptimizationWeights(w_span=6.0, span_cap=4)
        optimizer = FingeringOptimizer(weights=weights)
        
        # C major chord shape (span of 3 frets)
        chord = [
            FretChoice(string=5, fret=3, midi_note=48),  # C
            FretChoice(string=4, fret=2, midi_note=52),  # E
            FretChoice(string=3, fret=0, midi_note=50),  # G (open)
            FretChoice(string=2, fret=1, midi_note=60),  # C
            FretChoice(string=1, fret=0, midi_note=64),  # E (open)
        ]
        
        cost = optimizer.chord_cost(chord)
        
        # Should be finite (playable)
        assert cost != float('inf')
        assert cost >= 0
        
    def test_chord_cost_exceeds_span(self):
        """Test chord cost for unplayable wide chord"""
        weights = OptimizationWeights(w_span=6.0, span_cap=4)
        optimizer = FingeringOptimizer(weights=weights)
        
        # Impossible chord with 7 fret span
        chord = [
            FretChoice(string=6, fret=1, midi_note=41),
            FretChoice(string=5, fret=8, midi_note=53),  # 7 fret span!
            FretChoice(string=4, fret=5, midi_note=55),
        ]
        
        cost = optimizer.chord_cost(chord)
        
        # Should be infinite (unplayable)
        assert cost == float('inf')
        
    def test_optimize_sequence_simple_scale(self):
        """Test optimization of a simple scale passage"""
        optimizer = FingeringOptimizer(weights=FINGERING_PRESETS["easy"])
        
        # C major scale starting from middle C
        notes = [
            Note(midi_note=60, time=0.0, duration=0.5),    # C
            Note(midi_note=62, time=0.5, duration=0.5),    # D
            Note(midi_note=64, time=1.0, duration=0.5),    # E
            Note(midi_note=65, time=1.5, duration=0.5),    # F
            Note(midi_note=67, time=2.0, duration=0.5),    # G
        ]
        
        result = optimizer.optimize_sequence(notes)
        
        # Should return positions for all notes
        assert len(result) == len(notes)
        
        # Should prefer same string for scale runs (minimize string changes)
        strings_used = [pos.string for pos in result if pos]
        string_changes = sum(1 for i in range(1, len(strings_used)) 
                           if strings_used[i] != strings_used[i-1])
        assert string_changes <= 2  # Should minimize string changes
        
    def test_optimize_sequence_with_chord(self):
        """Test optimization with chords (simultaneous notes)"""
        optimizer = FingeringOptimizer(weights=FINGERING_PRESETS["balanced"])
        
        # C major chord (all notes at same time)
        notes = [
            Note(midi_note=48, time=0.0, duration=1.0),    # C
            Note(midi_note=52, time=0.0, duration=1.0),    # E
            Note(midi_note=55, time=0.0, duration=1.0),    # G
        ]
        
        result = optimizer.optimize_sequence(notes)
        
        # Should return positions for all notes
        assert len(result) == len(notes)
        
        # All positions should be valid
        assert all(pos is not None for pos in result)
        
        # Should use different strings for chord
        strings_used = [pos.string for pos in result]
        assert len(set(strings_used)) == len(strings_used)  # All different
        
    def test_optimize_empty_sequence(self):
        """Test optimization with empty note sequence"""
        optimizer = FingeringOptimizer()
        result = optimizer.optimize_sequence([])
        assert result == []
        
    def test_preset_weights_easy(self):
        """Test EASY preset favors lower positions and smaller spans"""
        easy_weights = FINGERING_PRESETS["easy"]
        
        assert easy_weights.span_cap == 4  # Smaller span limit
        assert easy_weights.w_jump > 4     # Higher jump penalty
        assert easy_weights.pref_fret_center < 10  # Prefer lower frets
        
    def test_preset_weights_technical(self):
        """Test TECHNICAL preset allows wider spans and higher positions"""
        tech_weights = FINGERING_PRESETS["technical"]
        
        assert tech_weights.span_cap >= 6  # Larger span allowed
        assert tech_weights.w_jump < 3     # Lower jump penalty
        assert tech_weights.pref_fret_center > 10  # Can use higher positions
        
    def test_group_into_chords(self):
        """Test chord grouping by onset time"""
        optimizer = FingeringOptimizer()
        
        notes = [
            Note(midi_note=60, time=0.0, duration=1.0),
            Note(midi_note=64, time=0.0, duration=1.0),    # Same time - chord
            Note(midi_note=67, time=0.005, duration=1.0),  # Very close - still chord
            Note(midi_note=62, time=1.0, duration=0.5),    # Different time
        ]
        
        groups = optimizer._group_into_chords(notes)
        
        assert len(groups) == 2  # Two groups
        assert len(groups[0]) == 3  # First three notes form a chord
        assert len(groups[1]) == 1  # Last note is separate