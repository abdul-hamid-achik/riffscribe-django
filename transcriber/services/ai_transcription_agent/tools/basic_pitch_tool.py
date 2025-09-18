"""
Basic Pitch Transcription Tool
Handles actual audio-to-MIDI conversion using Spotify's Basic Pitch
"""
import asyncio
import logging
import tempfile
from typing import Dict, List, Optional
import numpy as np

logger = logging.getLogger(__name__)


class BasicPitchTool:
    """Tool for Basic Pitch audio-to-MIDI transcription"""
    
    def __init__(self):
        self.model = None
        self.model_loaded = False
    
    def _ensure_model_loaded(self):
        """Lazy load Basic Pitch model"""
        if not self.model_loaded:
            try:
                from basic_pitch import ICASSP_2022_MODEL_PATH
                from basic_pitch.inference import predict
                self.predict = predict
                self.model_path = ICASSP_2022_MODEL_PATH
                self.model_loaded = True
                logger.info("Basic Pitch model loaded successfully")
            except ImportError as e:
                logger.error(f"Basic Pitch not available: {e}")
                raise ImportError("Install basic-pitch: pip install basic-pitch")
    
    async def transcribe(self, audio_path: str, onset_threshold: float = 0.5, 
                        frame_threshold: float = 0.3, minimum_note_length: float = 58,
                        minimum_frequency: Optional[float] = None,
                        maximum_frequency: Optional[float] = None) -> Dict:
        """
        Transcribe audio using Basic Pitch
        
        Args:
            audio_path: Path to audio file
            onset_threshold: Threshold for note onset detection (0-1)
            frame_threshold: Threshold for frame activation (0-1)
            minimum_note_length: Minimum note length in milliseconds
            minimum_frequency: Minimum frequency to consider (Hz)
            maximum_frequency: Maximum frequency to consider (Hz)
        
        Returns:
            Dictionary with transcription results
        """
        logger.info(f"Starting Basic Pitch transcription for: {audio_path}")
        self._ensure_model_loaded()
        
        try:
            # Run prediction
            model_output, midi_data, note_events = await asyncio.to_thread(
                self.predict,
                audio_path,
                self.model_path,
                onset_threshold=onset_threshold,
                frame_threshold=frame_threshold,
                minimum_note_length=minimum_note_length,
                minimum_frequency=minimum_frequency,
                maximum_frequency=maximum_frequency,
                melodia_trick=True,  # Improves single-instrument transcription
                debug_file=None
            )
            
            # Extract notes with proper timing and velocity
            notes = self._extract_notes_from_events(note_events)
            
            # Analyze pitch bends if present
            pitch_bends = self._extract_pitch_bends(model_output)
            
            # Get confidence metrics
            confidence = self._calculate_confidence(model_output, note_events)
            
            result = {
                'notes': notes,
                'midi_data': self._midi_to_dict(midi_data),
                'note_events': len(note_events),
                'confidence': confidence,
                'pitch_bends': pitch_bends,
                'model_version': 'ICASSP_2022'
            }
            
            logger.info(f"Basic Pitch transcription completed: {len(notes)} notes detected")
            return result
            
        except Exception as e:
            logger.error(f"Basic Pitch transcription failed: {e}")
            raise
    
    def _extract_notes_from_events(self, note_events) -> List[Dict]:
        """Extract structured note data from Basic Pitch note events"""
        notes = []
        
        for event in note_events:
            # Basic Pitch returns (start_time, end_time, pitch, velocity, confidence)
            note = {
                'start_time': float(event[0]),
                'end_time': float(event[1]),
                'midi_note': int(event[2]),
                'velocity': int(event[3] * 127) if len(event) > 3 else 80,
                'confidence': float(event[4]) if len(event) > 4 else 0.8,
                'duration': float(event[1] - event[0])
            }
            
            # Add frequency information
            note['frequency'] = self._midi_to_freq(note['midi_note'])
            
            notes.append(note)
        
        return sorted(notes, key=lambda x: x['start_time'])
    
    def _extract_pitch_bends(self, model_output) -> List[Dict]:
        """Extract pitch bend information from model output"""
        pitch_bends = []
        
        try:
            if hasattr(model_output, 'pitch_bends') and model_output.pitch_bends is not None:
                # Process pitch bend data
                for time, bend_value in enumerate(model_output.pitch_bends):
                    if abs(bend_value) > 0.1:  # Threshold for significant bends
                        pitch_bends.append({
                            'time': time * 0.01,  # Convert frame to time
                            'value': float(bend_value)
                        })
        except Exception as e:
            logger.debug(f"No pitch bends extracted: {e}")
        
        return pitch_bends
    
    def _calculate_confidence(self, model_output, note_events) -> float:
        """Calculate overall transcription confidence"""
        if not note_events:
            return 0.0
        
        try:
            # Calculate based on model activations and note density
            if hasattr(model_output, 'note_confidence'):
                confidences = [float(event[4]) if len(event) > 4 else 0.8 
                              for event in note_events]
                return float(np.mean(confidences))
            else:
                # Fallback confidence based on note density
                return min(0.9, 0.5 + (len(note_events) / 100) * 0.4)
        except:
            return 0.7  # Default confidence
    
    def _midi_to_dict(self, midi_data) -> Dict:
        """Convert MIDI data to dictionary"""
        try:
            return {
                'tracks': len(midi_data.tracks) if hasattr(midi_data, 'tracks') else 1,
                'ticks_per_beat': getattr(midi_data, 'ticks_per_beat', 480),
                'tempo': self._extract_tempo(midi_data)
            }
        except:
            return {'tracks': 1, 'ticks_per_beat': 480, 'tempo': 120}
    
    def _extract_tempo(self, midi_data) -> float:
        """Extract tempo from MIDI data"""
        try:
            for track in midi_data.tracks:
                for msg in track:
                    if msg.type == 'set_tempo':
                        # Convert microseconds per beat to BPM
                        return 60000000 / msg.tempo
        except:
            pass
        return 120.0  # Default tempo
    
    def _midi_to_freq(self, midi_note: int) -> float:
        """Convert MIDI note to frequency in Hz"""
        return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))
    
    async def transcribe_with_options(self, audio_path: str, 
                                      guitar_optimized: bool = True) -> Dict:
        """
        Transcribe with guitar-optimized settings
        
        Args:
            audio_path: Path to audio file
            guitar_optimized: Use settings optimized for guitar
        """
        if guitar_optimized:
            # Guitar-optimized parameters
            return await self.transcribe(
                audio_path,
                onset_threshold=0.4,  # More sensitive for guitar attacks
                frame_threshold=0.25,  # Lower threshold for sustained notes
                minimum_note_length=40,  # Shorter for fast playing
                minimum_frequency=82.41,  # E2 (lowest guitar note)
                maximum_frequency=1318.5  # E6 (24th fret high E)
            )
        else:
            # Default parameters
            return await self.transcribe(audio_path)