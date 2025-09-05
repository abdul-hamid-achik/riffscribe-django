"""
Advanced ML Pipeline for audio transcription with source separation and pitch detection.
"""
import os
import numpy as np
import librosa
import torch
import logging
from typing import Dict, List, Optional, Tuple
import tempfile
import soundfile as sf

# ML model imports
try:
    import basic_pitch
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import predict
except ImportError:
    basic_pitch = None
    
try:
    import demucs.api
    from demucs import pretrained
    from demucs.apply import apply_model
except ImportError:
    demucs = None

try:
    import crepe
except ImportError:
    crepe = None

try:
    import madmom
except ImportError:
    madmom = None

from scipy.signal import find_peaks
import music21

logger = logging.getLogger(__name__)


class MLPipeline:
    """
    Comprehensive ML pipeline for guitar transcription.
    Integrates multiple models for source separation, pitch detection, and analysis.
    """
    
    def __init__(self, use_gpu=False, demucs_model='htdemucs', basic_pitch_model='default'):
        self.use_gpu = use_gpu and torch.cuda.is_available()
        self.device = torch.device('cuda' if self.use_gpu else 'cpu')
        self.demucs_model_name = demucs_model
        self.basic_pitch_model = basic_pitch_model
        
        # Load models lazily
        self.demucs_model = None
        self.basic_pitch_loaded = False
        
        logger.info(f"ML Pipeline initialized. GPU: {self.use_gpu}, Device: {self.device}")
    
    def analyze_audio(self, audio_path: str) -> Dict:
        """
        Comprehensive audio analysis including tempo, key, complexity, and instruments.
        """
        # Load audio
        y, sr = librosa.load(audio_path, sr=None)
        
        # Basic info
        duration = librosa.get_duration(y=y, sr=sr)
        channels = 1 if len(y.shape) == 1 else y.shape[0]
        
        # Tempo detection (use madmom if available for better accuracy)
        if madmom:
            tempo, beats = self._detect_tempo_madmom(audio_path)
        else:
            tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
            tempo = float(tempo)
        
        # Key detection
        key = self._detect_key(y, sr)
        
        # Time signature detection
        time_signature = self._detect_time_signature(y, sr, beats)
        
        # Complexity estimation
        complexity = self._estimate_complexity(y, sr, tempo)
        
        # Instrument detection
        instruments = self._detect_instruments(y, sr)
        
        return {
            'duration': duration,
            'sample_rate': sr,
            'channels': channels,
            'tempo': tempo,
            'beats': beats.tolist() if isinstance(beats, np.ndarray) else beats,
            'key': key,
            'time_signature': time_signature,
            'complexity': complexity,
            'instruments': instruments
        }
    
    def separate_sources(self, audio_path: str) -> Dict[str, str]:
        """
        Separate audio into stems using Demucs.
        Returns paths to separated audio files.
        """
        if not demucs:
            logger.warning("Demucs not available, skipping source separation")
            return {'original': audio_path}
        
        try:
            # Load Demucs model
            if self.demucs_model is None:
                self.demucs_model = pretrained.get_model(self.demucs_model_name)
                self.demucs_model.to(self.device)
                self.demucs_model.eval()
            
            # Load audio
            wav, sr = librosa.load(audio_path, sr=44100, mono=False)
            if len(wav.shape) == 1:
                wav = np.stack([wav, wav])  # Convert mono to stereo
            
            # Prepare input
            wav_tensor = torch.from_numpy(wav).float().unsqueeze(0).to(self.device)
            
            # Apply model
            with torch.no_grad():
                sources = apply_model(self.demucs_model, wav_tensor, device=self.device)[0]
            
            # Save separated sources
            output_dir = tempfile.mkdtemp(prefix='demucs_')
            stems = {}
            
            source_names = self.demucs_model.sources
            for i, name in enumerate(source_names):
                if name in ['guitar', 'bass', 'drums', 'vocals']:
                    stem_path = os.path.join(output_dir, f'{name}.wav')
                    stem_audio = sources[i].cpu().numpy()
                    sf.write(stem_path, stem_audio.T, sr)
                    stems[name] = stem_path
            
            logger.info(f"Source separation complete. Stems saved to {output_dir}")
            return stems
            
        except Exception as e:
            logger.error(f"Source separation failed: {str(e)}")
            return {'original': audio_path}
    
    def transcribe(self, audio_path: str) -> Dict:
        """
        Transcribe audio to MIDI notes using multiple methods.
        Primary: basic-pitch (polyphonic)
        Fallback: crepe (monophonic) or librosa
        """
        notes = []
        midi_data = {}
        
        # Try basic-pitch first (best for polyphonic)
        if basic_pitch:
            try:
                notes, midi_data = self._transcribe_basic_pitch(audio_path)
                logger.info(f"Basic-pitch transcription complete: {len(notes)} notes detected")
            except Exception as e:
                logger.warning(f"Basic-pitch failed: {str(e)}, falling back to alternatives")
        
        # Fallback to crepe for monophonic
        if not notes and crepe:
            try:
                notes, midi_data = self._transcribe_crepe(audio_path)
                logger.info(f"CREPE transcription complete: {len(notes)} notes detected")
            except Exception as e:
                logger.warning(f"CREPE failed: {str(e)}, falling back to librosa")
        
        # Final fallback to librosa
        if not notes:
            notes, midi_data = self._transcribe_librosa(audio_path)
            logger.info(f"Librosa transcription complete: {len(notes)} notes detected")
        
        # Post-process notes
        notes = self._post_process_notes(notes)
        
        return {
            'notes': notes,
            'midi_data': midi_data
        }
    
    def _transcribe_basic_pitch(self, audio_path: str) -> Tuple[List, Dict]:
        """Transcribe using basic-pitch model."""
        # Run prediction
        model_output, midi_data, note_events = predict(
            audio_path,
            model_or_model_path=ICASSP_2022_MODEL_PATH,
            onset_threshold=0.5,
            frame_threshold=0.3,
            minimum_note_length=127,  # in ms
            minimum_frequency=82.41,  # E2
            maximum_frequency=1318.51,  # E6
            multiple_pitch_bends=False,
            melodia_trick=True,
            midi_tempo=120,
        )
        
        # Convert note events to our format
        notes = []
        for start_time, end_time, pitch, velocity, _ in note_events:
            notes.append({
                'start_time': float(start_time),
                'end_time': float(end_time),
                'pitch': float(pitch),
                'midi_note': int(pitch),
                'velocity': float(velocity),
                'confidence': float(velocity)
            })
        
        return notes, {'raw_output': model_output}
    
    def _transcribe_crepe(self, audio_path: str) -> Tuple[List, Dict]:
        """Transcribe using CREPE model (monophonic)."""
        y, sr = librosa.load(audio_path, sr=16000)
        
        # Get f0 with CREPE
        time, frequency, confidence, activation = crepe.predict(
            y, sr, viterbi=True, step_size=10
        )
        
        # Convert to notes
        notes = []
        current_note = None
        
        for i, (t, f, c) in enumerate(zip(time, frequency, confidence)):
            if c > 0.5 and f > 0:  # Confident and valid frequency
                midi_note = librosa.hz_to_midi(f)
                
                if current_note is None or abs(current_note['midi_note'] - midi_note) > 0.5:
                    # New note
                    if current_note:
                        notes.append(current_note)
                    current_note = {
                        'start_time': float(t),
                        'end_time': float(t),
                        'pitch': float(f),
                        'midi_note': int(round(midi_note)),
                        'velocity': float(c * 127),
                        'confidence': float(c)
                    }
                else:
                    # Continue current note
                    current_note['end_time'] = float(t)
            else:
                # End current note if any
                if current_note:
                    notes.append(current_note)
                    current_note = None
        
        if current_note:
            notes.append(current_note)
        
        return notes, {'method': 'crepe'}
    
    def _transcribe_librosa(self, audio_path: str) -> Tuple[List, Dict]:
        """Fallback transcription using librosa."""
        y, sr = librosa.load(audio_path, sr=None)
        
        # Harmonic-percussive separation
        y_harmonic, y_percussive = librosa.effects.hpss(y)
        
        # Onset detection
        onset_frames = librosa.onset.onset_detect(y=y, sr=sr, backtrack=True)
        onset_times = librosa.frames_to_time(onset_frames, sr=sr)
        
        # Pitch detection using piptrack
        pitches, magnitudes = librosa.piptrack(y=y_harmonic, sr=sr, threshold=0.1)
        
        notes = []
        for i, onset_time in enumerate(onset_times):
            # Get pitch at onset
            onset_frame = onset_frames[i]
            if onset_frame < pitches.shape[1]:
                index = magnitudes[:, onset_frame].argmax()
                pitch = pitches[index, onset_frame]
                
                if pitch > 0:
                    midi_note = librosa.hz_to_midi(pitch)
                    
                    # Estimate duration (to next onset or 0.5s)
                    duration = 0.5
                    if i < len(onset_times) - 1:
                        duration = min(onset_times[i + 1] - onset_time, 0.5)
                    
                    notes.append({
                        'start_time': float(onset_time),
                        'end_time': float(onset_time + duration),
                        'pitch': float(pitch),
                        'midi_note': int(round(midi_note)),
                        'velocity': 80,
                        'confidence': 0.5
                    })
        
        return notes, {'method': 'librosa'}
    
    def _detect_tempo_madmom(self, audio_path: str) -> Tuple[float, np.ndarray]:
        """Detect tempo using madmom for better accuracy."""
        from madmom.features.tempo import TempoEstimationProcessor
        from madmom.features.beats import RNNBeatProcessor
        
        # Tempo estimation
        tempo_processor = TempoEstimationProcessor(fps=100)
        beat_processor = RNNBeatProcessor()
        
        beats = beat_processor(audio_path)
        tempo = tempo_processor(beats)
        
        # Get most likely tempo
        if len(tempo) > 0:
            main_tempo = tempo[0][0]
        else:
            main_tempo = 120.0
        
        return float(main_tempo), beats
    
    def _detect_key(self, y: np.ndarray, sr: int) -> str:
        """Detect musical key using music21."""
        # Compute chroma features
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        chroma_avg = np.mean(chroma, axis=1)
        
        # Map to pitch classes
        pitch_classes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        
        # Use music21 for key analysis if available
        try:
            # Create a music21 stream from chroma
            s = music21.stream.Stream()
            for i, weight in enumerate(chroma_avg):
                if weight > 0.2:  # Threshold
                    note = music21.note.Note(pitch_classes[i])
                    note.volume.velocity = int(weight * 127)
                    s.append(note)
            
            # Analyze key
            key = s.analyze('key')
            return f"{key.tonic.name} {key.mode}"
        except:
            # Fallback to simple detection
            key_idx = np.argmax(chroma_avg)
            
            # Simple major/minor detection
            major_third = (key_idx + 4) % 12
            minor_third = (key_idx + 3) % 12
            
            if chroma_avg[major_third] > chroma_avg[minor_third]:
                return f"{pitch_classes[key_idx]} Major"
            else:
                return f"{pitch_classes[key_idx]} Minor"
    
    def _detect_time_signature(self, y: np.ndarray, sr: int, beats: np.ndarray) -> str:
        """Detect time signature from beat pattern."""
        if len(beats) < 4:
            return "4/4"
        
        # Calculate inter-beat intervals
        beat_intervals = np.diff(beats)
        
        # Look for patterns
        mean_interval = np.mean(beat_intervals)
        std_interval = np.std(beat_intervals)
        
        # Simple heuristic - can be improved
        if std_interval / mean_interval < 0.1:
            # Regular beats
            return "4/4"
        else:
            # Check for waltz pattern
            if len(beat_intervals) > 6:
                # Group into measures of 3
                grouped = beat_intervals[:6].reshape(2, 3)
                if np.std(grouped[0]) < 0.05 and np.std(grouped[1]) < 0.05:
                    return "3/4"
            
            # Default
            return "4/4"
    
    def _estimate_complexity(self, y: np.ndarray, sr: int, tempo: float) -> str:
        """Estimate playing complexity."""
        # Note density
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        onset_frames = librosa.onset.onset_detect(
            onset_envelope=onset_env, sr=sr, backtrack=False
        )
        notes_per_second = len(onset_frames) / (len(y) / sr)
        
        # Spectral complexity
        spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
        spectral_variance = np.var(spectral_centroid)
        
        # Tempo-based adjustment
        tempo_factor = tempo / 120.0
        
        # Combined score
        complexity_score = notes_per_second * tempo_factor + (spectral_variance / 1000000)
        
        if complexity_score < 3:
            return 'simple'
        elif complexity_score < 6:
            return 'moderate'
        else:
            return 'complex'
    
    def _detect_instruments(self, y: np.ndarray, sr: int) -> List[str]:
        """Basic instrument detection using spectral features."""
        instruments = []
        
        # Spectral features
        spectral_centroid = np.mean(librosa.feature.spectral_centroid(y=y, sr=sr))
        spectral_rolloff = np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr))
        zcr = np.mean(librosa.feature.zero_crossing_rate(y))
        
        # RMS energy in different frequency bands
        stft = librosa.stft(y)
        freqs = librosa.fft_frequencies(sr=sr)
        
        # Define frequency bands
        bass_mask = (freqs >= 50) & (freqs <= 250)
        mid_mask = (freqs >= 250) & (freqs <= 2000)
        high_mask = (freqs >= 2000) & (freqs <= 8000)
        
        bass_energy = np.mean(np.abs(stft[bass_mask, :]))
        mid_energy = np.mean(np.abs(stft[mid_mask, :]))
        high_energy = np.mean(np.abs(stft[high_mask, :]))
        
        # Heuristic detection
        if bass_energy > mid_energy * 0.8:
            instruments.append('bass')
        
        if mid_energy > bass_energy * 0.5 and spectral_centroid < 3000:
            instruments.append('guitar')
        
        if zcr > 0.1 and high_energy > mid_energy * 0.3:
            instruments.append('drums')
        
        if spectral_centroid > 1500 and spectral_centroid < 4000:
            if 'guitar' not in instruments:
                instruments.append('guitar')
        
        # Default to guitar if nothing detected
        if not instruments:
            instruments = ['guitar']
        
        return instruments
    
    def _post_process_notes(self, notes: List[Dict]) -> List[Dict]:
        """Post-process detected notes for better accuracy."""
        if not notes:
            return notes
        
        # Sort by start time
        notes.sort(key=lambda x: x['start_time'])
        
        # Merge very close notes
        merged_notes = []
        for note in notes:
            if merged_notes and abs(note['start_time'] - merged_notes[-1]['end_time']) < 0.01:
                # Merge with previous note if very close
                if abs(note['midi_note'] - merged_notes[-1]['midi_note']) <= 1:
                    merged_notes[-1]['end_time'] = note['end_time']
                    continue
            merged_notes.append(note)
        
        # Filter out very short notes (likely noise)
        filtered_notes = [
            note for note in merged_notes
            if note['end_time'] - note['start_time'] > 0.05  # 50ms minimum
        ]
        
        return filtered_notes