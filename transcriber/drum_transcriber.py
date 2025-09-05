"""
Drum transcription service for detecting and transcribing drum patterns.
Uses onset detection, spectral analysis, and pattern recognition.
"""

import numpy as np
import librosa
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)


@dataclass
class DrumHit:
    """Represents a single drum hit"""
    time: float  # Time in seconds
    drum_type: str  # 'kick', 'snare', 'hihat', 'crash', 'ride', 'tom'
    velocity: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0


class DrumTranscriber:
    """
    Transcribes drum audio to drum notation.
    Uses spectral analysis to separate different drum components.
    """
    
    # Frequency ranges for different drum components (Hz)
    DRUM_FREQ_RANGES = {
        'kick': (20, 100),      # Bass drum
        'snare': (150, 300),    # Snare drum  
        'hihat': (3000, 8000),  # Hi-hat
        'crash': (4000, 12000), # Crash cymbal
        'ride': (2000, 6000),   # Ride cymbal
        'tom_low': (80, 150),   # Low tom
        'tom_mid': (120, 200),  # Mid tom
        'tom_high': (150, 250), # High tom
    }
    
    # Standard drum kit mapping for notation
    DRUM_MIDI_MAP = {
        'kick': 36,      # C1 - Bass Drum
        'snare': 38,     # D1 - Snare
        'hihat': 42,     # F#1 - Closed Hi-hat
        'hihat_open': 46, # A#1 - Open Hi-hat
        'crash': 49,     # C#2 - Crash Cymbal
        'ride': 51,      # D#2 - Ride Cymbal
        'tom_high': 50,  # D2 - High Tom
        'tom_mid': 47,   # B1 - Mid Tom
        'tom_low': 45,   # A1 - Low Tom
    }
    
    def __init__(self, sample_rate: int = 22050):
        self.sample_rate = sample_rate
        
    def transcribe(self, audio_path: str) -> Dict:
        """
        Transcribe drums from audio file.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Dictionary containing drum hits, patterns, and notation
        """
        try:
            # Load audio
            y, sr = librosa.load(audio_path, sr=self.sample_rate)
            
            # Detect tempo and beats
            tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
            beat_times = librosa.frames_to_time(beats, sr=sr)
            
            # Detect onsets (drum hits)
            onset_frames = librosa.onset.onset_detect(
                y=y, sr=sr,
                backtrack=True,
                units='frames'
            )
            onset_times = librosa.frames_to_time(onset_frames, sr=sr)
            
            # Classify each onset as a drum type
            drum_hits = self._classify_drum_hits(y, sr, onset_frames, onset_times)
            
            # Detect patterns and structure
            patterns = self._detect_patterns(drum_hits, beat_times, tempo)
            
            # Generate drum notation
            notation = self._generate_drum_notation(drum_hits, tempo, beat_times)
            
            return {
                'tempo': float(tempo),
                'beats': beat_times.tolist(),
                'drum_hits': [self._drum_hit_to_dict(hit) for hit in drum_hits],
                'patterns': patterns,
                'notation': notation,
                'measures': self._organize_into_measures(drum_hits, beat_times, tempo)
            }
            
        except Exception as e:
            logger.error(f"Error transcribing drums: {str(e)}")
            return {
                'error': str(e),
                'tempo': 120,
                'drum_hits': [],
                'patterns': {},
                'notation': {}
            }
    
    def _classify_drum_hits(self, y: np.ndarray, sr: int, 
                           onset_frames: np.ndarray, 
                           onset_times: np.ndarray) -> List[DrumHit]:
        """
        Classify each onset as a specific drum type using spectral analysis.
        """
        drum_hits = []
        
        # Compute spectogram for frequency analysis
        D = librosa.stft(y)
        freqs = librosa.fft_frequencies(sr=sr)
        
        for i, (frame, time) in enumerate(zip(onset_frames, onset_times)):
            # Get spectral slice around onset
            start_frame = max(0, frame - 5)
            end_frame = min(D.shape[1], frame + 10)
            spectral_slice = np.abs(D[:, start_frame:end_frame]).mean(axis=1)
            
            # Analyze frequency content to determine drum type
            drum_type, confidence = self._identify_drum_type(spectral_slice, freqs)
            
            # Calculate velocity from amplitude
            velocity = self._calculate_velocity(y, frame, sr)
            
            drum_hits.append(DrumHit(
                time=float(time),
                drum_type=drum_type,
                velocity=velocity,
                confidence=confidence
            ))
        
        return drum_hits
    
    def _identify_drum_type(self, spectrum: np.ndarray, 
                           freqs: np.ndarray) -> Tuple[str, float]:
        """
        Identify drum type from frequency spectrum.
        """
        scores = {}
        
        for drum_type, (low_freq, high_freq) in self.DRUM_FREQ_RANGES.items():
            # Get frequency band mask
            mask = (freqs >= low_freq) & (freqs <= high_freq)
            
            # Calculate energy in this frequency band
            band_energy = spectrum[mask].sum()
            total_energy = spectrum.sum()
            
            if total_energy > 0:
                scores[drum_type] = band_energy / total_energy
            else:
                scores[drum_type] = 0
        
        # Additional heuristics for better classification
        if scores.get('kick', 0) > 0.6:
            return 'kick', scores['kick']
        elif scores.get('snare', 0) > 0.4:
            return 'snare', scores['snare']
        elif scores.get('hihat', 0) > 0.3:
            return 'hihat', scores['hihat']
        elif scores.get('crash', 0) > 0.25:
            return 'crash', scores['crash']
        else:
            # Default to most likely drum
            best_drum = max(scores, key=scores.get)
            return best_drum, scores[best_drum]
    
    def _calculate_velocity(self, y: np.ndarray, frame: int, sr: int) -> float:
        """
        Calculate velocity (loudness) of drum hit.
        """
        # Convert frame to sample
        sample = librosa.frames_to_samples(frame)
        
        # Get audio segment around hit
        start = max(0, sample - sr // 100)  # 10ms before
        end = min(len(y), sample + sr // 50)  # 20ms after
        
        # Calculate RMS energy
        segment = y[start:end]
        rms = np.sqrt(np.mean(segment**2))
        
        # Normalize to 0-1 range
        velocity = min(1.0, rms * 10)  # Adjust scaling factor as needed
        
        return float(velocity)
    
    def _detect_patterns(self, drum_hits: List[DrumHit], 
                        beat_times: np.ndarray, 
                        tempo: float) -> Dict:
        """
        Detect common drum patterns (e.g., basic rock beat, swing, etc.)
        """
        patterns = {
            'main_pattern': None,
            'fills': [],
            'variations': []
        }
        
        if not drum_hits:
            return patterns
        
        # Group hits by measure (assuming 4/4 time)
        beats_per_measure = 4
        measure_duration = 60.0 / tempo * beats_per_measure
        
        # Analyze pattern every 2 measures
        window_size = measure_duration * 2
        
        # Detect basic rock pattern (kick on 1&3, snare on 2&4, hihat eighth notes)
        kick_pattern = []
        snare_pattern = []
        hihat_pattern = []
        
        for hit in drum_hits:
            if hit.time < window_size:
                if hit.drum_type == 'kick':
                    kick_pattern.append(hit.time)
                elif hit.drum_type == 'snare':
                    snare_pattern.append(hit.time)
                elif hit.drum_type == 'hihat':
                    hihat_pattern.append(hit.time)
        
        # Identify pattern type
        if len(kick_pattern) >= 2 and len(snare_pattern) >= 2:
            patterns['main_pattern'] = 'rock_beat'
        elif len(hihat_pattern) > 8:
            patterns['main_pattern'] = 'hihat_groove'
        else:
            patterns['main_pattern'] = 'custom'
        
        # Detect fills (sudden increase in drum activity)
        patterns['fills'] = self._detect_fills(drum_hits, beat_times)
        
        return patterns
    
    def _detect_fills(self, drum_hits: List[DrumHit], 
                     beat_times: np.ndarray) -> List[Dict]:
        """
        Detect drum fills (bursts of activity).
        """
        fills = []
        
        # Use sliding window to detect high activity regions
        window_size = 2.0  # 2 second window
        step_size = 0.5    # 0.5 second step
        
        hit_times = [hit.time for hit in drum_hits]
        max_time = max(hit_times) if hit_times else 0
        
        for start_time in np.arange(0, max_time, step_size):
            end_time = start_time + window_size
            
            # Count hits in window
            window_hits = [h for h in drum_hits if start_time <= h.time < end_time]
            hit_density = len(window_hits) / window_size
            
            # If density is high, it might be a fill
            if hit_density > 8:  # More than 8 hits per second
                fills.append({
                    'start': float(start_time),
                    'end': float(end_time),
                    'density': float(hit_density),
                    'hits': len(window_hits)
                })
        
        # Merge overlapping fills
        merged_fills = []
        for fill in fills:
            if merged_fills and fill['start'] < merged_fills[-1]['end']:
                merged_fills[-1]['end'] = fill['end']
            else:
                merged_fills.append(fill)
        
        return merged_fills
    
    def _generate_drum_notation(self, drum_hits: List[DrumHit], 
                               tempo: float, 
                               beat_times: np.ndarray) -> Dict:
        """
        Generate drum notation in a format suitable for display/export.
        """
        notation = {
            'tempo': tempo,
            'time_signature': '4/4',  # Assume 4/4 for now
            'tracks': {}
        }
        
        # Separate hits by drum type
        for drum_type in self.DRUM_MIDI_MAP.keys():
            notation['tracks'][drum_type] = []
        
        # Quantize hits to nearest 16th note
        sixteenth_duration = 60.0 / tempo / 4  # Duration of 16th note
        
        for hit in drum_hits:
            # Quantize time
            quantized_time = round(hit.time / sixteenth_duration) * sixteenth_duration
            
            # Add to appropriate track
            if hit.drum_type in notation['tracks']:
                notation['tracks'][hit.drum_type].append({
                    'time': float(quantized_time),
                    'velocity': float(hit.velocity),
                    'confidence': float(hit.confidence)
                })
        
        return notation
    
    def _organize_into_measures(self, drum_hits: List[DrumHit], 
                               beat_times: np.ndarray, 
                               tempo: float) -> List[Dict]:
        """
        Organize drum hits into measures for easier processing.
        """
        measures = []
        beats_per_measure = 4
        measure_duration = 60.0 / tempo * beats_per_measure
        
        if not drum_hits:
            return measures
        
        max_time = max(hit.time for hit in drum_hits)
        num_measures = int(max_time / measure_duration) + 1
        
        for measure_num in range(num_measures):
            start_time = measure_num * measure_duration
            end_time = (measure_num + 1) * measure_duration
            
            # Get hits in this measure
            measure_hits = [
                self._drum_hit_to_dict(hit) 
                for hit in drum_hits 
                if start_time <= hit.time < end_time
            ]
            
            # Calculate relative positions within measure
            for hit in measure_hits:
                hit['relative_position'] = (hit['time'] - start_time) / measure_duration
                hit['beat'] = int(hit['relative_position'] * beats_per_measure) + 1
            
            measures.append({
                'number': measure_num + 1,
                'start_time': float(start_time),
                'end_time': float(end_time),
                'hits': measure_hits,
                'hit_count': len(measure_hits)
            })
        
        return measures
    
    def _drum_hit_to_dict(self, hit: DrumHit) -> Dict:
        """Convert DrumHit to dictionary."""
        return {
            'time': float(hit.time),
            'drum_type': hit.drum_type,
            'velocity': float(hit.velocity),
            'confidence': float(hit.confidence),
            'midi_note': self.DRUM_MIDI_MAP.get(hit.drum_type, 36)
        }
    
    def generate_drum_tab(self, drum_hits: List[Dict], tempo: float) -> str:
        """
        Generate ASCII drum tab notation.
        
        Example:
        HH |x-x-x-x-x-x-x-x-|
        SD |----o-------o---|
        BD |o-------o-------|
        """
        # Quantize to 16th notes
        sixteenth_duration = 60.0 / tempo / 4
        measure_duration = 60.0 / tempo * 4  # 4/4 time
        
        # Group by measures
        measures = []
        max_time = max(hit['time'] for hit in drum_hits) if drum_hits else measure_duration
        num_measures = int(max_time / measure_duration) + 1
        
        for m in range(num_measures):
            measure_start = m * measure_duration
            measure_end = (m + 1) * measure_duration
            
            # Initialize empty measure for each drum
            measure = {
                'HH': ['-'] * 16,  # Hi-hat
                'SD': ['-'] * 16,  # Snare
                'BD': ['-'] * 16,  # Bass drum
                'CR': ['-'] * 16,  # Crash
            }
            
            # Place hits in measure
            for hit in drum_hits:
                if measure_start <= hit['time'] < measure_end:
                    # Calculate position in measure (0-15)
                    rel_time = hit['time'] - measure_start
                    position = int(rel_time / sixteenth_duration)
                    position = min(15, max(0, position))
                    
                    # Map drum type to line
                    drum_type = hit.get('drum_type', 'kick')
                    if drum_type in ['hihat', 'hihat_open']:
                        symbol = 'x' if drum_type == 'hihat' else 'o'
                        measure['HH'][position] = symbol
                    elif drum_type == 'snare':
                        measure['SD'][position] = 'o'
                    elif drum_type == 'kick':
                        measure['BD'][position] = 'o'
                    elif drum_type == 'crash':
                        measure['CR'][position] = 'X'
            
            measures.append(measure)
        
        # Format as tab
        tab_lines = []
        
        # Header
        tab_lines.append(f"Tempo: {tempo:.0f} BPM")
        tab_lines.append("Time: 4/4")
        tab_lines.append("")
        
        # Tab notation
        for i, measure in enumerate(measures):
            if i % 4 == 0:  # New line every 4 measures
                if i > 0:
                    tab_lines.append("")
                tab_lines.append(f"Measure {i+1}:")
                
            # Only show non-empty drum lines
            for drum, symbols in [
                ('CR', measure['CR']),
                ('HH', measure['HH']),
                ('SD', measure['SD']),
                ('BD', measure['BD'])
            ]:
                if any(s != '-' for s in symbols):
                    line = f"{drum} |{''.join(symbols)}|"
                    tab_lines.append(line)
        
        return '\n'.join(tab_lines)