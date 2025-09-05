"""
Advanced ML Pipeline for audio transcription with source separation, pitch detection, and Whisper AI.
"""
import os
import numpy as np
import librosa
import torch
import logging
from typing import Dict, List, Optional, Tuple
import tempfile
import gc
from ..utils.json_utils import clean_analysis_result
import soundfile as sf
from django.conf import settings

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

# Import Whisper service and Multi-track service
from .whisper_service import WhisperService
from .multi_track_service import MultiTrackService

from scipy.signal import find_peaks
import music21

logger = logging.getLogger(__name__)


class MLPipeline:
    """
    Comprehensive ML pipeline for guitar transcription.
    Integrates multiple models for source separation, pitch detection, and analysis.
    """
    
    def __init__(self, use_gpu=False, demucs_model='htdemucs', basic_pitch_model='default', use_whisper=None, enable_multitrack=True):
        self.use_gpu = use_gpu and torch.cuda.is_available()
        self.device = torch.device('cuda' if self.use_gpu else 'cpu')
        self.demucs_model_name = demucs_model
        self.basic_pitch_model = basic_pitch_model
        self.enable_multitrack = enable_multitrack
        
        # Load models lazily
        self.demucs_model = None
        self.basic_pitch_loaded = False
        
        # Initialize Whisper if enabled
        self.use_whisper = use_whisper if use_whisper is not None else getattr(settings, 'USE_WHISPER', False)
        self.whisper_service = None
        if self.use_whisper and getattr(settings, 'OPENAI_API_KEY', ''):
            try:
                self.whisper_service = WhisperService(
                    api_key=settings.OPENAI_API_KEY
                )
                logger.info("Whisper AI service initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Whisper service: {str(e)}")
                self.whisper_service = None
        
        # Initialize Multi-track service
        self.multi_track_service = None
        if self.enable_multitrack:
            try:
                self.multi_track_service = MultiTrackService(
                    model_name=self.demucs_model_name,
                    use_gpu=self.use_gpu
                )
                logger.info("Multi-track service initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize multi-track service: {str(e)}")
                self.multi_track_service = None
        
        logger.info(f"ML Pipeline initialized. GPU: {self.use_gpu}, Device: {self.device}, Whisper: {self.whisper_service is not None}, Multi-track: {self.multi_track_service is not None}")
    
    def analyze_audio(self, audio_path: str) -> Dict:
        """
        Comprehensive audio analysis including tempo, key, complexity, and instruments.
        Enhanced with Whisper AI when available.
        """
        # Load audio with reduced sample rate to save memory
        y, sr = librosa.load(audio_path, sr=22050)
        
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
        
        result = {
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
        
        # Enhance with Whisper analysis if available
        if self.whisper_service:
            try:
                whisper_analysis = self.whisper_service.analyze_music(audio_path)
                # Ensure the whisper analysis is JSON serializable
                from ..utils.json_utils import ensure_json_serializable
                result['whisper_analysis'] = ensure_json_serializable(whisper_analysis)
                
                # Merge Whisper-detected instruments
                whisper_instruments = whisper_analysis.get('musical_elements', {}).get('instruments', [])
                for inst in whisper_instruments:
                    if inst not in result['instruments']:
                        result['instruments'].append(inst)
                
                # Clean up whisper analysis memory
                del whisper_analysis
                gc.collect()
                        
                logger.info("Audio analysis enhanced with Whisper AI")
            except Exception as e:
                logger.warning(f"Whisper analysis failed, continuing with traditional methods: {str(e)}")
        
        # Clean up audio data from memory
        del y
        gc.collect()
        
        return clean_analysis_result(result)
    
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
    
    def transcribe(self, audio_path: str, context: Optional[Dict] = None) -> Dict:
        """
        Transcribe audio to MIDI notes using multiple methods.
        Primary: basic-pitch (polyphonic) enhanced with Whisper
        Fallback: crepe (monophonic) or librosa
        """
        notes = []
        midi_data = {}
        chord_data = None
        
        # Try Whisper chord detection first if available
        if self.whisper_service and settings.WHISPER_ENABLE_CHORD_DETECTION:
            try:
                # Use context if provided (from analyze_audio)
                if context:
                    whisper_result = self.whisper_service.enhance_transcription_with_context(
                        audio_path, context
                    )
                else:
                    whisper_result = self.whisper_service.detect_chords_and_notes(audio_path)
                    
                chord_data = whisper_result
                midi_data['whisper_chords'] = chord_data
                logger.info(f"Whisper detected {len(chord_data.get('chords', []))} chords")
                
            except Exception as e:
                logger.warning(f"Whisper chord detection failed: {str(e)}")
        
        # Try basic-pitch first (best for polyphonic)
        if basic_pitch:
            try:
                notes, pitch_midi_data = self._transcribe_basic_pitch(audio_path)
                midi_data.update(pitch_midi_data)
                logger.info(f"Basic-pitch transcription complete: {len(notes)} notes detected")
            except Exception as e:
                logger.warning(f"Basic-pitch failed: {str(e)}, falling back to alternatives")
        
        # Fallback to crepe for monophonic
        if not notes and crepe:
            try:
                notes, crepe_midi_data = self._transcribe_crepe(audio_path)
                midi_data.update(crepe_midi_data)
                logger.info(f"CREPE transcription complete: {len(notes)} notes detected")
            except Exception as e:
                logger.warning(f"CREPE failed: {str(e)}, falling back to librosa")
        
        # Final fallback to librosa
        if not notes:
            notes, librosa_midi_data = self._transcribe_librosa(audio_path)
            midi_data.update(librosa_midi_data)
            logger.info(f"Librosa transcription complete: {len(notes)} notes detected")
        
        # Enhance notes with Whisper chord context if available
        if chord_data and chord_data.get('chords'):
            notes = self._enhance_notes_with_chords(notes, chord_data['chords'])
        
        # Post-process notes
        notes = self._post_process_notes(notes)
        
        return {
            'notes': notes,
            'midi_data': midi_data,
            'chord_data': chord_data
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
        y, sr = librosa.load(audio_path, sr=22050)
        
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
    
    def _enhance_notes_with_chords(self, notes: List[Dict], chords: List[Dict]) -> List[Dict]:
        """
        Enhance detected notes with Whisper chord information.
        Adds chord context and improves note confidence.
        """
        if not notes or not chords:
            return notes
            
        # Sort chords by time
        chords = sorted(chords, key=lambda c: c.get('start_time', 0))
        
        # For each note, find the corresponding chord
        for note in notes:
            note_time = note['start_time']
            
            # Find active chord at this time
            active_chord = None
            for chord in chords:
                if chord['start_time'] <= note_time <= chord.get('end_time', chord['start_time'] + 1):
                    active_chord = chord
                    break
                    
            if active_chord:
                # Add chord context to note
                note['chord_context'] = active_chord['chord']
                note['chord_confidence'] = active_chord.get('confidence', 0.5)
                
                # Boost confidence if note matches chord
                chord_notes = self._get_chord_notes(active_chord['chord'])
                if chord_notes:
                    note_pitch = note['midi_note'] % 12  # Get pitch class
                    if note_pitch in chord_notes:
                        note['confidence'] = min(1.0, note.get('confidence', 0.5) * 1.2)
                        note['in_chord'] = True
                        
        return notes
        
    def _get_chord_notes(self, chord_name: str) -> List[int]:
        """
        Get MIDI pitch classes for a chord name.
        Returns list of pitch classes (0-11).
        """
        # Basic chord mappings (pitch classes)
        chord_map = {
            'C': [0, 4, 7],      # C major
            'Cm': [0, 3, 7],     # C minor
            'C7': [0, 4, 7, 10], # C7
            'D': [2, 6, 9],      # D major
            'Dm': [2, 5, 9],     # D minor
            'D7': [2, 6, 9, 0],  # D7
            'E': [4, 8, 11],     # E major
            'Em': [4, 7, 11],    # E minor
            'E7': [4, 8, 11, 2], # E7
            'F': [5, 9, 0],      # F major
            'Fm': [5, 8, 0],     # F minor
            'F7': [5, 9, 0, 3],  # F7
            'G': [7, 11, 2],     # G major
            'Gm': [7, 10, 2],    # G minor
            'G7': [7, 11, 2, 5], # G7
            'A': [9, 1, 4],      # A major
            'Am': [9, 0, 4],     # A minor
            'A7': [9, 1, 4, 7],  # A7
            'B': [11, 3, 6],     # B major
            'Bm': [11, 2, 6],    # B minor
            'B7': [11, 3, 6, 9], # B7
        }
        
        # Try to find chord in map
        chord_upper = chord_name.upper()
        for key, notes in chord_map.items():
            if chord_upper.startswith(key):
                return notes
                
        return []
    
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
    
    def process_multitrack_transcription(self, transcription_obj) -> Dict:
        """
        Process a transcription with multi-track separation and individual track analysis.
        
        Args:
            transcription_obj: Transcription model instance
            
        Returns:
            Dict with multi-track processing results
        """
        if not self.multi_track_service:
            logger.warning("Multi-track service not available, falling back to single-track processing")
            return {'tracks': [], 'fallback': True}
        
        try:
            logger.info(f"Starting multi-track processing for: {transcription_obj.filename}")
            
            # Step 1: Separate audio into tracks
            tracks = self.multi_track_service.process_transcription(transcription_obj)
            
            # Step 2: Process each track individually
            processed_tracks = []
            for track in tracks:
                if not track.separated_audio:
                    continue
                    
                try:
                    # Skip processing for certain track types
                    if track.track_type in ['original', 'vocals']:
                        processed_tracks.append({
                            'track': track,
                            'processed': False,
                            'reason': f'Skipping {track.track_type} track'
                        })
                        continue
                    
                    logger.info(f"Processing track: {track.display_name}")
                    
                    # Analyze track audio
                    track_analysis = self.analyze_audio(track.separated_audio.path)
                    
                    # Transcribe track if it's a melodic instrument
                    track_transcription = None
                    if track.track_type in ['other', 'bass'] or track.instrument_type in ['electric_guitar', 'acoustic_guitar', 'bass']:
                        track_transcription = self.transcribe(
                            track.separated_audio.path,
                            context={
                                'tempo': track_analysis.get('tempo'),
                                'key': track_analysis.get('key'),
                                'instrument': track.instrument_type
                            }
                        )
                    
                    # Update track with analysis results
                    if track_transcription:
                        track.midi_data = track_transcription['midi_data']
                        track.guitar_notes = track_transcription['notes']
                        if 'chord_data' in track_transcription and track_transcription['chord_data']:
                            track.chord_progressions = track_transcription['chord_data']
                    
                    track.is_processed = True
                    track.save()
                    
                    processed_tracks.append({
                        'track': track,
                        'analysis': track_analysis,
                        'transcription': track_transcription,
                        'processed': True
                    })
                    
                    logger.info(f"Successfully processed track: {track.display_name}")
                    
                except Exception as e:
                    logger.error(f"Failed to process track {track.display_name}: {str(e)}")
                    track.processing_error = str(e)
                    track.save()
                    
                    processed_tracks.append({
                        'track': track,
                        'processed': False,
                        'error': str(e)
                    })
            
            # Step 3: Generate track variants for guitar tracks
            self._generate_track_variants(processed_tracks)
            
            # Step 4: Update overall transcription with multi-track info
            self._update_transcription_with_tracks(transcription_obj, tracks, processed_tracks)
            
            logger.info(f"Multi-track processing completed. Processed {len(processed_tracks)} tracks.")
            
            return {
                'tracks': processed_tracks,
                'track_count': len(tracks),
                'processed_count': len([t for t in processed_tracks if t['processed']]),
                'fallback': False
            }
            
        except Exception as e:
            logger.error(f"Multi-track processing failed: {str(e)}")
            raise
    
    def _generate_track_variants(self, processed_tracks: List[Dict]) -> None:
        """Generate fingering variants for guitar tracks."""
        from .variant_generator import VariantGenerator
        
        for track_info in processed_tracks:
            if not track_info['processed']:
                continue
                
            track = track_info['track']
            if track.instrument_type not in ['electric_guitar', 'acoustic_guitar']:
                continue
                
            if not track.guitar_notes:
                continue
                
            try:
                logger.info(f"Generating variants for track: {track.display_name}")
                
                # Create variant generator for this track
                variant_gen = VariantGenerator(track.transcription)
                
                # Generate variants using track-specific data
                track_variants = variant_gen.generate_track_variants(
                    track, 
                    track.guitar_notes
                )
                
                logger.info(f"Generated {len(track_variants)} variants for {track.display_name}")
                
            except Exception as e:
                logger.error(f"Failed to generate variants for track {track.display_name}: {str(e)}")
    
    def _update_transcription_with_tracks(self, transcription_obj, tracks: List, processed_tracks: List[Dict]) -> None:
        """Update the main transcription object with multi-track information."""
        try:
            # Update detected instruments with track information
            track_instruments = []
            for track in tracks:
                if track.instrument_type and track.instrument_type != 'other':
                    track_instruments.append(track.instrument_type)
            
            if track_instruments:
                # Combine with existing instruments, avoiding duplicates
                existing = transcription_obj.detected_instruments or []
                combined = list(set(existing + track_instruments))
                transcription_obj.detected_instruments = combined
            
            # Update complexity based on track count and content
            guitar_tracks = [t for t in tracks if t.instrument_type in ['electric_guitar', 'acoustic_guitar']]
            if len(guitar_tracks) > 1:
                # Multiple guitar tracks = more complex
                if transcription_obj.complexity == 'simple':
                    transcription_obj.complexity = 'moderate'
                elif transcription_obj.complexity == 'moderate':
                    transcription_obj.complexity = 'complex'
            
            transcription_obj.save()
            logger.info(f"Updated transcription with {len(tracks)} tracks")
            
        except Exception as e:
            logger.error(f"Failed to update transcription with track info: {str(e)}")
    
    def get_pipeline_info(self) -> Dict:
        """Get information about the pipeline configuration."""
        return {
            'gpu_enabled': self.use_gpu,
            'device': str(self.device),
            'whisper_enabled': self.whisper_service is not None,
            'multitrack_enabled': self.multi_track_service is not None,
            'demucs_model': self.demucs_model_name,
            'basic_pitch_available': basic_pitch is not None,
            'crepe_available': crepe is not None,
            'demucs_available': demucs is not None
        }