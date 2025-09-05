"""
Guitar tab generation with dynamic programming optimization for playability.
"""
import numpy as np
from typing import Dict, List, Tuple, Optional
import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class Technique(Enum):
    """Guitar playing techniques."""
    NORMAL = "normal"
    HAMMER_ON = "hammer_on"
    PULL_OFF = "pull_off"
    SLIDE_UP = "slide_up"
    SLIDE_DOWN = "slide_down"
    BEND = "bend"
    RELEASE = "release"
    VIBRATO = "vibrato"
    PALM_MUTE = "palm_mute"
    HARMONIC = "harmonic"
    TAP = "tap"


@dataclass
class GuitarNote:
    """Represents a note on the guitar."""
    time: float
    duration: float
    string: int  # 0-5 (0 = high E)
    fret: int
    midi_note: int
    technique: Technique = Technique.NORMAL
    velocity: int = 80
    
    def __repr__(self):
        return f"Note(s{self.string}f{self.fret} @ {self.time:.2f}s)"


class TabGenerator:
    """
    Generates optimized guitar tabs using dynamic programming.
    Considers playability, hand position, and technique detection.
    """
    
    # Standard tuning MIDI notes [E, A, D, G, B, E]
    STANDARD_TUNING = [40, 45, 50, 55, 59, 64]
    
    # Alternative tunings
    TUNINGS = {
        'standard': [40, 45, 50, 55, 59, 64],
        'drop_d': [38, 45, 50, 55, 59, 64],
        'half_step_down': [39, 44, 49, 54, 58, 63],
        'open_g': [38, 43, 50, 55, 59, 62],
        'dadgad': [38, 45, 50, 55, 57, 62],
    }
    
    def __init__(self, notes: List[Dict], tempo: float, time_signature: str = "4/4", 
                 tuning: str = 'standard'):
        self.notes = sorted(notes, key=lambda x: x['start_time'])
        self.tempo = tempo
        self.time_signature = time_signature
        self.tuning = self.TUNINGS.get(tuning, self.STANDARD_TUNING)
        
        # Playability parameters
        self.max_fret_stretch = 5  # Maximum frets hand can span
        self.preferred_position = 5  # Preferred fret position (5th position)
        self.string_change_cost = 1.0
        self.position_change_cost = 2.0
        self.open_string_bonus = -0.5
        
    def generate_optimized_tabs(self) -> Dict:
        """
        Generate optimized guitar tabs using dynamic programming.
        """
        if not self.notes:
            return self._empty_tab_data()
        
        # Convert notes to possible positions
        note_positions = self._generate_note_positions()
        
        # Optimize string/fret assignment using DP
        optimized_notes = self._optimize_fingering(note_positions)
        
        # Detect and apply techniques
        optimized_notes = self._detect_techniques(optimized_notes)
        
        # Group into measures
        measures = self._group_into_measures(optimized_notes)
        
        # Generate tab data structure
        tab_data = {
            'tempo': self.tempo,
            'time_signature': self.time_signature,
            'tuning': self.tuning,
            'measures': measures,
            'techniques_used': self._get_techniques_summary(optimized_notes)
        }
        
        return tab_data
    
    def _generate_note_positions(self) -> List[List[Tuple[int, int, float]]]:
        """
        Generate all possible string/fret combinations for each note.
        Returns list of lists where each inner list contains (string, fret, cost) tuples.
        """
        positions = []
        
        for note in self.notes:
            midi_note = note['midi_note']
            note_positions = []
            
            # Find all possible positions for this note
            for string_idx in range(6):
                fret = midi_note - self.tuning[string_idx]
                
                if 0 <= fret <= 24:  # Valid fret range
                    # Calculate position cost
                    cost = self._calculate_position_cost(string_idx, fret)
                    note_positions.append((string_idx, fret, cost))
            
            # Sort by cost (lower is better)
            note_positions.sort(key=lambda x: x[2])
            positions.append(note_positions)
        
        return positions
    
    def _calculate_position_cost(self, string: int, fret: int) -> float:
        """
        Calculate the cost of playing a note at a given position.
        """
        cost = 0.0
        
        # Prefer middle strings
        string_preference = [1.0, 0.5, 0.0, 0.0, 0.5, 1.0]
        cost += string_preference[string]
        
        # Prefer positions around 5th fret
        position_cost = abs(fret - self.preferred_position) * 0.3
        cost += position_cost
        
        # Bonus for open strings
        if fret == 0:
            cost += self.open_string_bonus
        
        # Penalty for very high frets
        if fret > 15:
            cost += (fret - 15) * 0.5
        
        return cost
    
    def _optimize_fingering(self, note_positions: List[List[Tuple[int, int, float]]]) -> List[GuitarNote]:
        """
        Use dynamic programming to find optimal string/fret assignments.
        Minimizes hand movement and maximizes playability.
        """
        n = len(self.notes)
        if n == 0:
            return []
        
        # DP table: dp[i][j] = (min_cost, prev_position_idx)
        # i = note index, j = position option index
        dp = {}
        
        # Initialize first note
        for j, (string, fret, cost) in enumerate(note_positions[0]):
            dp[(0, j)] = (cost, -1)
        
        # Fill DP table
        for i in range(1, n):
            for j, (string, fret, cost) in enumerate(note_positions[i]):
                min_cost = float('inf')
                best_prev = -1
                
                # Try all previous positions
                for k, (prev_string, prev_fret, _) in enumerate(note_positions[i-1]):
                    if (i-1, k) not in dp:
                        continue
                    
                    prev_cost = dp[(i-1, k)][0]
                    
                    # Calculate transition cost
                    transition_cost = self._calculate_transition_cost(
                        prev_string, prev_fret, string, fret,
                        self.notes[i-1], self.notes[i]
                    )
                    
                    total_cost = prev_cost + cost + transition_cost
                    
                    if total_cost < min_cost:
                        min_cost = total_cost
                        best_prev = k
                
                dp[(i, j)] = (min_cost, best_prev)
        
        # Backtrack to find optimal path
        guitar_notes = []
        
        # Find best ending position
        min_final_cost = float('inf')
        best_final_pos = -1
        for j in range(len(note_positions[-1])):
            if (n-1, j) in dp and dp[(n-1, j)][0] < min_final_cost:
                min_final_cost = dp[(n-1, j)][0]
                best_final_pos = j
        
        # Backtrack
        path = []
        curr_pos = best_final_pos
        for i in range(n-1, -1, -1):
            if curr_pos >= 0 and i < len(note_positions) and curr_pos < len(note_positions[i]):
                string, fret, _ = note_positions[i][curr_pos]
                path.append((i, string, fret))
                if i > 0:
                    curr_pos = dp[(i, curr_pos)][1]
        
        path.reverse()
        
        # Create GuitarNote objects
        for i, string, fret in path:
            note = self.notes[i]
            guitar_note = GuitarNote(
                time=note['start_time'],
                duration=note['end_time'] - note['start_time'],
                string=string,
                fret=fret,
                midi_note=note['midi_note'],
                velocity=note.get('velocity', 80)
            )
            guitar_notes.append(guitar_note)
        
        return guitar_notes
    
    def _calculate_transition_cost(self, prev_string: int, prev_fret: int,
                                  curr_string: int, curr_fret: int,
                                  prev_note: Dict, curr_note: Dict) -> float:
        """
        Calculate cost of transitioning between two positions.
        """
        cost = 0.0
        
        # Time between notes
        time_diff = curr_note['start_time'] - prev_note['end_time']
        
        # String change cost
        if prev_string != curr_string:
            cost += self.string_change_cost * abs(prev_string - curr_string)
        
        # Position change cost
        if prev_fret > 0 and curr_fret > 0:  # Not open strings
            fret_distance = abs(curr_fret - prev_fret)
            if fret_distance > self.max_fret_stretch:
                # Need to move hand position
                cost += self.position_change_cost * (fret_distance / self.max_fret_stretch)
        
        # Reduce cost for longer time gaps (more time to move)
        if time_diff > 0.5:
            cost *= 0.5
        elif time_diff > 0.25:
            cost *= 0.75
        
        return cost
    
    def _detect_techniques(self, notes: List[GuitarNote]) -> List[GuitarNote]:
        """
        Detect and apply guitar playing techniques based on note patterns.
        """
        if len(notes) < 2:
            return notes
        
        for i in range(len(notes) - 1):
            curr = notes[i]
            next_note = notes[i + 1]
            
            # Same string techniques
            if curr.string == next_note.string:
                fret_diff = next_note.fret - curr.fret
                time_diff = next_note.time - curr.time
                
                # Hammer-on / Pull-off
                if 0 < time_diff < 0.1:  # Very quick transition
                    if fret_diff > 0 and fret_diff <= 4:
                        next_note.technique = Technique.HAMMER_ON
                    elif fret_diff < 0 and fret_diff >= -4:
                        next_note.technique = Technique.PULL_OFF
                
                # Slide
                elif 0.1 <= time_diff < 0.3:
                    if fret_diff > 0:
                        next_note.technique = Technique.SLIDE_UP
                    elif fret_diff < 0:
                        next_note.technique = Technique.SLIDE_DOWN
            
            # Detect vibrato (oscillating pitch on same note)
            if i > 0:
                prev = notes[i - 1]
                if (curr.string == prev.string and 
                    abs(curr.fret - prev.fret) <= 1 and
                    curr.time - prev.time < 0.1):
                    curr.technique = Technique.VIBRATO
        
        # Detect bends (pitch variations)
        for i, note in enumerate(notes):
            # Check for micro-pitch variations in original data
            original = self.notes[i]
            if 'pitch_variation' in original and abs(original['pitch_variation']) > 0.1:
                note.technique = Technique.BEND
        
        return notes
    
    def _group_into_measures(self, notes: List[GuitarNote]) -> List[Dict]:
        """
        Group notes into measures based on tempo and time signature.
        """
        if not notes:
            return []
        
        # Parse time signature
        beats_per_measure = int(self.time_signature.split('/')[0])
        beat_duration = 60.0 / self.tempo  # Duration of one beat in seconds
        measure_duration = beat_duration * beats_per_measure
        
        measures = []
        current_measure = {
            'number': 1,
            'start_time': 0,
            'notes': []
        }
        
        for note in notes:
            # Check if note belongs to current measure
            measure_num = int(note.time / measure_duration) + 1
            
            if measure_num > current_measure['number']:
                # Start new measure
                if current_measure['notes']:
                    measures.append(current_measure)
                
                current_measure = {
                    'number': measure_num,
                    'start_time': (measure_num - 1) * measure_duration,
                    'notes': []
                }
            
            # Add note to measure
            note_dict = {
                'string': note.string,
                'fret': note.fret,
                'time': note.time - current_measure['start_time'],
                'duration': note.duration,
                'technique': note.technique.value,
                'velocity': note.velocity
            }
            current_measure['notes'].append(note_dict)
        
        # Add last measure
        if current_measure['notes']:
            measures.append(current_measure)
        
        return measures
    
    def _get_techniques_summary(self, notes: List[GuitarNote]) -> Dict[str, int]:
        """
        Get summary of techniques used in the tab.
        """
        techniques = {}
        for note in notes:
            if note.technique != Technique.NORMAL:
                tech_name = note.technique.value
                techniques[tech_name] = techniques.get(tech_name, 0) + 1
        return techniques
    
    def _empty_tab_data(self) -> Dict:
        """Return empty tab data structure."""
        return {
            'tempo': self.tempo,
            'time_signature': self.time_signature,
            'tuning': self.tuning,
            'measures': [],
            'techniques_used': {}
        }
    
    def to_ascii_tab(self, measures_per_line: int = 4) -> str:
        """
        Generate ASCII tab representation.
        """
        tab_data = self.generate_optimized_tabs()
        
        if not tab_data['measures']:
            return "No notes detected"
        
        string_names = ['e', 'B', 'G', 'D', 'A', 'E']
        output_lines = []
        
        # Process measures in groups
        for line_start in range(0, len(tab_data['measures']), measures_per_line):
            line_measures = tab_data['measures'][line_start:line_start + measures_per_line]
            
            # Initialize tab lines for this row
            tab_lines = {name: [] for name in string_names}
            
            for measure in line_measures:
                # Create measure tabs
                measure_width = 16
                measure_tabs = {name: '-' * measure_width for name in string_names}
                
                # Place notes
                for note in measure['notes']:
                    string_name = string_names[note['string']]
                    position = int(note['time'] * 4)  # Quantize to 16th notes
                    if position < measure_width:
                        fret_str = str(note['fret'])
                        
                        # Add technique markers
                        if note['technique'] == 'hammer_on':
                            fret_str = f"h{fret_str}"
                        elif note['technique'] == 'pull_off':
                            fret_str = f"p{fret_str}"
                        elif note['technique'] == 'slide_up':
                            fret_str = f"/{fret_str}"
                        elif note['technique'] == 'slide_down':
                            fret_str = f"\\{fret_str}"
                        elif note['technique'] == 'bend':
                            fret_str = f"b{fret_str}"
                        
                        # Place on tab
                        measure_tabs[string_name] = (
                            measure_tabs[string_name][:position] +
                            fret_str +
                            measure_tabs[string_name][position + len(fret_str):]
                        )[:measure_width]
                
                # Add to line
                for name in string_names:
                    tab_lines[name].append(measure_tabs[name])
            
            # Format and add line to output
            for name in string_names:
                line = f"{name}|" + "|".join(tab_lines[name]) + "|"
                output_lines.append(line)
            
            output_lines.append("")  # Empty line between tab rows
        
        return "\n".join(output_lines)