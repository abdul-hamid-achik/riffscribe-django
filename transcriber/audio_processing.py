import librosa
import numpy as np
from scipy.signal import find_peaks
import json
from typing import Dict, List, Tuple, Optional


class AudioAnalyzer:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.y = None
        self.sr = None
        self.tempo = None
        self.beat_frames = None
        
    def load_audio(self):
        self.y, self.sr = librosa.load(self.file_path, sr=None)
        return self.y, self.sr
    
    def get_duration(self) -> float:
        if self.y is None:
            self.load_audio()
        return librosa.get_duration(y=self.y, sr=self.sr)
    
    def estimate_tempo(self) -> Tuple[float, np.ndarray]:
        if self.y is None:
            self.load_audio()
        
        # Estimate tempo
        tempo, beats = librosa.beat.beat_track(y=self.y, sr=self.sr)
        self.tempo = tempo
        self.beat_frames = beats
        return float(tempo), beats
    
    def estimate_key(self) -> str:
        if self.y is None:
            self.load_audio()
        
        # Compute chroma features
        chroma = librosa.feature.chroma_cqt(y=self.y, sr=self.sr)
        
        # Average across time
        chroma_avg = np.mean(chroma, axis=1)
        
        # Map to key names
        keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        key_idx = np.argmax(chroma_avg)
        
        # Simple major/minor detection based on third interval
        major_third = (key_idx + 4) % 12
        minor_third = (key_idx + 3) % 12
        
        if chroma_avg[major_third] > chroma_avg[minor_third]:
            return f"{keys[key_idx]} Major"
        else:
            return f"{keys[key_idx]} Minor"
    
    def detect_onset_times(self) -> List[float]:
        if self.y is None:
            self.load_audio()
        
        # Detect onsets
        onset_frames = librosa.onset.onset_detect(
            y=self.y, 
            sr=self.sr,
            backtrack=True
        )
        
        # Convert frames to time
        onset_times = librosa.frames_to_time(onset_frames, sr=self.sr)
        return onset_times.tolist()
    
    def extract_pitch_contour(self) -> Dict:
        if self.y is None:
            self.load_audio()
        
        # Use harmonic-percussive separation
        y_harmonic, y_percussive = librosa.effects.hpss(self.y)
        
        # Extract pitch using piptrack
        pitches, magnitudes = librosa.piptrack(
            y=y_harmonic, 
            sr=self.sr,
            threshold=0.1
        )
        
        # Get the most prominent pitch at each time
        pitch_contour = []
        for t in range(pitches.shape[1]):
            index = magnitudes[:, t].argmax()
            pitch = pitches[index, t]
            if pitch > 0:
                pitch_contour.append({
                    'time': librosa.frames_to_time(t, sr=self.sr),
                    'frequency': float(pitch),
                    'midi_note': librosa.hz_to_midi(pitch) if pitch > 0 else None
                })
        
        return pitch_contour
    
    def estimate_complexity(self) -> str:
        if self.y is None:
            self.load_audio()
        
        # Analyze various features to estimate complexity
        onset_times = self.detect_onset_times()
        notes_per_second = len(onset_times) / self.get_duration() if onset_times else 0
        
        # Spectral complexity
        spectral_centroid = librosa.feature.spectral_centroid(y=self.y, sr=self.sr)
        spectral_variance = np.var(spectral_centroid)
        
        # Simple heuristic for complexity
        if notes_per_second < 2 and spectral_variance < 1000000:
            return 'simple'
        elif notes_per_second < 4 and spectral_variance < 2000000:
            return 'moderate'
        else:
            return 'complex'
    
    def detect_instruments(self) -> List[str]:
        if self.y is None:
            self.load_audio()
        
        instruments = []
        
        # Analyze spectral features
        spectral_centroid = librosa.feature.spectral_centroid(y=self.y, sr=self.sr)
        mean_centroid = np.mean(spectral_centroid)
        
        # Zero crossing rate for percussive detection
        zcr = librosa.feature.zero_crossing_rate(self.y)
        mean_zcr = np.mean(zcr)
        
        # Simple heuristic-based detection
        # This is a simplified approach - real instrument detection would use ML models
        if mean_centroid < 2000:
            instruments.append('bass')
        if 2000 < mean_centroid < 4000:
            instruments.append('guitar')
        if mean_centroid > 4000:
            instruments.append('cymbals')
        if mean_zcr > 0.1:
            instruments.append('drums')
        
        # Default to guitar if nothing detected
        if not instruments:
            instruments = ['guitar']
        
        return instruments


class GuitarTabGenerator:
    def __init__(self, pitch_contour: List[Dict], tempo: float):
        self.pitch_contour = pitch_contour
        self.tempo = tempo
        self.tuning = [40, 45, 50, 55, 59, 64]  # Standard tuning MIDI notes (E, A, D, G, B, E)
        
    def midi_to_fret(self, midi_note: float, string_idx: int) -> Optional[int]:
        if midi_note is None:
            return None
        
        fret = int(midi_note - self.tuning[string_idx])
        if 0 <= fret <= 24:  # Typical guitar range
            return fret
        return None
    
    def find_best_string_for_note(self, midi_note: float) -> Tuple[int, int]:
        best_string = -1
        best_fret = -1
        min_fret = 25
        
        for string_idx in range(6):
            fret = self.midi_to_fret(midi_note, string_idx)
            if fret is not None and 0 <= fret < min_fret:
                min_fret = fret
                best_string = string_idx
                best_fret = fret
        
        return best_string, best_fret
    
    def generate_tab_data(self) -> Dict:
        tab_data = {
            'tempo': self.tempo,
            'time_signature': '4/4',
            'measures': []
        }
        
        # Group notes into measures based on tempo
        measure_duration = 60.0 / self.tempo * 4  # Duration of one 4/4 measure
        current_measure = {'notes': [], 'start_time': 0}
        
        for note_data in self.pitch_contour:
            if note_data['midi_note']:
                string, fret = self.find_best_string_for_note(note_data['midi_note'])
                if string >= 0:
                    note = {
                        'string': string,
                        'fret': fret,
                        'time': note_data['time'],
                        'duration': 0.25  # Default quarter note
                    }
                    
                    # Check if we need a new measure
                    if note_data['time'] - current_measure['start_time'] > measure_duration:
                        if current_measure['notes']:
                            tab_data['measures'].append(current_measure)
                        current_measure = {
                            'notes': [],
                            'start_time': note_data['time']
                        }
                    
                    current_measure['notes'].append(note)
        
        # Add the last measure
        if current_measure['notes']:
            tab_data['measures'].append(current_measure)
        
        return tab_data
    
    def to_ascii_tab(self, max_width: int = 80) -> str:
        tab_data = self.generate_tab_data()
        string_names = ['e', 'B', 'G', 'D', 'A', 'E']
        tab_lines = {name: [] for name in string_names}
        
        for measure in tab_data['measures'][:4]:  # Limit to first 4 measures for preview
            measure_tabs = {name: '-' * 16 for name in string_names}  # 16 chars per measure
            
            for note in measure['notes']:
                string_name = string_names[note['string']]
                position = int((note['time'] - measure['start_time']) / (60.0 / self.tempo * 4) * 16)
                if position < 16:
                    measure_tabs[string_name] = (
                        measure_tabs[string_name][:position] + 
                        str(note['fret']) + 
                        measure_tabs[string_name][position + len(str(note['fret'])):]
                    )
            
            for name in string_names:
                tab_lines[name].append(measure_tabs[name])
        
        # Format output
        output = []
        for name in string_names:
            line = f"{name}|" + "-|-".join(tab_lines[name]) + "-|"
            output.append(line)
        
        return '\n'.join(output)