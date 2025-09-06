"""
Fingering variant generation with technique inference and metrics
"""

import json
import logging
import math
from typing import Dict, List, Tuple, Optional, Any
from django.db import transaction

logger = logging.getLogger(__name__)

from ..models import (
    Transcription, FingeringVariant, 
    PlayabilityMetrics, FingeringMeasureStat
)
from .humanizer_service import (
    HumanizerService, OptimizationWeights, 
    HUMANIZER_PRESETS, Note, FretChoice, STANDARD_TUNING
)


class TechniqueInference:
    """Infer guitar playing techniques from note sequences"""
    
    @staticmethod
    def infer_techniques(notes: List[Dict], tab_data: List[FretChoice]) -> Dict[str, int]:
        """
        Analyze note sequence and infer techniques
        Returns counts of detected techniques
        """
        techniques = {
            "hammer_on": 0,
            "pull_off": 0,
            "slide": 0,
            "bend": 0,
            "vibrato": 0
        }
        
        if len(notes) < 2:
            return techniques
            
        for i in range(1, len(notes)):
            if not tab_data[i] or not tab_data[i-1]:
                continue
                
            prev_note = notes[i-1]
            curr_note = notes[i]
            prev_pos = tab_data[i-1]
            curr_pos = tab_data[i]
            
            # Same string techniques
            if prev_pos.string == curr_pos.string:
                time_gap = curr_note.get('start_time', 0) - prev_note.get('end_time', 0)
                fret_diff = curr_pos.fret - prev_pos.fret
                
                # Hammer-on/Pull-off: small time gap, small fret distance
                if abs(time_gap) < 0.05 and 0 < abs(fret_diff) <= 2:
                    if fret_diff > 0:
                        techniques["hammer_on"] += 1
                    else:
                        techniques["pull_off"] += 1
                        
                # Slide: larger fret distance with sustain
                elif abs(time_gap) < 0.02 and abs(fret_diff) > 2:
                    techniques["slide"] += 1
                    
        return techniques
    
    @staticmethod
    def remove_techniques(tab_data: Dict, preset_name: str) -> Tuple[Dict, Dict]:
        """
        Remove complex techniques for easier presets
        Returns modified tab_data and removed technique counts
        """
        removed = {}
        
        if preset_name != "easy":
            return tab_data, removed
            
        # For easy preset, simplify or remove complex techniques
        modified_data = json.loads(json.dumps(tab_data))  # Deep copy
        
        for measure in modified_data.get('measures', []):
            for note in measure.get('notes', []):
                # Remove bends
                if note.get('technique') == 'bend':
                    note.pop('technique', None)
                    removed['bends'] = removed.get('bends', 0) + 1
                    
                # Simplify wide slides
                elif note.get('technique') == 'slide' and abs(note.get('slide_length', 0)) > 5:
                    note.pop('technique', None)
                    removed['slides'] = removed.get('slides', 0) + 1
                    
        return modified_data, removed


class MetricsCalculator:
    """Calculate playability metrics for fingering variants"""
    
    @staticmethod
    def compute_metrics(tab_data: Dict) -> Dict[str, Any]:
        """Calculate comprehensive metrics for a tab"""
        metrics = {
            'playability_score': 0,
            'difficulty_score': 0,
            'max_fret_span': 0,
            'position_changes': 0,
            'open_strings_used': 0,
            'avg_fret_jump': 0,
            'problem_sections': [],
            'measure_stats': []
        }
        
        all_frets = []
        all_jumps = []
        position_changes = 0
        open_strings = 0
        prev_position = None
        
        for measure in tab_data.get('measures', []):
            measure_frets = []
            measure_jumps = []
            chord_spans = []
            string_crossings = 0
            prev_string = None
            
            # Group notes by time for chord detection
            time_groups = {}
            for note in measure.get('notes', []):
                time_key = round(note['time'], 3)
                if time_key not in time_groups:
                    time_groups[time_key] = []
                time_groups[time_key].append(note)
                
            for time_key in sorted(time_groups.keys()):
                chord_notes = time_groups[time_key]
                
                if len(chord_notes) > 1:
                    # Chord span calculation
                    frets = [n['fret'] for n in chord_notes if n['fret'] > 0]
                    if frets:
                        span = max(frets) - min(frets)
                        chord_spans.append(span)
                        if span > 5:
                            metrics['problem_sections'].append({
                                'measure': measure['number'],
                                'reason': f'wide chord span ({span} frets)'
                            })
                            
                for note in chord_notes:
                    fret = note['fret']
                    string = note['string']
                    
                    all_frets.append(fret)
                    measure_frets.append(fret)
                    
                    if fret == 0:
                        open_strings += 1
                        
                    # Position tracking
                    position = MetricsCalculator._get_position(fret)
                    if prev_position and position != prev_position and position > 0:
                        position_changes += 1
                    prev_position = position
                    
                    # String crossings
                    if prev_string and string != prev_string:
                        string_crossings += 1
                    prev_string = string
                    
                    # Jump calculation (same string only)
                    if measure_frets and len(measure_frets) > 1:
                        if string == prev_string:
                            jump = abs(fret - measure_frets[-2])
                            all_jumps.append(jump)
                            measure_jumps.append(jump)
                            
            # Measure statistics
            measure_stat = {
                'measure_number': measure['number'],
                'avg_fret': sum(measure_frets) / len(measure_frets) if measure_frets else 0,
                'max_jump': max(measure_jumps) if measure_jumps else 0,
                'chord_span': max(chord_spans) if chord_spans else 0,
                'string_crossings': string_crossings
            }
            metrics['measure_stats'].append(measure_stat)
            
        # Calculate final scores
        metrics['max_fret_span'] = max([s['chord_span'] for s in metrics['measure_stats']]) if metrics['measure_stats'] else 0
        metrics['position_changes'] = position_changes
        metrics['open_strings_used'] = open_strings
        metrics['avg_fret_jump'] = sum(all_jumps) / len(all_jumps) if all_jumps else 0
        
        # Playability score (0-100, higher = easier)
        avg_jump = metrics['avg_fret_jump']
        changes_per_measure = position_changes / max(len(tab_data.get('measures', [])), 1)
        span_penalty = max(0, metrics['max_fret_span'] - 4) * 4
        open_ratio = open_strings / max(len(all_frets), 1)
        
        metrics['playability_score'] = max(0, min(100,
            100 - (2 * avg_jump) - (3 * changes_per_measure) - span_penalty + (open_ratio * 10)
        ))
        
        metrics['difficulty_score'] = 100 - metrics['playability_score']
        
        return metrics
    
    @staticmethod
    def _get_position(fret: int) -> int:
        """Map fret to position number"""
        if fret == 0:
            return 0
        elif fret <= 4:
            return 1
        elif fret <= 9:
            return 2
        elif fret <= 14:
            return 3
        else:
            return 4
            
    @staticmethod
    def recommend_skill_level(playability_score: float) -> str:
        """Recommend skill level based on playability score"""
        if playability_score >= 80:
            return 'beginner'
        elif playability_score >= 60:
            return 'intermediate'
        elif playability_score >= 40:
            return 'advanced'
        else:
            return 'expert'


class VariantGenerator:
    """Generate multiple fingering variants for a transcription"""
    
    def __init__(self, transcription: Transcription):
        self.transcription = transcription
        self.tuning = self._get_tuning()
        
    def _get_tuning(self) -> List[int]:
        """Extract tuning from transcription or use standard"""
        if self.transcription.guitar_notes:
            tuning = self.transcription.guitar_notes.get('tuning')
            if tuning:
                return tuning
        return STANDARD_TUNING
        
    def generate_all_variants(self) -> List[FingeringVariant]:
        """Generate all preset variants for the transcription"""
        variants = []
        
        # Clear existing variants
        with transaction.atomic():
            FingeringVariant.objects.filter(transcription=self.transcription).delete()
            
            for preset_name, weights in HUMANIZER_PRESETS.items():
                variant = self.generate_variant(preset_name, weights)
                if variant:
                    variants.append(variant)
                    
            # Select best variant by default
            if variants:
                best_variant = max(variants, key=lambda v: v.playability_score)
                best_variant.is_selected = True
                best_variant.save()
                
                # Update parent transcription
                self._update_parent_transcription(best_variant)
                
        return variants
    
    def generate_variant(self, preset_name: str, weights: OptimizationWeights) -> Optional[FingeringVariant]:
        """Generate a single variant with given weights"""
        
        # Extract notes from MIDI data
        notes = self._extract_notes_from_midi()
        if not notes:
            return None
            
        # Adjust weights for original preset based on analysis
        if preset_name == "original":
            weights = self._adjust_weights_for_original(weights)
            
        # Run optimizer
        optimizer = HumanizerService(tuning=self.tuning, weights=weights)
        optimized_positions = optimizer.optimize_sequence(notes)
        
        # Convert to tab data format
        tab_data = self._convert_to_tab_format(notes, optimized_positions)
        
        # Infer techniques
        technique_counts = TechniqueInference.infer_techniques(
            self.transcription.midi_data.get('notes', []) if self.transcription.midi_data else [],
            optimized_positions
        )
        tab_data['techniques_used'] = technique_counts
        
        # Apply simplifications for easy mode
        if preset_name == "easy":
            tab_data, removed_techniques = TechniqueInference.remove_techniques(tab_data, preset_name)
        else:
            removed_techniques = {}
            
        # Calculate metrics
        metrics = MetricsCalculator.compute_metrics(tab_data)
        
        # Create variant
        variant = FingeringVariant.objects.create(
            transcription=self.transcription,
            variant_name=preset_name,
            difficulty_score=metrics['difficulty_score'],
            playability_score=metrics['playability_score'],
            tab_data=tab_data,
            removed_techniques=removed_techniques if removed_techniques else None,
            config=weights.__dict__
        )
        
        # Create measure stats
        for stat in metrics['measure_stats']:
            FingeringMeasureStat.objects.create(
                variant=variant,
                **stat
            )
            
        return variant
    
    def _extract_notes_from_midi(self) -> List[Note]:
        """Extract Note objects from MIDI data"""
        notes = []
        
        if not self.transcription.midi_data:
            return notes
            
        midi_notes = self.transcription.midi_data.get('notes', [])
        
        for note_data in midi_notes:
            notes.append(Note(
                midi_note=int(note_data.get('midi_note', 60)),
                time=float(note_data.get('start_time', 0)),
                duration=float(note_data.get('end_time', 0)) - float(note_data.get('start_time', 0)),
                velocity=int(note_data.get('velocity', 80))
            ))
            
        return sorted(notes, key=lambda n: n.time)
    
    def _convert_to_tab_format(self, notes: List[Note], positions: List[Optional[FretChoice]]) -> Dict:
        """Convert optimizer output to guitar_notes JSON format"""
        
        # Initialize structure
        tab_data = {
            'tempo': self.transcription.estimated_tempo or 120,
            'time_signature': '4/4',
            'tuning': self.tuning,
            'measures': [],
            'techniques_used': {}
        }
        
        # Group notes into measures (assuming 4/4 time)
        tempo = tab_data['tempo']
        beats_per_measure = 4
        seconds_per_measure = (60.0 / tempo) * beats_per_measure
        
        current_measure = {
            'number': 1,
            'start_time': 0.0,
            'notes': []
        }
        
        for i, (note, pos) in enumerate(zip(notes, positions)):
            if pos is None:
                continue
                
            measure_num = int(note.time / seconds_per_measure) + 1
            
            if measure_num > current_measure['number']:
                if current_measure['notes']:
                    tab_data['measures'].append(current_measure)
                current_measure = {
                    'number': measure_num,
                    'start_time': (measure_num - 1) * seconds_per_measure,
                    'notes': []
                }
                
            # Add note to measure
            note_dict = {
                'string': pos.string,
                'fret': pos.fret,
                'time': note.time,
                'duration': note.duration,
                'velocity': note.velocity
            }
            
            current_measure['notes'].append(note_dict)
            
        # Add last measure
        if current_measure['notes']:
            tab_data['measures'].append(current_measure)
            
        return tab_data
    
    def _adjust_weights_for_original(self, weights: OptimizationWeights) -> OptimizationWeights:
        """Adjust weights based on transcription analysis"""
        
        # Analyze pitch distribution to find preferred position
        if self.transcription.midi_data:
            midi_notes = [n.get('midi_note', 60) for n in self.transcription.midi_data.get('notes', [])]
            if midi_notes:
                avg_midi = sum(midi_notes) / len(midi_notes)
                
                # Map average MIDI note to adjust position weight
                # Lower notes should have less position penalty (prefer lower frets)
                if avg_midi < 48:
                    weights.w_position *= 0.5
                elif avg_midi < 60:
                    weights.w_position *= 0.8
                else:
                    weights.w_position *= 1.2
                    
        # Adjust span constraints based on tempo
        if self.transcription.estimated_tempo:
            if self.transcription.estimated_tempo > 140:
                weights.max_physical_span = max(4, weights.max_physical_span - 1)
            elif self.transcription.estimated_tempo < 80:
                weights.max_physical_span = min(7, weights.max_physical_span + 1)
                
        return weights
    
    def _update_parent_transcription(self, selected_variant: FingeringVariant):
        """Update parent transcription with selected variant data"""
        
        # Update guitar_notes with selected variant's tab data
        self.transcription.guitar_notes = selected_variant.tab_data
        self.transcription.save(update_fields=['guitar_notes'])
        
        # Create or update PlayabilityMetrics
        metrics, created = PlayabilityMetrics.objects.get_or_create(
            transcription=self.transcription
        )
        
        # Calculate aggregated metrics from variant
        metrics.playability_score = selected_variant.playability_score
        metrics.recommended_skill_level = MetricsCalculator.recommend_skill_level(
            selected_variant.playability_score
        )
        
        # Get detailed metrics from measure stats
        measure_stats = selected_variant.measure_stats.all()
        if measure_stats:
            metrics.max_fret_span = max(s.chord_span for s in measure_stats)
            
            # Count position changes
            position_changes = 0
            prev_avg_fret = None
            for stat in measure_stats:
                if prev_avg_fret is not None:
                    if abs(stat.avg_fret - prev_avg_fret) > 5:
                        position_changes += 1
                prev_avg_fret = stat.avg_fret
            metrics.position_changes = position_changes
            
        # Count open strings
        open_count = 0
        for measure in selected_variant.tab_data.get('measures', []):
            for note in measure.get('notes', []):
                if note.get('fret') == 0:
                    open_count += 1
        metrics.open_strings_used = open_count
        
        # Suggest practice tempo
        if self.transcription.estimated_tempo:
            if selected_variant.playability_score < 40:
                metrics.slow_tempo_suggestion = int(self.transcription.estimated_tempo * 0.6)
            elif selected_variant.playability_score < 60:
                metrics.slow_tempo_suggestion = int(self.transcription.estimated_tempo * 0.75)
            else:
                metrics.slow_tempo_suggestion = int(self.transcription.estimated_tempo * 0.9)
                
        metrics.save()
    
    def generate_track_variants(self, track, track_notes: List[Dict]) -> List:
        """
        Generate fingering variants for a specific track.
        
        Args:
            track: Track model instance
            track_notes: List of note dictionaries for this track
            
        Returns:
            List of created TrackVariant objects
        """
        from ..models import TrackVariant  # Import here to avoid circular imports
        
        variants = []
        
        # Only generate variants for guitar tracks
        if track.instrument_type not in ['electric_guitar', 'acoustic_guitar']:
            return variants
        
        # Clear existing track variants
        with transaction.atomic():
            TrackVariant.objects.filter(track=track).delete()
            
            # Convert track notes to Note objects
            notes = self._convert_track_notes_to_note_objects(track_notes)
            if not notes:
                return variants
            
            # Generate variants for each preset
            for preset_name, weights in HUMANIZER_PRESETS.items():
                variant = self._generate_track_variant(track, preset_name, weights, notes, track_notes)
                if variant:
                    variants.append(variant)
                    
            # Select best variant by default (highest playability score)
            if variants:
                best_variant = max(variants, key=lambda v: v.playability_score)
                best_variant.is_selected = True
                best_variant.save()
                
        return variants
    
    def _generate_track_variant(self, track, preset_name: str, weights: OptimizationWeights, 
                              notes: List[Note], track_notes: List[Dict]) -> Optional:
        """Generate a single variant for a specific track."""
        from .models import TrackVariant  # Import here to avoid circular imports
        
        # Adjust weights for track-specific considerations
        if preset_name == "original":
            weights = self._adjust_weights_for_track(weights, track_notes, track)
            
        # Run optimizer
        optimizer = HumanizerService(tuning=self.tuning, weights=weights)
        optimized_positions = optimizer.optimize_sequence(notes)
        
        # Convert to tab data format
        tab_data = self._convert_to_tab_format_for_track(notes, optimized_positions, track)
        
        # Infer techniques
        technique_counts = TechniqueInference.infer_techniques(track_notes, optimized_positions)
        tab_data['techniques_used'] = technique_counts
        
        # Apply simplifications for easy mode
        removed_techniques = {}
        if preset_name == "easy":
            tab_data, removed_techniques = TechniqueInference.remove_techniques(tab_data, preset_name)
            
        # Calculate metrics
        metrics = MetricsCalculator.compute_metrics(tab_data)
        
        # Create track variant
        variant = TrackVariant.objects.create(
            track=track,
            variant_name=preset_name,
            difficulty_score=metrics['difficulty_score'],
            playability_score=metrics['playability_score'],
            tab_data=tab_data,
            removed_techniques=removed_techniques if removed_techniques else None,
            config=weights.__dict__
        )
        
        return variant
    
    def _convert_track_notes_to_note_objects(self, track_notes: List[Dict]) -> List[Note]:
        """Convert track-specific note data to Note objects."""
        notes = []
        
        for note_data in track_notes:
            notes.append(Note(
                midi_note=int(note_data.get('midi_note', 60)),
                time=float(note_data.get('start_time', 0)),
                duration=float(note_data.get('end_time', 0)) - float(note_data.get('start_time', 0)),
                velocity=int(note_data.get('velocity', 80))
            ))
            
        return sorted(notes, key=lambda n: n.time)
    
    def _adjust_weights_for_track(self, weights: OptimizationWeights, track_notes: List[Dict], track) -> OptimizationWeights:
        """Adjust optimization weights based on track characteristics."""
        
        # Analyze track-specific features
        if track_notes:
            midi_notes = [n.get('midi_note', 60) for n in track_notes]
            avg_midi = sum(midi_notes) / len(midi_notes)
            
            # Adjust based on instrument type
            if track.instrument_type == 'bass':
                # Bass guitars typically play in lower register
                weights.w_position *= 0.7  # Less penalty for low positions
                weights.w_open_bonus *= 1.5  # Encourage open strings for bass
                weights.max_physical_span = min(4, weights.max_physical_span)  # Tighter spans for bass
                
            elif track.instrument_type == 'acoustic_guitar':
                # Acoustic guitars often use more open chords
                weights.w_open_bonus *= 1.25
                weights.w_position *= 0.9  # Slight preference for lower positions
                
            elif track.instrument_type == 'electric_guitar':
                # Electric guitars can handle more complex fingerings
                if avg_midi > 60:  # Higher register
                    weights.w_position *= 1.1  # Higher penalty for low positions
                    weights.max_physical_span = min(7, weights.max_physical_span + 1)
                    
        # Adjust based on track prominence
        if hasattr(track, 'prominence_score') and track.prominence_score:
            if track.prominence_score > 0.7:  # Prominent track
                # More complex fingerings acceptable for lead parts
                if weights.max_physical_span < 6:
                    weights.max_physical_span += 1
                    
            elif track.prominence_score < 0.3:  # Background track
                # Simpler fingerings for rhythm parts
                weights.w_open_bonus = min(3.0, weights.w_open_bonus * 1.5)
                weights.max_physical_span = max(4, weights.max_physical_span - 1)
                
        return weights
    
    def _convert_to_tab_format_for_track(self, notes: List[Note], positions: List[Optional[FretChoice]], track) -> Dict:
        """Convert optimizer output to track-specific tab format."""
        
        # Start with basic conversion
        tab_data = self._convert_to_tab_format(notes, positions)
        
        # Add track-specific metadata
        tab_data['track_info'] = {
            'track_type': track.track_type,
            'instrument_type': track.instrument_type,
            'track_name': track.display_name,
            'prominence_score': getattr(track, 'prominence_score', 0.5)
        }
        
        # Adjust tempo if different from main transcription
        if hasattr(track, 'transcription') and track.transcription.estimated_tempo:
            tab_data['tempo'] = track.transcription.estimated_tempo
            
        return tab_data
    
    def update_track_selection(self, track, variant_name: str) -> bool:
        """
        Update which variant is selected for a track.
        
        Args:
            track: Track model instance
            variant_name: Name of variant to select
            
        Returns:
            True if successful, False otherwise
        """
        from .models import TrackVariant  # Import here to avoid circular imports
        
        try:
            with transaction.atomic():
                # Deselect all variants for this track
                TrackVariant.objects.filter(track=track, is_selected=True).update(is_selected=False)
                
                # Select the requested variant
                variant = TrackVariant.objects.filter(track=track, variant_name=variant_name).first()
                if variant:
                    variant.is_selected = True
                    variant.save()
                    
                    # Update track with selected variant data
                    track.guitar_notes = variant.tab_data
                    track.save(update_fields=['guitar_notes'])
                    
                    return True
                    
        except Exception as e:
            logger.error(f"Failed to update track variant selection: {str(e)}")
            
        return False