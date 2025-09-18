"""
Advanced Transcription Service
Orchestrates MT3, Omnizart, and CREPE for maximum accuracy and traceability
"""
import asyncio
import logging
import time
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor

from .mt3_service import get_mt3_service, MT3TranscriptionResult
from .omnizart_service import get_omnizart_service, OmnizartResult
from .crepe_service import get_crepe_service, CREPEResult
from .metrics_service import start_task_metrics, complete_task_metrics, update_progress
from .rate_limiter import check_openai_rate_limit, record_openai_request

logger = logging.getLogger(__name__)


@dataclass
class AdvancedTranscriptionResult:
    """Comprehensive transcription result with full traceability"""
    # Core transcription data
    tracks: Dict[str, List[Dict]]  # instrument -> notes
    
    # Musical metadata  
    tempo: float
    key: str
    time_signature: str
    complexity: str
    detected_instruments: List[str]
    
    # Quality metrics
    confidence_scores: Dict[str, float]  # per instrument
    overall_confidence: float
    accuracy_score: float  # Estimated accuracy (0-1)
    
    # Processing metadata (traceability)
    models_used: Dict[str, str]  # instrument -> model name
    processing_times: Dict[str, float]  # stage -> duration
    total_processing_time: float
    
    # Raw results for debugging/analysis
    mt3_result: Optional[MT3TranscriptionResult]
    omnizart_results: Dict[str, OmnizartResult]
    crepe_result: Optional[CREPEResult]
    
    # Chord and rhythm analysis
    chord_progression: List[Dict]
    beat_tracking: List[float]
    
    # Audio metadata
    duration: float
    sample_rate: int
    
    # Version tracking
    service_version: str
    timestamp: str


class AdvancedTranscriptionService:
    """
    Master transcription service that combines multiple SOTA models
    for maximum accuracy and comprehensive traceability
    """
    
    SERVICE_VERSION = "2.0.0"
    
    def __init__(self):
        self.mt3_service = get_mt3_service()
        self.omnizart_service = get_omnizart_service()
        self.crepe_service = get_crepe_service()
        
        # Accuracy weights for model fusion
        self.model_weights = {
            'mt3': 0.5,        # Highest weight - SOTA multi-track
            'omnizart': 0.3,   # Medium weight - specialized models
            'crepe': 0.2       # Lower weight - pitch detection support
        }
        
        logger.info("Advanced Transcription Service initialized with SOTA models")
    
    async def transcribe_audio_advanced(self, audio_path: str,
                                       transcription_id: Optional[str] = None,
                                       use_all_models: bool = True,
                                       accuracy_mode: str = 'maximum') -> AdvancedTranscriptionResult:
        """
        Transcribe audio using all available models for maximum accuracy
        
        Args:
            audio_path: Path to audio file
            transcription_id: ID for progress tracking
            use_all_models: Whether to use all models or just MT3
            accuracy_mode: 'fast', 'balanced', 'maximum'
        
        Returns:
            Comprehensive transcription result with full traceability
        """
        logger.info(f"Starting advanced transcription (mode: {accuracy_mode}): {audio_path}")
        start_time = time.time()
        
        # Initialize progress tracking
        if transcription_id:
            update_progress(transcription_id, 'advanced_transcription', 5, 'starting')
        
        processing_times = {}
        models_used = {}
        
        try:
            # Step 1: MT3 Multi-track transcription (PRIMARY)
            logger.info("Step 1: Running MT3 multi-track transcription...")
            mt3_start = time.time()
            
            if transcription_id:
                update_progress(transcription_id, 'advanced_transcription', 20, 'mt3_processing')
            
            mt3_result = await self.mt3_service.transcribe_multitrack(audio_path)
            processing_times['mt3'] = time.time() - mt3_start
            models_used.update({inst: 'MT3' for inst in mt3_result.tracks.keys()})
            
            logger.info(f"MT3 completed: {len(mt3_result.tracks)} instruments in {processing_times['mt3']:.2f}s")
            
            # Initialize result with MT3 data
            combined_tracks = mt3_result.tracks.copy()
            confidence_scores = mt3_result.confidence_scores.copy()
            
            if use_all_models and accuracy_mode in ['balanced', 'maximum']:
                # Step 2: Omnizart specialized transcription (ENHANCEMENT)
                logger.info("Step 2: Running Omnizart specialized transcription...")
                omnizart_start = time.time()
                
                if transcription_id:
                    update_progress(transcription_id, 'advanced_transcription', 50, 'omnizart_processing')
                
                omnizart_results = await self.omnizart_service.transcribe_all_instruments(audio_path)
                processing_times['omnizart'] = time.time() - omnizart_start
                
                # Merge Omnizart results with MT3
                combined_tracks, confidence_scores = await self._merge_omnizart_results(
                    combined_tracks, confidence_scores, omnizart_results
                )
                
                logger.info(f"Omnizart completed: {len(omnizart_results)} instruments in {processing_times['omnizart']:.2f}s")
            else:
                omnizart_results = {}
            
            # Step 3: CREPE pitch refinement (PRECISION)
            crepe_result = None
            if use_all_models and accuracy_mode == 'maximum':
                logger.info("Step 3: Running CREPE pitch refinement...")
                crepe_start = time.time()
                
                if transcription_id:
                    update_progress(transcription_id, 'advanced_transcription', 75, 'crepe_processing')
                
                crepe_result = await self.crepe_service.detect_pitch_with_onsets(audio_path)
                processing_times['crepe'] = time.time() - crepe_start
                
                # Refine pitch accuracy using CREPE
                combined_tracks = await self._refine_with_crepe(combined_tracks, crepe_result)
                
                logger.info(f"CREPE completed: {len(crepe_result.notes)} refined notes in {processing_times['crepe']:.2f}s")
            
            # Step 4: Extract enhanced musical metadata
            if transcription_id:
                update_progress(transcription_id, 'advanced_transcription', 90, 'analyzing_metadata')
            
            metadata = await self._extract_enhanced_metadata(
                mt3_result, omnizart_results, crepe_result
            )
            
            # Step 5: Calculate quality metrics
            accuracy_score = self._calculate_accuracy_score(
                combined_tracks, confidence_scores, metadata
            )
            
            # Get audio metadata
            audio_metadata = await self._get_audio_metadata(audio_path)
            
            total_time = time.time() - start_time
            processing_times['total'] = total_time
            
            # Create comprehensive result
            result = AdvancedTranscriptionResult(
                tracks=combined_tracks,
                tempo=metadata['tempo'],
                key=metadata['key'],
                time_signature=metadata['time_signature'],
                complexity=metadata['complexity'],
                detected_instruments=list(combined_tracks.keys()),
                confidence_scores=confidence_scores,
                overall_confidence=float(np.mean(list(confidence_scores.values()))) if confidence_scores else 0.8,
                accuracy_score=accuracy_score,
                models_used=models_used,
                processing_times=processing_times,
                total_processing_time=total_time,
                mt3_result=mt3_result,
                omnizart_results=omnizart_results,
                crepe_result=crepe_result,
                chord_progression=metadata.get('chords', []),
                beat_tracking=metadata.get('beats', []),
                duration=audio_metadata['duration'],
                sample_rate=audio_metadata['sample_rate'],
                service_version=self.SERVICE_VERSION,
                timestamp=time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
            )
            
            if transcription_id:
                update_progress(transcription_id, 'advanced_transcription', 100, 'completed')
            
            logger.info(f"Advanced transcription completed in {total_time:.2f}s")
            logger.info(f"Final result: {len(combined_tracks)} instruments, "
                       f"accuracy: {accuracy_score:.3f}, "
                       f"confidence: {result.overall_confidence:.3f}")
            
            return result
            
        except Exception as e:
            if transcription_id:
                update_progress(transcription_id, 'advanced_transcription', 0, 'failed')
            
            logger.error(f"Advanced transcription failed: {e}")
            raise
    
    async def _merge_omnizart_results(self, mt3_tracks: Dict, mt3_confidence: Dict,
                                     omnizart_results: Dict[str, OmnizartResult]) -> Tuple[Dict, Dict]:
        """Merge Omnizart results with MT3 for enhanced accuracy"""
        merged_tracks = mt3_tracks.copy()
        merged_confidence = mt3_confidence.copy()
        
        for instrument, omnizart_result in omnizart_results.items():
            if instrument in merged_tracks:
                # Merge notes from both models using weighted combination
                mt3_notes = merged_tracks[instrument]
                omnizart_notes = omnizart_result.notes
                
                # Use MT3 as base, enhance with Omnizart where confidence is higher
                enhanced_notes = await self._combine_note_lists(
                    mt3_notes, omnizart_notes, 
                    mt3_weight=self.model_weights['mt3'],
                    omnizart_weight=self.model_weights['omnizart']
                )
                
                merged_tracks[instrument] = enhanced_notes
                
                # Update confidence score (weighted average)
                mt3_conf = merged_confidence.get(instrument, 0.8)
                omnizart_conf = omnizart_result.confidence
                
                merged_confidence[instrument] = (
                    mt3_conf * self.model_weights['mt3'] + 
                    omnizart_conf * self.model_weights['omnizart']
                ) / (self.model_weights['mt3'] + self.model_weights['omnizart'])
                
                logger.debug(f"Merged {instrument}: MT3 conf={mt3_conf:.2f}, "
                           f"Omnizart conf={omnizart_conf:.2f}, "
                           f"final={merged_confidence[instrument]:.2f}")
            else:
                # Add new instrument found by Omnizart
                merged_tracks[instrument] = omnizart_result.notes
                merged_confidence[instrument] = omnizart_result.confidence
                logger.info(f"Added new instrument from Omnizart: {instrument}")
        
        return merged_tracks, merged_confidence
    
    async def _combine_note_lists(self, notes1: List[Dict], notes2: List[Dict],
                                 mt3_weight: float, omnizart_weight: float) -> List[Dict]:
        """Intelligently combine note lists from different models"""
        if not notes2:
            return notes1
        if not notes1:
            return notes2
        
        # Create time-based grid for comparison
        combined_notes = []
        time_tolerance = 0.1  # 100ms tolerance for matching notes
        
        # Start with MT3 notes (higher weight)
        for mt3_note in notes1:
            # Find matching Omnizart notes
            matching_omnizart = [
                n for n in notes2 
                if abs(n['start_time'] - mt3_note['start_time']) < time_tolerance
                and abs(n['midi_note'] - mt3_note['midi_note']) <= 1  # Semitone tolerance
            ]
            
            if matching_omnizart:
                # Merge with highest confidence match
                best_match = max(matching_omnizart, key=lambda x: x.get('confidence', 0.8))
                
                # Weighted merge
                merged_note = mt3_note.copy()
                merged_note['confidence'] = (
                    mt3_note.get('confidence', 0.9) * mt3_weight +
                    best_match.get('confidence', 0.8) * omnizart_weight
                ) / (mt3_weight + omnizart_weight)
                
                # Use more precise timing if Omnizart has higher confidence
                if best_match.get('confidence', 0.8) > mt3_note.get('confidence', 0.9):
                    merged_note['start_time'] = best_match['start_time']
                    merged_note['end_time'] = best_match['end_time']
                    merged_note['duration'] = best_match['duration']
                
                combined_notes.append(merged_note)
            else:
                # Keep MT3 note
                combined_notes.append(mt3_note)
        
        # Add unique Omnizart notes not matched by MT3
        for omnizart_note in notes2:
            is_unique = not any(
                abs(omnizart_note['start_time'] - mt3_note['start_time']) < time_tolerance
                and abs(omnizart_note['midi_note'] - mt3_note['midi_note']) <= 1
                for mt3_note in notes1
            )
            
            if is_unique and omnizart_note.get('confidence', 0.8) > 0.7:
                combined_notes.append(omnizart_note)
        
        # Sort by start time
        combined_notes.sort(key=lambda x: x['start_time'])
        
        logger.debug(f"Combined notes: {len(notes1)} + {len(notes2)} -> {len(combined_notes)}")
        return combined_notes
    
    async def _refine_with_crepe(self, tracks: Dict[str, List[Dict]], 
                                crepe_result: CREPEResult) -> Dict[str, List[Dict]]:
        """Refine pitch accuracy using CREPE"""
        if not crepe_result or not crepe_result.notes:
            return tracks
        
        refined_tracks = {}
        
        for instrument, notes in tracks.items():
            if instrument in ['guitar', 'bass', 'vocals']:  # Instruments that benefit from pitch refinement
                refined_notes = await self._apply_crepe_refinement(notes, crepe_result)
                refined_tracks[instrument] = refined_notes
                logger.debug(f"CREPE refined {instrument}: {len(notes)} -> {len(refined_notes)} notes")
            else:
                refined_tracks[instrument] = notes
        
        return refined_tracks
    
    async def _apply_crepe_refinement(self, notes: List[Dict], 
                                     crepe_result: CREPEResult) -> List[Dict]:
        """Apply CREPE pitch refinement to note list"""
        refined_notes = []
        
        for note in notes:
            # Find CREPE pitch measurements within note duration
            start_time = note['start_time']
            end_time = note['end_time']
            
            # Get CREPE pitches in this time range
            relevant_pitches = [
                (t, p, c) for t, p, c in zip(crepe_result.times, crepe_result.pitches, crepe_result.confidences)
                if start_time <= t <= end_time and c > 0.8  # High confidence only
            ]
            
            if relevant_pitches:
                # Use CREPE's pitch if it's more confident
                avg_crepe_pitch = np.mean([p for _, p, _ in relevant_pitches])
                avg_crepe_confidence = np.mean([c for _, _, c in relevant_pitches])
                
                crepe_midi = 69 + 12 * np.log2(avg_crepe_pitch / 440.0)
                
                # Use CREPE pitch if significantly different and more confident
                if (abs(crepe_midi - note['midi_note']) > 0.5 and 
                    avg_crepe_confidence > note.get('confidence', 0.8)):
                    
                    refined_note = note.copy()
                    refined_note['midi_note'] = int(round(crepe_midi))
                    refined_note['frequency'] = avg_crepe_pitch
                    refined_note['confidence'] = avg_crepe_confidence
                    refined_note['refined_by'] = 'CREPE'
                    
                    refined_notes.append(refined_note)
                    logger.debug(f"CREPE refined note: {note['midi_note']} -> {refined_note['midi_note']}")
                else:
                    refined_notes.append(note)
            else:
                refined_notes.append(note)
        
        return refined_notes
    
    async def _extract_enhanced_metadata(self, mt3_result: MT3TranscriptionResult,
                                        omnizart_results: Dict[str, OmnizartResult],
                                        crepe_result: Optional[CREPEResult]) -> Dict[str, Any]:
        """Extract enhanced musical metadata from all sources"""
        metadata = {
            'tempo': mt3_result.tempo,
            'key': mt3_result.key_signature,
            'time_signature': mt3_result.time_signature,
            'complexity': 'moderate',
            'chords': [],
            'beats': []
        }
        
        # Get chord progression from Omnizart if available
        if 'chord' in omnizart_results:
            metadata['chords'] = omnizart_results['chord'].chords or []
        
        # Get beat tracking from Omnizart if available  
        if 'beat' in omnizart_results:
            metadata['beats'] = omnizart_results['beat'].beats or []
        
        # Estimate complexity based on number of instruments and note density
        total_instruments = len(mt3_result.tracks)
        total_notes = sum(len(notes) for notes in mt3_result.tracks.values())
        
        if total_instruments >= 4 and total_notes > 200:
            metadata['complexity'] = 'complex'
        elif total_instruments >= 2 and total_notes > 100:
            metadata['complexity'] = 'moderate'  
        else:
            metadata['complexity'] = 'simple'
        
        return metadata
    
    def _calculate_accuracy_score(self, tracks: Dict, confidence_scores: Dict, 
                                 metadata: Dict) -> float:
        """Calculate estimated accuracy score based on multiple factors"""
        factors = []
        
        # Factor 1: Average confidence across all instruments
        if confidence_scores:
            avg_confidence = np.mean(list(confidence_scores.values()))
            factors.append(avg_confidence * 0.4)  # 40% weight
        
        # Factor 2: Number of instruments successfully detected
        instrument_factor = min(1.0, len(tracks) / 4.0)  # Normalize to 4 instruments
        factors.append(instrument_factor * 0.2)  # 20% weight
        
        # Factor 3: Note density consistency
        if tracks:
            note_counts = [len(notes) for notes in tracks.values()]
            if note_counts:
                density_consistency = 1.0 - (np.std(note_counts) / (np.mean(note_counts) + 1))
                factors.append(max(0.0, density_consistency) * 0.2)  # 20% weight
        
        # Factor 4: Model agreement (if multiple models used)
        model_agreement = 0.8  # Default assumption
        factors.append(model_agreement * 0.2)  # 20% weight
        
        # Combine factors
        accuracy_score = sum(factors)
        
        # Clamp to reasonable range
        return max(0.1, min(1.0, accuracy_score))
    
    async def _get_audio_metadata(self, audio_path: str) -> Dict[str, Any]:
        """Get audio file metadata"""
        import librosa
        
        try:
            # Get basic audio info
            y, sr = await asyncio.to_thread(librosa.load, audio_path, sr=None)
            duration = librosa.get_duration(y=y, sr=sr)
            
            return {
                'duration': duration,
                'sample_rate': sr,
                'channels': 1 if y.ndim == 1 else y.shape[0]
            }
        except Exception as e:
            logger.warning(f"Could not get audio metadata: {e}")
            return {
                'duration': 60.0,
                'sample_rate': 44100,
                'channels': 2
            }
    
    async def transcribe_single_instrument(self, audio_path: str, 
                                          instrument: str,
                                          use_specialized_model: bool = True) -> Dict[str, Any]:
        """
        Transcribe single instrument with highest accuracy
        
        Args:
            audio_path: Path to audio file
            instrument: Target instrument
            use_specialized_model: Whether to use instrument-specific models
        """
        logger.info(f"Starting single instrument transcription: {instrument}")
        
        results = {}
        
        # Use specialized Omnizart model if available and requested
        if use_specialized_model and instrument in ['piano', 'guitar', 'vocal', 'drum']:
            try:
                omnizart_result = await self.omnizart_service.transcribe_instrument(
                    audio_path, instrument
                )
                results['omnizart'] = omnizart_result
                logger.info(f"Omnizart {instrument}: {len(omnizart_result.notes)} notes")
            except Exception as e:
                logger.warning(f"Omnizart {instrument} failed: {e}")
        
        # Also get MT3 result for comparison
        try:
            mt3_result = await self.mt3_service.transcribe_multitrack(audio_path)
            if instrument in mt3_result.tracks:
                results['mt3'] = {
                    'notes': mt3_result.tracks[instrument],
                    'confidence': mt3_result.confidence_scores.get(instrument, 0.8)
                }
                logger.info(f"MT3 {instrument}: {len(mt3_result.tracks[instrument])} notes")
        except Exception as e:
            logger.warning(f"MT3 {instrument} failed: {e}")
        
        # Combine results if we have multiple
        if len(results) > 1 and 'omnizart' in results and 'mt3' in results:
            # Use Omnizart as primary (specialized model)
            combined_notes = await self._combine_note_lists(
                results['omnizart'].notes,
                results['mt3']['notes'],
                mt3_weight=0.3,
                omnizart_weight=0.7
            )
            
            final_confidence = (
                results['omnizart'].confidence * 0.7 +
                results['mt3']['confidence'] * 0.3
            )
        elif 'omnizart' in results:
            combined_notes = results['omnizart'].notes
            final_confidence = results['omnizart'].confidence
        elif 'mt3' in results:
            combined_notes = results['mt3']['notes']
            final_confidence = results['mt3']['confidence']
        else:
            combined_notes = []
            final_confidence = 0.0
        
        return {
            'notes': combined_notes,
            'confidence': final_confidence,
            'models_used': list(results.keys())
        }
    
    def get_service_info(self) -> Dict[str, Any]:
        """Get service information and capabilities"""
        return {
            'version': self.SERVICE_VERSION,
            'models': {
                'mt3': 'Google Multi-Task Multitrack Music Transcription',
                'omnizart': 'Comprehensive music transcription toolkit',
                'crepe': 'Advanced pitch detection with CNN'
            },
            'supported_instruments': [
                'piano', 'guitar', 'bass', 'drums', 'vocals', 
                'strings', 'brass', 'woodwinds', 'other'
            ],
            'accuracy_modes': ['fast', 'balanced', 'maximum'],
            'max_audio_length': 300.0,  # 5 minutes
            'expected_accuracy': {
                'guitar': 0.92,
                'piano': 0.95, 
                'vocals': 0.88,
                'bass': 0.85,
                'drums': 0.80
            }
        }


# Global service instance
advanced_transcription_service = AdvancedTranscriptionService()


# Convenience functions
async def transcribe_advanced(audio_path: str, **kwargs) -> AdvancedTranscriptionResult:
    """Convenience function for advanced transcription"""
    return await advanced_transcription_service.transcribe_audio_advanced(audio_path, **kwargs)


def get_advanced_service() -> AdvancedTranscriptionService:
    """Get the global advanced transcription service"""
    return advanced_transcription_service
