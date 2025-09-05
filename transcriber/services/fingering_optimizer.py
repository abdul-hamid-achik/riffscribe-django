"""
Playability-aware fingering optimizer using dynamic programming
"""

import math
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import numpy as np


# Standard guitar tuning (MIDI notes for open strings E2-A2-D3-G3-B3-E4)
STANDARD_TUNING = [40, 45, 50, 55, 59, 64]


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
    string: int  # 1-6 (1=highest pitch string)
    fret: int    # 0-24
    midi_note: int
    

@dataclass 
class OptimizationWeights:
    """Weight parameters for the cost function"""
    # Local costs
    w_fret: float = 1.0           # Penalty for distance from preferred fret region
    w_open: float = 1.0           # Bonus for open strings (negative cost)
    w_high: float = 2.0           # Penalty for high frets (>17)
    pref_fret_center: int = 9     # Preferred fret region center
    
    # Transition costs
    w_jump: float = 4.0           # Penalty for large fret jumps
    w_string: float = 2.0         # Penalty for string changes
    w_pos: float = 2.0            # Penalty for position shifts
    w_span: float = 6.0           # Penalty for chord span
    w_same: float = 0.5           # Bonus for staying on same string
    
    # Constraints
    span_cap: int = 5             # Maximum allowed chord span
    max_jump: int = 12            # Maximum allowed jump
    

# Preset configurations
FINGERING_PRESETS = {
    "easy": OptimizationWeights(
        w_jump=6, w_string=3, w_span=8, span_cap=4,
        w_open=2, w_high=2, pref_fret_center=7,
        w_pos=3, w_same=1
    ),
    "balanced": OptimizationWeights(
        w_jump=4, w_string=2, w_span=6, span_cap=5,
        w_open=1, w_high=1, pref_fret_center=9,
        w_pos=2, w_same=0.5
    ),
    "technical": OptimizationWeights(
        w_jump=2, w_string=1, w_span=3, span_cap=7,
        w_open=0.5, w_high=0, pref_fret_center=12,
        w_pos=1, w_same=0.25
    ),
    "original": OptimizationWeights(
        w_jump=3, w_string=1.5, w_span=5, span_cap=6,
        w_open=1, w_high=0.5, pref_fret_center=10,
        w_pos=1.5, w_same=0.3
    )
}


class FingeringOptimizer:
    """Dynamic programming optimizer for guitar fingering"""
    
    def __init__(self, tuning: List[int] = None, weights: OptimizationWeights = None):
        self.tuning = tuning or STANDARD_TUNING
        self.weights = weights or FINGERING_PRESETS["balanced"]
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
    
    def get_position_window(self, fret: int) -> int:
        """Get the position window (5-fret regions) for a given fret"""
        if fret == 0:
            return 0  # Open position
        elif fret <= 5:
            return 1  # First position
        elif fret <= 9:
            return 2  # Fifth position
        elif fret <= 14:
            return 3  # Seventh/ninth position
        else:
            return 4  # Higher positions
            
    def local_cost(self, choice: FretChoice) -> float:
        """Calculate the local cost of a single fret choice"""
        cost = 0.0
        
        # Distance from preferred fret region
        if choice.fret > 0:  # Not open string
            cost += self.weights.w_fret * abs(choice.fret - self.weights.pref_fret_center)
            
        # Open string bonus
        if choice.fret == 0:
            cost -= self.weights.w_open
            
        # High fret penalty
        if choice.fret > 17:
            cost += self.weights.w_high * (choice.fret - 17)
            
        return cost
    
    def transition_cost(self, prev: FretChoice, curr: FretChoice) -> float:
        """Calculate the cost of transitioning between two positions"""
        cost = 0.0
        
        # Fret jump penalty (quadratic for large jumps)
        if prev.string == curr.string:
            jump = abs(curr.fret - prev.fret)
            if jump > 4:
                cost += self.weights.w_jump * (jump ** 1.5)
            else:
                cost += self.weights.w_jump * jump
                
        # String change penalty
        string_dist = abs(curr.string - prev.string)
        cost += self.weights.w_string * string_dist
        
        # Position shift penalty
        if self.get_position_window(prev.fret) != self.get_position_window(curr.fret):
            cost += self.weights.w_pos
            
        # Same string bonus
        if prev.string == curr.string:
            cost -= self.weights.w_same
            
        return cost
    
    def chord_cost(self, choices: List[FretChoice]) -> float:
        """Calculate additional cost for chord shapes"""
        if len(choices) <= 1:
            return 0.0
            
        cost = 0.0
        
        # Calculate chord span (excluding open strings)
        non_open_frets = [c.fret for c in choices if c.fret > 0]
        if non_open_frets:
            span = max(non_open_frets) - min(non_open_frets)
            
            # Span penalty
            cost += self.weights.w_span * span
            
            # Hard constraint: exceed span cap
            if span > self.weights.span_cap:
                return float('inf')
                
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