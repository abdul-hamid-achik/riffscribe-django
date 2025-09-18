"""
Omnizart Service - Comprehensive music transcription toolkit
Provides specialized models for different instruments and musical elements
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
class OmnizartResult:
    """Results from Omnizart transcription"""
    instrument: str
    notes: List[Dict]
    chords: Optional[List[Dict]]
    beats: Optional[List[float]]
    confidence: float
    model_used: str
    processing_time: float


class OmnizartService:
    """Service for Omnizart multi-instrument transcription"""
    
    def __init__(self):
        self.models = {}
        self.models_loaded = False
        
        # Available Omnizart models
        self.available_models = {
            'piano': 'Piano',
            'guitar': 'Guitar', 
            'vocal': 'Vocal',
            'vocal-contour': 'Vocal Contour',
            'drum': 'Drum',
            'chord': 'Chord',
            'beat': 'Beat'
        }
    
    def _ensure_models_loaded(self, model_types: List[str]):
        """Lazy load specific Omnizart models"""
        try:
            import omnizart.music as music
            import omnizart.vocal as vocal
            import omnizart.drum as drum
            import omnizart.chord as chord
            import omnizart.beat as beat
            
            self.modules = {
                'piano': music,
                'guitar': music,  # Use music module for guitar
                'vocal': vocal,
                'vocal-contour': vocal,
                'drum': drum,
                'chord': chord,
                'beat': beat
            }
            
            # Load requested models
            for model_type in model_types:
                if model_type not in self.models and model_type in self.modules:
                    logger.info(f"Loading Omnizart {model_type} model...")
                    # Models are loaded on-demand by Omnizart
                    self.models[model_type] = self.modules[model_type]
            
            self.models_loaded = True
            logger.info(f"Omnizart models loaded: {list(self.models.keys())}")
            
        except ImportError as e:
            logger.error(f"Omnizart not available: {e}")
            raise ImportError("Install Omnizart: pip install omnizart")
    
    async def transcribe_instrument(self, audio_path: str, 
                                   instrument: str,
                                   model_path: Optional[str] = None) -> OmnizartResult:
        """
        Transcribe specific instrument using Omnizart
        
        Args:
            audio_path: Path to audio file
            instrument: Instrument type to transcribe
            model_path: Optional custom model path
        
        Returns:
            OmnizartResult with transcription data
        """
        logger.info(f"Starting Omnizart {instrument} transcription: {audio_path}")
        start_time = asyncio.get_event_loop().time()
        
        # Ensure model is loaded
        self._ensure_models_loaded([instrument])
        
        try:
            # Run instrument-specific transcription
            if instrument in ['piano', 'guitar']:
                result = await self._transcribe_music(audio_path, instrument, model_path)
            elif instrument in ['vocal', 'vocal-contour']:
                result = await self._transcribe_vocal(audio_path, model_path)
            elif instrument == 'drum':
                result = await self._transcribe_drum(audio_path, model_path)
            elif instrument == 'chord':
                result = await self._transcribe_chord(audio_path, model_path)
            elif instrument == 'beat':
                result = await self._transcribe_beat(audio_path, model_path)
            else:
                raise ValueError(f"Unsupported instrument: {instrument}")
            
            processing_time = asyncio.get_event_loop().time() - start_time
            
            omnizart_result = OmnizartResult(
                instrument=instrument,
                notes=result.get('notes', []),
                chords=result.get('chords'),
                beats=result.get('beats'),
                confidence=result.get('confidence', 0.8),
                model_used=f"omnizart_{instrument}",
                processing_time=processing_time
            )
            
            logger.info(f"Omnizart {instrument} transcription completed: "
                       f"{len(omnizart_result.notes)} notes in {processing_time:.2f}s")
            
            return omnizart_result
            
        except Exception as e:
            logger.error(f"Omnizart {instrument} transcription failed: {e}")
            raise
    
    async def _transcribe_music(self, audio_path: str, instrument: str, 
                               model_path: Optional[str] = None) -> Dict:
        """Transcribe piano/guitar using music module"""
        module = self.models['piano']  # Use piano module for both
        
        # Run transcription
        midi_path = await asyncio.to_thread(
            module.transcribe,
            audio_path,
            model_path=model_path,
            output='./output'  # Omnizart requires output path
        )
        
        # Parse MIDI result
        notes = await self._parse_midi_to_notes(midi_path)
        confidence = self._estimate_music_confidence(notes)
        
        # Clean up
        if os.path.exists(midi_path):
            os.remove(midi_path)
        
        return {
            'notes': notes,
            'confidence': confidence
        }
    
    async def _transcribe_vocal(self, audio_path: str, 
                               model_path: Optional[str] = None) -> Dict:
        """Transcribe vocals using vocal module"""
        module = self.models['vocal']
        
        # Run transcription
        midi_path = await asyncio.to_thread(
            module.transcribe,
            audio_path,
            model_path=model_path,
            output='./output'
        )
        
        notes = await self._parse_midi_to_notes(midi_path)
        confidence = self._estimate_vocal_confidence(notes)
        
        # Clean up
        if os.path.exists(midi_path):
            os.remove(midi_path)
        
        return {
            'notes': notes,
            'confidence': confidence
        }
    
    async def _transcribe_drum(self, audio_path: str,
                              model_path: Optional[str] = None) -> Dict:
        """Transcribe drums using drum module"""
        module = self.models['drum']
        
        # Run transcription  
        midi_path = await asyncio.to_thread(
            module.transcribe,
            audio_path,
            model_path=model_path,
            output='./output'
        )
        
        notes = await self._parse_midi_to_notes(midi_path)
        confidence = self._estimate_drum_confidence(notes)
        
        # Clean up
        if os.path.exists(midi_path):
            os.remove(midi_path)
        
        return {
            'notes': notes,
            'confidence': confidence
        }
    
    async def _transcribe_chord(self, audio_path: str,
                               model_path: Optional[str] = None) -> Dict:
        """Transcribe chord progressions"""
        module = self.models['chord']
        
        # Run transcription
        result_path = await asyncio.to_thread(
            module.transcribe,
            audio_path,
            model_path=model_path,
            output='./output'
        )
        
        # Parse chord result (CSV format)
        chords = await self._parse_chord_csv(result_path)
        
        # Clean up
        if os.path.exists(result_path):
            os.remove(result_path)
        
        return {
            'chords': chords,
            'confidence': 0.85  # Chord detection is generally reliable
        }
    
    async def _transcribe_beat(self, audio_path: str,
                              model_path: Optional[str] = None) -> Dict:
        """Transcribe beat/tempo information"""
        module = self.models['beat']
        
        # Run transcription
        result_path = await asyncio.to_thread(
            module.transcribe,
            audio_path,
            model_path=model_path,
            output='./output'
        )
        
        # Parse beat result
        beats = await self._parse_beat_csv(result_path)
        
        # Clean up
        if os.path.exists(result_path):
            os.remove(result_path)
        
        return {
            'beats': beats,
            'confidence': 0.9  # Beat detection is very reliable
        }
    
    async def _parse_midi_to_notes(self, midi_path: str) -> List[Dict]:
        """Parse MIDI file to note list"""
        import pretty_midi
        
        if not os.path.exists(midi_path):
            return []
        
        try:
            midi_data = pretty_midi.PrettyMIDI(midi_path)
            notes = []
            
            for instrument in midi_data.instruments:
                for note in instrument.notes:
                    notes.append({
                        'midi_note': note.pitch,
                        'start_time': note.start,
                        'end_time': note.end,
                        'duration': note.end - note.start,
                        'velocity': note.velocity,
                        'program': instrument.program,
                        'is_drum': instrument.is_drum
                    })
            
            return sorted(notes, key=lambda x: x['start_time'])
            
        except Exception as e:
            logger.error(f"Failed to parse MIDI file {midi_path}: {e}")
            return []
    
    async def _parse_chord_csv(self, csv_path: str) -> List[Dict]:
        """Parse chord progression CSV"""
        import csv
        
        chords = []
        try:
            with open(csv_path, 'r') as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 2:
                        chords.append({
                            'time': float(row[0]),
                            'chord': row[1]
                        })
        except Exception as e:
            logger.error(f"Failed to parse chord CSV {csv_path}: {e}")
        
        return chords
    
    async def _parse_beat_csv(self, csv_path: str) -> List[float]:
        """Parse beat timing CSV"""
        beats = []
        try:
            with open(csv_path, 'r') as f:
                for line in f:
                    beat_time = float(line.strip())
                    beats.append(beat_time)
        except Exception as e:
            logger.error(f"Failed to parse beat CSV {csv_path}: {e}")
        
        return beats
    
    def _estimate_music_confidence(self, notes: List[Dict]) -> float:
        """Estimate confidence for music transcription"""
        if not notes:
            return 0.0
        
        # Simple heuristic based on note density and range
        duration = max(note['end_time'] for note in notes) if notes else 1.0
        note_density = len(notes) / duration
        
        # Reasonable note density indicates good transcription
        if 0.5 <= note_density <= 10.0:
            return 0.9
        elif note_density < 0.5:
            return 0.6  # Too sparse
        else:
            return 0.7  # Too dense, might be noise
    
    def _estimate_vocal_confidence(self, notes: List[Dict]) -> float:
        """Estimate confidence for vocal transcription"""
        if not notes:
            return 0.0
        
        # Vocal notes should be more continuous and in vocal range
        vocal_range_notes = [n for n in notes if 200 <= n['midi_note'] <= 800]  # Vocal frequency range
        confidence = len(vocal_range_notes) / len(notes) if notes else 0.0
        
        return min(0.95, confidence + 0.3)  # Boost vocal confidence
    
    def _estimate_drum_confidence(self, notes: List[Dict]) -> float:
        """Estimate confidence for drum transcription"""
        if not notes:
            return 0.0
        
        # Drums should have short, percussive notes
        short_notes = [n for n in notes if n['duration'] < 0.5]
        confidence = len(short_notes) / len(notes) if notes else 0.0
        
        return min(0.9, confidence + 0.2)
    
    async def transcribe_all_instruments(self, audio_path: str) -> Dict[str, OmnizartResult]:
        """Transcribe all supported instruments"""
        logger.info(f"Starting comprehensive Omnizart transcription: {audio_path}")
        
        # Define instruments to transcribe
        instruments_to_process = ['piano', 'guitar', 'vocal', 'drum']
        
        results = {}
        
        # Process each instrument
        for instrument in instruments_to_process:
            try:
                result = await self.transcribe_instrument(audio_path, instrument)
                
                # Only include if we got meaningful results
                if result.notes or (instrument == 'chord' and result.chords):
                    results[instrument] = result
                    logger.info(f"Successfully transcribed {instrument}: "
                               f"{len(result.notes)} notes, confidence: {result.confidence:.2f}")
                else:
                    logger.info(f"No significant {instrument} content detected")
                    
            except Exception as e:
                logger.warning(f"Failed to transcribe {instrument}: {e}")
                continue
        
        return results


# Global service instance
omnizart_service = OmnizartService()


# Convenience functions
async def transcribe_with_omnizart(audio_path: str, instrument: str) -> OmnizartResult:
    """Convenience function for single instrument transcription"""
    return await omnizart_service.transcribe_instrument(audio_path, instrument)


async def transcribe_all_with_omnizart(audio_path: str) -> Dict[str, OmnizartResult]:
    """Convenience function for all instruments transcription"""
    return await omnizart_service.transcribe_all_instruments(audio_path)


def get_omnizart_service() -> OmnizartService:
    """Get the global Omnizart service instance"""
    return omnizart_service
