"""
CREPE Service - Advanced pitch detection with convolutional neural networks
Provides high-accuracy pitch estimation for music transcription
"""
import asyncio
import logging
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CREPEResult:
    """Results from CREPE pitch detection"""
    pitches: List[float]  # Pitch values in Hz
    confidences: List[float]  # Confidence scores (0-1)
    times: List[float]  # Time stamps
    notes: List[Dict]  # Converted to note format
    average_confidence: float
    processing_time: float


class CREPEService:
    """Service for CREPE pitch detection"""
    
    def __init__(self):
        self.model_loaded = False
        self.step_size = 10  # milliseconds between predictions
        self.model_capacity = 'full'  # 'tiny', 'small', 'medium', 'large', 'full'
    
    def _ensure_model_loaded(self):
        """Lazy load CREPE model"""
        if not self.model_loaded:
            try:
                import crepe
                self.crepe = crepe
                self.model_loaded = True
                logger.info(f"CREPE model loaded (capacity: {self.model_capacity})")
            except ImportError as e:
                logger.error(f"CREPE not available: {e}")
                raise ImportError("Install CREPE: pip install crepe tensorflow")
    
    async def detect_pitch(self, audio_path: str,
                          viterbi: bool = True,
                          center: bool = True,
                          confidence_threshold: float = 0.5) -> CREPEResult:
        """
        Detect pitch using CREPE
        
        Args:
            audio_path: Path to audio file
            viterbi: Use Viterbi smoothing for better continuity
            center: Center the audio
            confidence_threshold: Minimum confidence to include pitch
        
        Returns:
            CREPEResult with pitch detection data
        """
        logger.info(f"Starting CREPE pitch detection: {audio_path}")
        start_time = asyncio.get_event_loop().time()
        
        self._ensure_model_loaded()
        
        try:
            # Run CREPE prediction
            time_stamps, pitches, confidence, activation = await asyncio.to_thread(
                self.crepe.predict,
                audio_path,
                step_size=self.step_size,
                viterbi=viterbi,
                center=center,
                model_capacity=self.model_capacity,
                verbose=False
            )
            
            # Filter by confidence threshold
            valid_indices = confidence >= confidence_threshold
            
            filtered_times = time_stamps[valid_indices].tolist()
            filtered_pitches = pitches[valid_indices].tolist()
            filtered_confidences = confidence[valid_indices].tolist()
            
            # Convert pitches to notes
            notes = await self._pitches_to_notes(
                filtered_times, 
                filtered_pitches, 
                filtered_confidences
            )
            
            processing_time = asyncio.get_event_loop().time() - start_time
            average_confidence = float(np.mean(filtered_confidences)) if filtered_confidences else 0.0
            
            result = CREPEResult(
                pitches=filtered_pitches,
                confidences=filtered_confidences,
                times=filtered_times,
                notes=notes,
                average_confidence=average_confidence,
                processing_time=processing_time
            )
            
            logger.info(f"CREPE pitch detection completed: "
                       f"{len(filtered_pitches)} pitch points, "
                       f"{len(notes)} notes, "
                       f"avg confidence: {average_confidence:.3f}")
            
            return result
            
        except Exception as e:
            logger.error(f"CREPE pitch detection failed: {e}")
            raise
    
    async def _pitches_to_notes(self, times: List[float], 
                               pitches: List[float], 
                               confidences: List[float]) -> List[Dict]:
        """Convert pitch sequence to note events"""
        if not times or not pitches:
            return []
        
        notes = []
        current_note = None
        
        for i, (time, pitch, conf) in enumerate(zip(times, pitches, confidences)):
            midi_note = self._freq_to_midi(pitch)
            
            # Start new note if pitch changed significantly or first note
            if (current_note is None or 
                abs(midi_note - current_note['midi_note']) > 0.5 or
                time - current_note['start_time'] > 2.0):  # Max 2 second notes
                
                # End previous note
                if current_note is not None:
                    current_note['end_time'] = time
                    current_note['duration'] = time - current_note['start_time']
                    
                    # Only add if note is reasonable length
                    if current_note['duration'] > 0.05:  # At least 50ms
                        notes.append(current_note)
                
                # Start new note
                current_note = {
                    'midi_note': int(round(midi_note)),
                    'start_time': time,
                    'end_time': time,
                    'frequency': pitch,
                    'confidence': conf,
                    'velocity': int(conf * 100 + 27)  # Convert confidence to velocity
                }
        
        # End final note
        if current_note is not None:
            current_note['end_time'] = times[-1] + 0.1  # Small buffer
            current_note['duration'] = current_note['end_time'] - current_note['start_time']
            if current_note['duration'] > 0.05:
                notes.append(current_note)
        
        return notes
    
    def _freq_to_midi(self, freq: float) -> float:
        """Convert frequency to MIDI note number"""
        if freq <= 0:
            return 0
        return 69 + 12 * np.log2(freq / 440.0)
    
    async def detect_pitch_with_onsets(self, audio_path: str,
                                      onset_threshold: float = 0.3) -> CREPEResult:
        """
        Detect pitch with onset detection for better note segmentation
        
        Args:
            audio_path: Path to audio file
            onset_threshold: Threshold for onset detection
        """
        logger.info(f"Starting CREPE pitch detection with onset analysis: {audio_path}")
        
        # First, get basic pitch detection
        pitch_result = await self.detect_pitch(audio_path)
        
        try:
            # Use librosa for onset detection
            import librosa
            
            # Load audio
            y, sr = await asyncio.to_thread(librosa.load, audio_path)
            
            # Detect onsets
            onset_frames = await asyncio.to_thread(
                librosa.onset.onset_detect,
                y=y,
                sr=sr,
                hop_length=512,
                threshold=onset_threshold
            )
            
            onset_times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=512)
            
            # Refine notes using onset information
            refined_notes = await self._refine_notes_with_onsets(
                pitch_result.notes,
                onset_times.tolist()
            )
            
            # Update result with refined notes
            pitch_result.notes = refined_notes
            
            logger.info(f"Refined {len(refined_notes)} notes using {len(onset_times)} onsets")
            
        except Exception as e:
            logger.warning(f"Onset detection failed, using basic pitch detection: {e}")
        
        return pitch_result
    
    async def _refine_notes_with_onsets(self, notes: List[Dict], 
                                       onsets: List[float]) -> List[Dict]:
        """Refine note boundaries using onset detection"""
        if not notes or not onsets:
            return notes
        
        refined_notes = []
        
        for note in notes:
            # Find closest onset to note start
            closest_onset = min(onsets, key=lambda x: abs(x - note['start_time']))
            
            # Use onset if it's close enough (within 200ms)
            if abs(closest_onset - note['start_time']) < 0.2:
                note['start_time'] = closest_onset
                note['duration'] = note['end_time'] - note['start_time']
            
            refined_notes.append(note)
        
        return refined_notes
    
    def set_model_capacity(self, capacity: str):
        """Set CREPE model capacity"""
        valid_capacities = ['tiny', 'small', 'medium', 'large', 'full']
        if capacity in valid_capacities:
            self.model_capacity = capacity
            logger.info(f"CREPE model capacity set to: {capacity}")
        else:
            logger.warning(f"Invalid capacity: {capacity}, using 'full'")


# Global service instance
crepe_service = CREPEService()


# Convenience functions
async def detect_pitch_with_crepe(audio_path: str, **kwargs) -> CREPEResult:
    """Convenience function for CREPE pitch detection"""
    return await crepe_service.detect_pitch(audio_path, **kwargs)


def get_crepe_service() -> CREPEService:
    """Get the global CREPE service instance"""
    return crepe_service
