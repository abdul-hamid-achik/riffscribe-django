"""
Playability-aware humanizer service using dynamic programming
Accounts for physical guitar ergonomics, finger positioning, and natural chord shapes
"""

import math
from typing import Dict, List, Tuple, Optional, Any, Set
from dataclasses import dataclass
import numpy as np


# Standard guitar tuning (MIDI notes for open strings E2-A2-D3-G3-B3-E4)
STANDARD_TUNING = [40, 45, 50, 55, 59, 64]

# Common tunings (string 6 to string 1: low to high)
TUNINGS = {
    "standard": [40, 45, 50, 55, 59, 64],      # E-A-D-G-B-E
    "half_step_down": [39, 44, 49, 54, 58, 63], # Eb-Ab-Db-Gb-Bb-Eb  
    "whole_step_down": [38, 43, 48, 53, 57, 62], # D-G-C-F-A-D
    "drop_d": [38, 45, 50, 55, 59, 64],        # D-A-D-G-B-E
    "drop_c": [36, 43, 48, 53, 57, 62],        # C-G-C-F-A-D
    "open_g": [38, 43, 50, 55, 59, 62],        # D-G-D-G-B-D
    "open_d": [38, 45, 50, 54, 57, 62],        # D-A-D-F#-A-D
}

# Physical fret spacing model (relative distances, fret 1 = 1.0)
# Based on 12th root of 2 exponential spacing
FRET_SPACING = {i: 1.0 / (2 ** ((i-1) / 12)) if i > 0 else 0 for i in range(25)}

# Finger stretch capabilities (in fret units, accounting for fret spacing)
FINGER_STRETCHES = {
    # (finger1, finger2): max_comfortable_span_in_fret_units
    (1, 2): 2.5,  # Index to middle
    (1, 3): 4.0,  # Index to ring  
    (1, 4): 5.5,  # Index to pinky
    (2, 3): 2.0,  # Middle to ring
    (2, 4): 3.5,  # Middle to pinky
    (3, 4): 2.5,  # Ring to pinky
}

# CAGED chord shape templates (string, fret_offset_from_root)
# Each shape is defined relative to its root position
CAGED_SHAPES = {
    "C": {
        # C shape pattern (relative to root fret)
        "pattern": [
            (6, 3), (5, 3), (4, 2), (3, 0), (2, 1), (1, 0)  # C major at 3rd fret
        ],
        "core_notes": [(4, 2), (3, 0), (2, 1)],  # Essential fingering
        "fingers": {3: 1, 2: 2, 1: 3}  # fret_offset: finger
    },
    "A": {
        # A shape barre chord (movable)
        "pattern": [
            (6, 0), (5, 2), (4, 2), (3, 2), (2, 0), (1, 0)
        ],
        "core_notes": [(5, 2), (4, 2), (3, 2)],
        "fingers": {0: 1, 2: 3}  # Barre + ring finger
    },
    "G": {
        # G shape (complex, movable version)
        "pattern": [
            (6, 3), (5, 2), (4, 0), (3, 0), (2, 3), (1, 3)
        ],
        "core_notes": [(6, 3), (5, 2), (2, 3), (1, 3)],
        "fingers": {2: 2, 3: 3}
    },
    "E": {
        # E shape barre chord  
        "pattern": [
            (6, 0), (5, 2), (4, 2), (3, 1), (2, 0), (1, 0)
        ],
        "core_notes": [(5, 2), (4, 2), (3, 1)],
        "fingers": {0: 1, 1: 2, 2: 3}
    },
    "D": {
        # D shape (triangular)
        "pattern": [
            (4, 0), (3, 2), (2, 3), (1, 2)
        ],
        "core_notes": [(4, 0), (3, 2), (2, 3), (1, 2)],
        "fingers": {0: 0, 2: 1, 3: 3, 2: 2}  # Open, index, ring, middle
    }
}


@dataclass
class Note:
    """Represents a single note to be placed on the fretboard"""
    midi_note: int
    time: float
    duration: float
    velocity: int = 80
    
    
@dataclass(frozen=True)
class FretChoice:
    """A possible fret/string combination for a note"""
    string: int  # 1-6 (1=highest pitch string, 6=lowest)
    fret: int    # 0-24
    midi_note: int
    finger: Optional[int] = None  # 1-4 (index, middle, ring, pinky) or None for open


@dataclass
class Position:
    """Represents a hand position on the guitar neck"""
    base_fret: int  # Fret where index finger is positioned
    choices: List[FretChoice]  # All notes in this position
    
    def get_span(self) -> float:
        """Get the physical span of this position in fret units"""
        if not self.choices or all(c.fret == 0 for c in self.choices):
            return 0.0
        
        non_open = [c for c in self.choices if c.fret > 0]
        if not non_open:
            return 0.0
            
        frets = [c.fret for c in non_open]
        min_fret, max_fret = min(frets), max(frets)
        
        # Calculate physical span accounting for fret spacing
        span = 0.0
        for f in range(min_fret, max_fret):
            span += FRET_SPACING[f]
        return span
    

@dataclass 
class OptimizationWeights:
    """Weight parameters for the ergonomic cost function"""
    # Physical costs
    w_stretch: float = 10.0       # Penalty for finger stretches beyond comfort
    w_position: float = 2.0       # Penalty for difficult positions (low frets)
    w_string_jump: float = 8.0    # Heavy penalty for jumping across strings
    w_open_bonus: float = 2.0     # Bonus for open strings
    
    # Transition costs  
    w_pos_shift: float = 5.0      # Penalty for moving hand position
    w_finger_conflict: float = 20.0  # Penalty for impossible finger assignments
    w_same_string: float = 1.0    # Bonus for staying on same string for melody
    
    # Musical costs
    w_voice_leading: float = 3.0  # Penalty for poor voice leading
    w_chord_shape: float = -3.0   # Bonus for recognizable chord shapes
    
    # Hard constraints
    max_physical_span: float = 6.0    # Max span in fret units
    max_string_jump: int = 3          # Max strings to jump at once
    

# Preset configurations for different playing styles
HUMANIZER_PRESETS = {
    "easy": OptimizationWeights(
        w_stretch=15.0, w_string_jump=12.0, w_pos_shift=8.0,
        w_open_bonus=3.0, w_finger_conflict=25.0,
        max_physical_span=4.0, max_string_jump=2
    ),
    "balanced": OptimizationWeights(
        w_stretch=10.0, w_string_jump=8.0, w_pos_shift=5.0,
        w_open_bonus=2.0, w_finger_conflict=20.0,
        max_physical_span=6.0, max_string_jump=3
    ),
    "technical": OptimizationWeights(
        w_stretch=5.0, w_string_jump=4.0, w_pos_shift=3.0,
        w_open_bonus=1.0, w_finger_conflict=15.0,
        max_physical_span=8.0, max_string_jump=4
    ),
    "original": OptimizationWeights()  # Use default values
}


class HumanizerService:
    """Ergonomically-aware guitar fingering optimizer using dynamic programming"""
    
    def __init__(self, tuning=None, weights: OptimizationWeights = None):
        # Handle tuning as string name or list of MIDI notes
        if isinstance(tuning, str):
            self.tuning = TUNINGS.get(tuning, STANDARD_TUNING)
        else:
            self.tuning = tuning or STANDARD_TUNING
            
        self.weights = weights or HUMANIZER_PRESETS["balanced"]
        self.num_strings = len(self.tuning)
        self.max_fret = 24
        
    def get_possible_positions(self, midi_note: int) -> List[FretChoice]:
        """Find all possible string/fret combinations for a given MIDI note"""
        positions = []
        
        for string_idx, open_note in enumerate(self.tuning):
            fret = midi_note - open_note
            if 0 <= fret <= self.max_fret:
                positions.append(FretChoice(
                    string=string_idx + 1,  # 1-indexed
                    fret=fret,
                    midi_note=midi_note
                ))
                
        return positions
        
    def assign_fingers_to_position(self, choices: List[FretChoice]) -> List[FretChoice]:
        """Assign finger numbers to choices in a position, returns new choices with fingers"""
        if not choices:
            return []
            
        # Filter out open strings for finger assignment
        non_open = [c for c in choices if c.fret > 0]
        open_strings = [c for c in choices if c.fret == 0]
        
        if not non_open:
            return choices  # All open strings
            
        # Sort by fret number for logical finger assignment
        non_open.sort(key=lambda x: x.fret)
        
        # Find base fret (where index finger would be)
        min_fret = min(c.fret for c in non_open)
        
        # Assign fingers based on fret distance from base
        result = []
        for choice in non_open:
            fret_offset = choice.fret - min_fret
            
            # Simple finger assignment: 1 fret = 1 finger typically
            if fret_offset == 0:
                finger = 1  # Index finger
            elif fret_offset == 1:
                finger = 2  # Middle finger  
            elif fret_offset == 2:
                finger = 3  # Ring finger
            elif fret_offset == 3:
                finger = 4  # Pinky finger
            else:
                # For larger spans, use pinky or reject
                finger = 4 if fret_offset <= 5 else None
                
            if finger:
                result.append(FretChoice(
                    string=choice.string,
                    fret=choice.fret,
                    midi_note=choice.midi_note,
                    finger=finger
                ))
                
        # Add back open strings (no finger assigned)
        result.extend(open_strings)
        return result
    
    def validate_finger_stretch(self, choices: List[FretChoice]) -> bool:
        """Check if finger assignments are physically possible"""
        if not choices:
            return True
            
        # Get fingered notes only
        fingered = [c for c in choices if c.finger is not None]
        if len(fingered) <= 1:
            return True
            
        # Check all finger pair stretches
        for i, choice1 in enumerate(fingered):
            for choice2 in fingered[i+1:]:
                if choice1.finger == choice2.finger:
                    return False  # Same finger on different frets
                    
                # Calculate physical distance
                fret_span = abs(choice2.fret - choice1.fret)
                physical_span = sum(FRET_SPACING[min(choice1.fret, choice2.fret) + j] 
                                  for j in range(fret_span))
                
                # Check if stretch is within finger capability
                finger_pair = tuple(sorted([choice1.finger, choice2.finger]))
                max_stretch = FINGER_STRETCHES.get(finger_pair, 2.0)  # Conservative default
                
                if physical_span > max_stretch:
                    return False
                    
        return True
        
    def local_cost(self, choice: FretChoice) -> float:
        """Calculate the ergonomic cost of a single fret choice"""
        cost = 0.0
        
        # Open string bonus
        if choice.fret == 0:
            cost -= self.weights.w_open_bonus
            return cost
            
        # Position difficulty (lower frets are harder due to wider spacing)
        if choice.fret <= 5:
            cost += self.weights.w_position * (6 - choice.fret) * 0.5
            
        return cost
    
    def transition_cost(self, prev: FretChoice, curr: FretChoice) -> float:
        """Calculate the ergonomic cost of transitioning between positions"""
        cost = 0.0
        
        # String jumping penalty (exponential - jumping strings is very expensive)
        string_jump = abs(curr.string - prev.string)
        if string_jump > self.weights.max_string_jump:
            return float('inf')  # Hard constraint
            
        if string_jump > 0:
            cost += self.weights.w_string_jump * (string_jump ** 1.8)
        else:
            # Bonus for staying on same string (good for melody)
            cost -= self.weights.w_same_string
            
        # Position shift cost (moving hand is expensive)
        if prev.fret > 0 and curr.fret > 0:  # Both are fretted
            prev_pos = self._get_hand_position(prev.fret)
            curr_pos = self._get_hand_position(curr.fret)
            
            if prev_pos != curr_pos:
                pos_shift = abs(curr_pos - prev_pos)
                cost += self.weights.w_pos_shift * pos_shift
                
        # Same-string fret movement (sliding is natural)
        if prev.string == curr.string and prev.fret != curr.fret:
            fret_dist = abs(curr.fret - prev.fret)
            # Small slides are easy, large ones are harder
            if fret_dist <= 2:
                cost += 0.5  # Easy slide
            elif fret_dist <= 5:
                cost += 2.0  # Medium slide
            else:
                cost += 5.0  # Hard jump
                
        # Voice leading penalty for melodic motion
        melodic_interval = abs(prev.midi_note - curr.midi_note)
        if melodic_interval > 0:
            # Penalize large melodic leaps (smoothness preference)
            if melodic_interval <= 2:  # Minor/major 2nd
                cost += 0.0  # Smooth step motion
            elif melodic_interval <= 4:  # Minor/major 3rd
                cost += self.weights.w_voice_leading * 0.5
            elif melodic_interval <= 7:  # 4th, 5th
                cost += self.weights.w_voice_leading * 1.0
            elif melodic_interval <= 12:  # Up to octave
                cost += self.weights.w_voice_leading * 2.0
            else:  # Large leaps
                cost += self.weights.w_voice_leading * 3.0
                
        return cost
        
    def _get_hand_position(self, fret: int) -> int:
        """Get the hand position (base fret for index finger)"""
        if fret <= 0:
            return 0
        elif fret <= 4:
            return 1  # 1st position
        elif fret <= 7:
            return 5  # 5th position
        elif fret <= 11:
            return 8  # 8th position
        else:
            return fret - 3  # Index finger 3 frets back
            
    def recognize_caged_shape(self, choices: List[FretChoice]) -> Tuple[Optional[str], float]:
        """
        Check if choices match a CAGED chord shape pattern
        Returns (shape_name, match_confidence) where confidence is 0.0-1.0
        """
        if len(choices) < 3:  # Need at least 3 notes for a chord
            return None, 0.0
            
        best_match = None
        best_score = 0.0
        
        for shape_name, shape_data in CAGED_SHAPES.items():
            # Try different root positions on the neck
            for root_fret in range(0, 13):  # Common positions
                score = self._match_caged_pattern(choices, shape_data, root_fret)
                if score > best_score:
                    best_score = score
                    best_match = shape_name
                    
        return best_match, best_score
        
    def _match_caged_pattern(self, choices: List[FretChoice], shape_data: dict, root_fret: int) -> float:
        """Calculate how well choices match a CAGED pattern at a given root position"""
        pattern = shape_data["pattern"]
        core_notes = shape_data["core_notes"] 
        
        # Convert pattern to absolute fret positions
        expected_positions = set()
        for string, fret_offset in pattern:
            abs_fret = root_fret + fret_offset
            if 0 <= abs_fret <= 24:  # Valid fret range
                expected_positions.add((string, abs_fret))
                
        # Convert choices to position set
        actual_positions = {(c.string, c.fret) for c in choices}
        
        # Calculate match score
        total_expected = len(expected_positions)
        if total_expected == 0:
            return 0.0
            
        # Count matches, with extra weight for core notes
        matches = 0
        core_matches = 0
        
        for pos in actual_positions:
            if pos in expected_positions:
                matches += 1
                # Check if this is a core note
                string, fret = pos
                relative_fret = fret - root_fret
                if (string, relative_fret) in core_notes:
                    core_matches += 1
                    
        # Score based on percentage match, with bonus for core note matches
        basic_score = matches / total_expected
        core_bonus = core_matches / len(core_notes) if core_notes else 0
        
        return (basic_score * 0.7 + core_bonus * 0.3)
    
    def chord_cost(self, choices: List[FretChoice]) -> float:
        """Calculate ergonomic cost for chord shapes with physical constraints"""
        if len(choices) <= 1:
            return 0.0
            
        cost = 0.0
        
        # Assign fingers and validate physical possibility
        fingered_choices = self.assign_fingers_to_position(choices)
        
        if not self.validate_finger_stretch(fingered_choices):
            return float('inf')  # Impossible finger stretch
            
        # Calculate physical span
        position = Position(
            base_fret=min((c.fret for c in fingered_choices if c.fret > 0), default=0),
            choices=fingered_choices
        )
        
        physical_span = position.get_span()
        
        # Hard constraint: maximum physical span
        if physical_span > self.weights.max_physical_span:
            return float('inf')
            
        # Cost increases exponentially with span (harder stretches)
        if physical_span > 0:
            cost += self.weights.w_stretch * (physical_span ** 1.5)
            
        # Extra penalty for spans in lower positions (wider frets)
        if any(c.fret > 0 and c.fret <= 5 for c in fingered_choices):
            low_fret_factor = 2.0  # Double the penalty in low positions
            cost *= low_fret_factor
            
        # Check for string conflicts (multiple notes on same string)
        strings_used = [c.string for c in choices]
        if len(strings_used) != len(set(strings_used)):
            return float('inf')  # Can't play multiple notes on same string
            
        # CAGED shape recognition bonus
        shape_name, confidence = self.recognize_caged_shape(choices)
        if shape_name and confidence > 0.5:  # Good match threshold
            caged_bonus = self.weights.w_chord_shape * confidence
            cost += caged_bonus  # w_chord_shape is negative for bonus
            
        return cost
    
    def optimize_sequence(self, notes: List[Note]) -> List[FretChoice]:
        """
        Optimize fingering for a sequence of notes using dynamic programming
        """
        if not notes:
            return []
            
        n = len(notes)
        
        # Get possible positions for each note
        all_positions = []
        for note in notes:
            positions = self.get_possible_positions(note.midi_note)
            if not positions:
                # Note out of range, skip
                all_positions.append([])
            else:
                all_positions.append(positions)
                
        # Handle chords (notes with same onset time)
        chord_groups = self._group_into_chords(notes)
        
        # DP arrays
        dp = [{} for _ in range(n)]  # dp[i][position] = min cost
        parent = [{} for _ in range(n)]  # For backtracking
        
        # Initialize first note/chord
        first_group = chord_groups[0]
        if len(first_group) == 1:
            # Single note
            idx = first_group[0]
            for pos in all_positions[idx]:
                dp[idx][pos] = self.local_cost(pos)
                parent[idx][pos] = None
        else:
            # Chord - find best combination
            chord_positions = self._optimize_chord(
                [notes[i] for i in first_group],
                [all_positions[i] for i in first_group]
            )
            if chord_positions:
                for i, pos in zip(first_group, chord_positions):
                    dp[i][pos] = self.local_cost(pos) + self.chord_cost(chord_positions)
                    parent[i][pos] = None
                    
        # Process remaining notes/chords
        prev_indices = first_group
        
        for group in chord_groups[1:]:
            if len(group) == 1:
                # Single note
                idx = group[0]
                for curr_pos in all_positions[idx]:
                    min_cost = float('inf')
                    best_prev = None
                    
                    # Find best previous position
                    for prev_idx in prev_indices:
                        for prev_pos in dp[prev_idx]:
                            cost = (dp[prev_idx][prev_pos] + 
                                  self.local_cost(curr_pos) +
                                  self.transition_cost(prev_pos, curr_pos))
                            
                            if cost < min_cost:
                                min_cost = cost
                                best_prev = (prev_idx, prev_pos)
                                
                    if best_prev:
                        dp[idx][curr_pos] = min_cost
                        parent[idx][curr_pos] = best_prev
                        
            else:
                # Chord
                chord_positions = self._optimize_chord(
                    [notes[i] for i in group],
                    [all_positions[i] for i in group]
                )
                
                if chord_positions:
                    # Calculate transition from previous positions
                    min_cost = float('inf')
                    best_prev = None
                    
                    for prev_idx in prev_indices:
                        for prev_pos in dp[prev_idx]:
                            # Use closest string in chord for transition
                            closest_pos = min(chord_positions, 
                                            key=lambda p: abs(p.string - prev_pos.string))
                            cost = (dp[prev_idx][prev_pos] +
                                  sum(self.local_cost(p) for p in chord_positions) +
                                  self.chord_cost(chord_positions) +
                                  self.transition_cost(prev_pos, closest_pos))
                            
                            if cost < min_cost:
                                min_cost = cost
                                best_prev = (prev_idx, prev_pos)
                                
                    if best_prev:
                        for i, pos in zip(group, chord_positions):
                            dp[i][pos] = min_cost
                            parent[i][pos] = best_prev
                            
            prev_indices = group
            
        # Backtrack to find optimal path
        result = [None] * n
        
        # Find ending position with minimum cost
        last_idx = chord_groups[-1][-1]
        if dp[last_idx]:
            best_pos = min(dp[last_idx].items(), key=lambda x: x[1])[0]
            
            # Backtrack
            curr_idx = last_idx
            curr_pos = best_pos
            
            while curr_idx >= 0:
                result[curr_idx] = curr_pos
                
                if parent[curr_idx][curr_pos]:
                    prev_idx, prev_pos = parent[curr_idx][curr_pos]
                    curr_idx = prev_idx
                    curr_pos = prev_pos
                else:
                    break
                    
        return result
    
    def _group_into_chords(self, notes: List[Note]) -> List[List[int]]:
        """Group notes by onset time to identify chords"""
        groups = []
        current_group = []
        current_time = None
        
        for i, note in enumerate(notes):
            if current_time is None or abs(note.time - current_time) < 0.01:
                current_group.append(i)
                current_time = note.time
            else:
                groups.append(current_group)
                current_group = [i]
                current_time = note.time
                
        if current_group:
            groups.append(current_group)
            
        return groups
    
    def _optimize_chord(self, chord_notes: List[Note], 
                       possible_positions: List[List[FretChoice]]) -> List[FretChoice]:
        """Find optimal string assignment for a chord"""
        if not all(possible_positions):
            return []
            
        # For small chords, try all combinations
        if len(chord_notes) <= 3:
            best_combo = None
            best_cost = float('inf')
            
            def try_combinations(idx, current_combo, used_strings):
                nonlocal best_combo, best_cost
                
                if idx == len(chord_notes):
                    cost = sum(self.local_cost(p) for p in current_combo)
                    cost += self.chord_cost(current_combo)
                    
                    if cost < best_cost:
                        best_cost = cost
                        best_combo = current_combo[:]
                    return
                    
                for pos in possible_positions[idx]:
                    if pos.string not in used_strings:
                        current_combo.append(pos)
                        used_strings.add(pos.string)
                        try_combinations(idx + 1, current_combo, used_strings)
                        current_combo.pop()
                        used_strings.remove(pos.string)
                        
            try_combinations(0, [], set())
            return best_combo or []
            
        else:
            # For larger chords, use greedy assignment
            result = []
            used_strings = set()
            
            # Sort notes by pitch for better voice leading
            sorted_indices = sorted(range(len(chord_notes)), 
                                  key=lambda i: chord_notes[i].midi_note)
            
            for idx in sorted_indices:
                best_pos = None
                best_cost = float('inf')
                
                for pos in possible_positions[idx]:
                    if pos.string not in used_strings:
                        cost = self.local_cost(pos)
                        if cost < best_cost:
                            best_cost = cost
                            best_pos = pos
                            
                if best_pos:
                    result.append(best_pos)
                    used_strings.add(best_pos.string)
                    
            return result


# Example usage and testing
if __name__ == "__main__":
    # Example: Create a simple melodic passage
    notes = [
        Note(midi_note=64, time=0.0, duration=0.5),    # E4
        Note(midi_note=67, time=0.5, duration=0.5),    # G4  
        Note(midi_note=69, time=1.0, duration=0.5),    # A4
        Note(midi_note=72, time=1.5, duration=0.5),    # C5
    ]
    
    # Test with different tunings and difficulty levels
    print("=== ERGONOMIC GUITAR TABLATURE OPTIMIZER ===\n")
    
    for tuning_name in ["standard", "half_step_down", "drop_d"]:
        print(f"--- {tuning_name.upper().replace('_', ' ')} TUNING ---")
        
        for preset in ["easy", "balanced", "technical"]:
            humanizer = HumanizerService(
                tuning=tuning_name,
                weights=HUMANIZER_PRESETS[preset]
            )
            
            result = humanizer.optimize_sequence(notes)
            
            print(f"{preset.capitalize()} difficulty:")
            for i, choice in enumerate(result):
                if choice:
                    note = notes[i]
                    finger_info = f" (finger {choice.finger})" if choice.finger else " (open)"
                    print(f"  Note {i+1}: String {choice.string}, Fret {choice.fret}{finger_info}")
                else:
                    print(f"  Note {i+1}: No valid position found")
            print()
        print()
