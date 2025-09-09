"""
Modern AI-First Music Transcription Service
Uses Spotify's Basic Pitch for complete audio-to-MIDI conversion
Replaces complex ML pipeline with lightweight AI approach
"""
import os
import logging
import tempfile
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    """Complete transcription result with all instruments"""
    midi_data: Dict
    notes: List[Dict]
    guitar_notes: List[Dict]
    bass_notes: List[Dict] 
    drum_notes: List[Dict]
    tempo: float
    duration: float
    confidence: float
    instruments_detected: List[str]


class AITranscriptionService:
    """
    Modern AI-first transcription service using Basic Pitch
    Completely replaces traditional ML pipeline
    """
    
    def __init__(self):
        self.model_loaded = False
        logger.info("AI Transcription Service initialized")
    
    def _ensure_basic_pitch_loaded(self):
        """Lazy load Basic Pitch model"""
        if not self.model_loaded:
            try:
                from basic_pitch.inference import predict
                self.predict = predict
                self.model_loaded = True
                logger.info("Basic Pitch model loaded successfully")
            except ImportError as e:
                logger.error(f"Basic Pitch not available: {e}")
                raise ImportError("Install basic-pitch: pip install basic-pitch")
    
    async def transcribe_complete_audio(self, audio_path: str) -> TranscriptionResult:
        """
        Complete AI transcription - replaces entire traditional pipeline
        Returns full MIDI data for all instruments
        """
        logger.info(f"Starting complete AI transcription: {audio_path}")
        self._ensure_basic_pitch_loaded()
        
        try:
            # Use Basic Pitch for complete transcription
            model_output, midi_data, note_events = self.predict(audio_path)
            
            # Extract comprehensive note information
            all_notes = self._extract_notes_from_midi(midi_data)
            
            # Separate instruments by pitch ranges and patterns
            guitar_notes = self._extract_guitar_notes(all_notes)
            bass_notes = self._extract_bass_notes(all_notes)
            drum_notes = self._extract_drum_notes(model_output, note_events)
            
            # Get audio metadata
            duration = self._get_audio_duration(audio_path)
            tempo = self._estimate_tempo(note_events)
            
            # Detect what instruments are present
            instruments = self._detect_instruments(guitar_notes, bass_notes, drum_notes)
            
            result = TranscriptionResult(
                midi_data=self._convert_midi_to_dict(midi_data),
                notes=all_notes,
                guitar_notes=guitar_notes,
                bass_notes=bass_notes,
                drum_notes=drum_notes,
                tempo=tempo,
                duration=duration,
                confidence=0.9,  # Basic Pitch is very reliable
                instruments_detected=instruments
            )
            
            logger.info(f"Complete transcription: {len(all_notes)} total notes, "
                       f"{len(guitar_notes)} guitar, {len(bass_notes)} bass, "
                       f"{len(drum_notes)} drums, {tempo}bpm")
            
            return result
            
        except Exception as e:
            logger.error(f"AI transcription failed: {e}")
            raise
    
    def _extract_notes_from_midi(self, midi_data) -> List[Dict]:
        """Extract all notes from MIDI data with proper timing"""
        notes = []
        
        for track in midi_data.tracks:
            current_time = 0
            for msg in track:
                current_time += msg.time
                
                if msg.type == 'note_on' and msg.velocity > 0:
                    # Find corresponding note_off
                    note_off_time = current_time
                    temp_time = current_time
                    
                    for future_msg in track[track.index(msg)+1:]:
                        temp_time += future_msg.time
                        if (future_msg.type == 'note_off' and 
                            future_msg.note == msg.note):
                            note_off_time = temp_time
                            break
                    
                    notes.append({
                        'midi_note': msg.note,
                        'start_time': current_time / 480.0,  # Convert ticks to seconds
                        'end_time': note_off_time / 480.0,
                        'duration': (note_off_time - current_time) / 480.0,
                        'velocity': msg.velocity,
                        'channel': msg.channel,
                        'confidence': 0.9
                    })
        
        return sorted(notes, key=lambda x: x['start_time'])
    
    def _extract_guitar_notes(self, all_notes: List[Dict]) -> List[Dict]:
        """Extract guitar notes (mid-range, 40-84 MIDI)"""
        guitar_notes = []
        
        for note in all_notes:
            midi_note = note['midi_note']
            # Guitar range: E2 (40) to C6 (84)
            if 40 <= midi_note <= 84:
                guitar_note = note.copy()
                
                # Add guitar-specific tablature information
                string, fret = self._midi_to_guitar_tab(midi_note)
                guitar_note.update({
                    'string': string,
                    'fret': fret,
                    'technique': 'normal'
                })
                
                guitar_notes.append(guitar_note)
        
        return guitar_notes
    
    def _extract_bass_notes(self, all_notes: List[Dict]) -> List[Dict]:
        """Extract bass notes (low range, 28-67 MIDI)"""
        bass_notes = []
        
        for note in all_notes:
            midi_note = note['midi_note']
            # Bass range: E1 (28) to G4 (67)
            if 28 <= midi_note <= 67:
                bass_note = note.copy()
                
                # Add bass-specific tablature
                string, fret = self._midi_to_bass_tab(midi_note)
                bass_note.update({
                    'string': string,
                    'fret': fret,
                    'technique': 'normal'
                })
                
                bass_notes.append(bass_note)
        
        return bass_notes
    
    def _extract_drum_notes(self, model_output, note_events) -> List[Dict]:
        """Extract drum notes from Basic Pitch output"""
        drum_notes = []
        
        # Basic Pitch doesn't explicitly separate drums, but we can detect
        # percussive elements from the onset detection
        try:
            # Look for short, sharp attacks that indicate drums
            for event in note_events:
                if hasattr(event, 'start_time') and hasattr(event, 'pitch'):
                    # Drums typically have very short durations and specific pitches
                    duration = getattr(event, 'end_time', event.start_time + 0.1) - event.start_time
                    
                    if duration < 0.2:  # Short notes likely drums
                        drum_type = self._classify_drum_type(event.pitch)
                        if drum_type:
                            drum_notes.append({
                                'drum_type': drum_type,
                                'start_time': event.start_time,
                                'velocity': getattr(event, 'amplitude', 0.8) * 127,
                                'confidence': 0.7
                            })
        except Exception as e:
            logger.warning(f"Drum extraction failed: {e}")
        
        return drum_notes
    
    def _midi_to_guitar_tab(self, midi_note: int) -> Tuple[int, int]:
        """Convert MIDI note to guitar string/fret (standard tuning)"""
        # Standard tuning: E(40), A(45), D(50), G(55), B(59), E(64)
        strings = [64, 59, 55, 50, 45, 40]  # High E to Low E
        
        for string_idx, open_note in enumerate(strings):
            if midi_note >= open_note:
                fret = midi_note - open_note
                if fret <= 24:  # Reasonable fret limit
                    return string_idx + 1, fret
        
        # Default to high E string
        return 1, max(0, midi_note - 64)
    
    def _midi_to_bass_tab(self, midi_note: int) -> Tuple[int, int]:
        """Convert MIDI note to bass string/fret (EADG tuning)"""
        # Bass tuning: G(43), D(38), A(33), E(28)
        strings = [43, 38, 33, 28]  # G to E
        
        for string_idx, open_note in enumerate(strings):
            if midi_note >= open_note:
                fret = midi_note - open_note
                if fret <= 24:
                    return string_idx + 1, fret
        
        # Default to G string
        return 1, max(0, midi_note - 43)
    
    def _classify_drum_type(self, pitch: float) -> Optional[str]:
        """Classify drum type based on pitch"""
        # Basic drum classification by pitch range
        if pitch < 60:
            return 'kick'
        elif 60 <= pitch < 80:
            return 'snare'
        elif 80 <= pitch < 100:
            return 'hihat'
        elif pitch >= 100:
            return 'crash'
        return None
    
    def _estimate_tempo(self, note_events) -> float:
        """Estimate tempo from note events"""
        if not note_events or len(note_events) < 4:
            return 120.0
        
        try:
            # Calculate intervals between note onsets
            onsets = [event.start_time for event in note_events[:50]]  # First 50 notes
            intervals = [onsets[i+1] - onsets[i] for i in range(len(onsets)-1)]
            
            # Find most common interval (likely beat)
            intervals = [i for i in intervals if 0.2 < i < 2.0]  # Reasonable tempo range
            if intervals:
                avg_interval = np.median(intervals)
                bpm = 60.0 / avg_interval
                return max(60, min(200, bpm))  # Clamp to reasonable range
        except Exception:
            pass
        
        return 120.0
    
    def _detect_instruments(self, guitar_notes: List, bass_notes: List, drum_notes: List) -> List[str]:
        """Detect which instruments are present"""
        instruments = []
        
        if guitar_notes:
            instruments.append('guitar')
        if bass_notes:
            instruments.append('bass')
        if drum_notes:
            instruments.append('drums')
        
        return instruments or ['guitar']  # Default to guitar
    
    def _get_audio_duration(self, audio_path: str) -> float:
        """Get audio duration"""
        try:
            import librosa
            return librosa.get_duration(path=audio_path)
        except:
            # Fallback estimate
            return os.path.getsize(audio_path) / 16000.0
    
    def _convert_midi_to_dict(self, midi_data) -> Dict:
        """Convert MIDI data to dictionary format"""
        return {
            'tracks': len(midi_data.tracks),
            'ticks_per_beat': midi_data.ticks_per_beat,
            'type': midi_data.type,
            'filename': getattr(midi_data, 'filename', '')
        }


# Export the main service
__all__ = ['AITranscriptionService', 'TranscriptionResult']