"""
MT3 (Multi-Task Multitrack Music Transcription) Service
Google's state-of-the-art transformer model for multi-instrument transcription
"""
import asyncio
import logging
import tempfile
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass 
class MT3TranscriptionResult:
    """Results from MT3 transcription"""
    tracks: Dict[str, List[Dict]]  # instrument -> notes
    tempo: float
    time_signature: str
    key_signature: str
    confidence_scores: Dict[str, float]  # per instrument
    total_confidence: float
    processing_time: float
    model_version: str


class MT3Service:
    """Service for Google's MT3 multi-track transcription"""
    
    def __init__(self):
        self.model = None
        self.model_loaded = False
        self.supported_instruments = [
            'piano', 'guitar', 'bass', 'drums', 'vocals', 'strings', 'brass', 'woodwinds'
        ]
    
    def _ensure_model_loaded(self):
        """Lazy load MT3 model"""
        if not self.model_loaded:
            try:
                import mt3
                import note_seq
                from mt3 import models, inference
                
                self.mt3 = mt3
                self.note_seq = note_seq
                self.inference = inference
                
                # Load pre-trained model
                self.model = models.load_model('mt3')
                self.model_loaded = True
                
                logger.info("MT3 model loaded successfully")
            except ImportError as e:
                logger.error(f"MT3 not available: {e}")
                raise ImportError("Install MT3: pip install mt3 note-seq")
            except Exception as e:
                logger.error(f"Failed to load MT3 model: {e}")
                raise
    
    async def transcribe_multitrack(self, audio_path: str, 
                                   max_length: float = 300.0,
                                   temperature: float = 0.0) -> MT3TranscriptionResult:
        """
        Transcribe audio using MT3 for multi-track output
        
        Args:
            audio_path: Path to audio file
            max_length: Maximum audio length in seconds
            temperature: Sampling temperature for transcription
        
        Returns:
            MT3TranscriptionResult with per-instrument transcriptions
        """
        logger.info(f"Starting MT3 multi-track transcription: {audio_path}")
        start_time = asyncio.get_event_loop().time()
        
        self._ensure_model_loaded()
        
        try:
            # Load and preprocess audio
            audio_data = await self._load_audio(audio_path, max_length)
            
            # Run MT3 inference
            transcription_result = await asyncio.to_thread(
                self._run_mt3_inference,
                audio_data,
                temperature
            )
            
            # Process results into structured format
            tracks = await self._process_mt3_output(transcription_result)
            
            # Calculate confidence scores
            confidence_scores = self._calculate_confidence_scores(tracks, transcription_result)
            
            # Extract musical metadata
            tempo = self._extract_tempo(transcription_result)
            time_signature = self._extract_time_signature(transcription_result)
            key_signature = self._extract_key_signature(transcription_result)
            
            processing_time = asyncio.get_event_loop().time() - start_time
            
            result = MT3TranscriptionResult(
                tracks=tracks,
                tempo=tempo,
                time_signature=time_signature,
                key_signature=key_signature,
                confidence_scores=confidence_scores,
                total_confidence=np.mean(list(confidence_scores.values())) if confidence_scores else 0.8,
                processing_time=processing_time,
                model_version="mt3_v1"
            )
            
            logger.info(f"MT3 transcription completed in {processing_time:.2f}s")
            logger.info(f"Detected instruments: {list(tracks.keys())}")
            
            return result
            
        except Exception as e:
            logger.error(f"MT3 transcription failed: {e}")
            raise
    
    async def _load_audio(self, audio_path: str, max_length: float) -> np.ndarray:
        """Load and preprocess audio for MT3"""
        import librosa
        
        # Load audio with MT3's expected sample rate (16kHz)
        audio, sr = await asyncio.to_thread(
            librosa.load, 
            audio_path, 
            sr=16000,  # MT3 expects 16kHz
            mono=True,
            duration=max_length
        )
        
        logger.info(f"Loaded audio: {len(audio)/sr:.2f}s at {sr}Hz")
        return audio
    
    def _run_mt3_inference(self, audio_data: np.ndarray, temperature: float) -> Any:
        """Run MT3 model inference"""
        # Convert audio to note sequence format
        audio_sample_rate = 16000  # MT3's expected rate
        
        # Run transcription
        transcription = self.inference.infer(
            self.model,
            audio_data,
            sample_rate=audio_sample_rate,
            temperature=temperature
        )
        
        return transcription
    
    async def _process_mt3_output(self, transcription_result: Any) -> Dict[str, List[Dict]]:
        """Process MT3 output into structured track format"""
        tracks = {}
        
        # MT3 outputs notes with instrument programs
        for note in transcription_result.notes:
            # Map MIDI program to instrument name
            instrument = self._program_to_instrument(note.program)
            
            if instrument not in tracks:
                tracks[instrument] = []
            
            tracks[instrument].append({
                'midi_note': note.pitch,
                'start_time': note.start_time,
                'end_time': note.end_time,
                'duration': note.end_time - note.start_time,
                'velocity': note.velocity,
                'program': note.program,
                'confidence': getattr(note, 'confidence', 0.9)
            })
        
        # Sort notes by start time for each instrument
        for instrument in tracks:
            tracks[instrument].sort(key=lambda x: x['start_time'])
        
        logger.info(f"Processed MT3 output: {len(tracks)} instruments detected")
        return tracks
    
    def _program_to_instrument(self, program: int) -> str:
        """Map MIDI program number to instrument name"""
        # General MIDI instrument mapping (simplified)
        program_map = {
            # Guitar family (24-31)
            **{i: 'guitar' for i in range(24, 32)},
            
            # Bass family (32-39) 
            **{i: 'bass' for i in range(32, 40)},
            
            # Piano family (0-7)
            **{i: 'piano' for i in range(0, 8)},
            
            # Strings (40-55)
            **{i: 'strings' for i in range(40, 56)},
            
            # Brass (56-71)
            **{i: 'brass' for i in range(56, 72)},
            
            # Woodwinds (64-79)
            **{i: 'woodwinds' for i in range(64, 80)},
            
            # Drums (channel 9, but program can vary)
            128: 'drums'  # Special case for drums
        }
        
        return program_map.get(program, 'other')
    
    def _calculate_confidence_scores(self, tracks: Dict, transcription_result: Any) -> Dict[str, float]:
        """Calculate confidence scores per instrument"""
        confidence_scores = {}
        
        for instrument, notes in tracks.items():
            if notes:
                # Average confidence of all notes for this instrument
                confidences = [note.get('confidence', 0.9) for note in notes]
                confidence_scores[instrument] = float(np.mean(confidences))
            else:
                confidence_scores[instrument] = 0.0
        
        return confidence_scores
    
    def _extract_tempo(self, transcription_result: Any) -> float:
        """Extract tempo from MT3 result"""
        try:
            # MT3 includes tempo markings
            for tempo_change in transcription_result.tempo_changes:
                if tempo_change.time == 0:  # Initial tempo
                    return tempo_change.qpm  # Quarter notes per minute
            
            # Fallback: estimate from note timing
            return self._estimate_tempo_from_notes(transcription_result.notes)
            
        except Exception as e:
            logger.warning(f"Could not extract tempo: {e}")
            return 120.0  # Default tempo
    
    def _extract_time_signature(self, transcription_result: Any) -> str:
        """Extract time signature from MT3 result"""
        try:
            for time_sig in transcription_result.time_signatures:
                if time_sig.time == 0:  # Initial time signature
                    return f"{time_sig.numerator}/{time_sig.denominator}"
        except Exception:
            pass
        
        return "4/4"  # Default
    
    def _extract_key_signature(self, transcription_result: Any) -> str:
        """Extract key signature from MT3 result"""
        try:
            for key_sig in transcription_result.key_signatures:
                if key_sig.time == 0:  # Initial key
                    return self._key_signature_to_string(key_sig)
        except Exception:
            pass
        
        return "C Major"  # Default
    
    def _key_signature_to_string(self, key_sig: Any) -> str:
        """Convert key signature object to string"""
        # Simplified key signature conversion
        key_map = {
            0: "C Major", 1: "G Major", 2: "D Major", 3: "A Major",
            4: "E Major", 5: "B Major", 6: "F# Major", 7: "C# Major",
            -1: "F Major", -2: "Bb Major", -3: "Eb Major", -4: "Ab Major",
            -5: "Db Major", -6: "Gb Major", -7: "Cb Major"
        }
        return key_map.get(key_sig.key, "C Major")
    
    def _estimate_tempo_from_notes(self, notes: List) -> float:
        """Estimate tempo from note timing patterns"""
        if len(notes) < 4:
            return 120.0
        
        # Calculate inter-onset intervals
        onset_times = [note.start_time for note in notes[:20]]  # First 20 notes
        onset_times.sort()
        
        intervals = []
        for i in range(1, len(onset_times)):
            interval = onset_times[i] - onset_times[i-1]
            if 0.1 < interval < 2.0:  # Reasonable note intervals
                intervals.append(interval)
        
        if not intervals:
            return 120.0
        
        # Find most common interval (beat)
        avg_interval = np.median(intervals)
        estimated_bpm = 60.0 / avg_interval
        
        # Clamp to reasonable range
        return max(60.0, min(200.0, estimated_bpm))
    
    async def get_supported_instruments(self) -> List[str]:
        """Get list of instruments MT3 can transcribe"""
        return self.supported_instruments.copy()
    
    def cleanup_resources(self):
        """Clean up model resources"""
        if self.model_loaded:
            del self.model
            self.model = None
            self.model_loaded = False
            logger.info("MT3 model resources cleaned up")


# Global service instance
mt3_service = MT3Service()


# Convenience functions
async def transcribe_with_mt3(audio_path: str, **kwargs) -> MT3TranscriptionResult:
    """Convenience function for MT3 transcription"""
    return await mt3_service.transcribe_multitrack(audio_path, **kwargs)


def get_mt3_service() -> MT3Service:
    """Get the global MT3 service instance"""
    return mt3_service
