"""
Result Combiner Tool
Combines Whisper and GPT analysis results into structured format
"""
import logging
from typing import Dict, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AIAnalysisResult:
    """Results from AI audio analysis"""
    tempo: float
    key: str
    time_signature: str
    complexity: str
    instruments: List[str]
    chord_progression: List[Dict]
    notes: List[Dict]
    confidence: float
    analysis_summary: str
    duration: float  # Add actual audio duration


class ResultCombinerTool:
    """Tool for combining analysis results"""
    
    def combine(self, whisper_result: Dict, musical_analysis: Dict, duration: float = None) -> AIAnalysisResult:
        """Combine Whisper and GPT analysis results"""
        logger.info("Combining analysis results...")
        
        # Process notes from musical analysis
        notes = []
        for note_data in musical_analysis.get('notes', []):
            try:
                processed_note = {
                    'midi_note': int(note_data.get('midi_note', 60)),
                    'start_time': float(note_data.get('start_time', 0.0)),
                    'end_time': float(note_data.get('end_time', 0.5)),
                    'duration': float(note_data.get('end_time', 0.5) - note_data.get('start_time', 0.0)),
                    'velocity': int(note_data.get('velocity', 80)),
                    'pitch': int(note_data.get('midi_note', 60)),
                    'confidence': float(note_data.get('confidence', 0.8))
                }
                notes.append(processed_note)
            except Exception as e:
                logger.warning(f"Skipping invalid note data: {note_data}, error: {e}")
                continue
        
        # Normalize complexity
        complexity = self._normalize_complexity(musical_analysis.get('complexity', 'moderate'))
        
        # Get duration from whisper result, fallback to passed duration, then default
        actual_duration = (
            whisper_result.get('duration') or 
            duration or 
            60.0  # fallback default
        )
        
        result = AIAnalysisResult(
            tempo=float(musical_analysis.get('tempo', 120)),
            key=str(musical_analysis.get('key', 'C Major')),
            time_signature=str(musical_analysis.get('time_signature', '4/4')),
            complexity=complexity,
            instruments=musical_analysis.get('instruments', ['guitar']),
            chord_progression=musical_analysis.get('chord_progression', []),
            notes=notes,
            confidence=float(musical_analysis.get('confidence', 0.8)),
            analysis_summary=str(musical_analysis.get('analysis_summary', 'AI analysis completed')),
            duration=float(actual_duration)
        )
        
        logger.info(f"Combined results: {result.tempo}bpm, {result.key}, {len(result.notes)} notes")
        return result
    
    def combine_with_basic_pitch(self, basic_pitch_result: Dict, whisper_result: Dict = None, 
                                gpt_result: Dict = None, duration: float = None) -> AIAnalysisResult:
        """
        Combine Basic Pitch transcription with optional Whisper/GPT results
        Prioritizes Basic Pitch for note detection, uses GPT for musical context
        """
        logger.info("Combining Basic Pitch results with AI analysis...")
        
        # Use Basic Pitch notes as primary source
        notes = basic_pitch_result.get('notes', [])
        
        # Get tempo from Basic Pitch MIDI data or GPT analysis
        tempo = 120.0
        if basic_pitch_result.get('midi_data', {}).get('tempo'):
            tempo = basic_pitch_result['midi_data']['tempo']
        elif gpt_result and gpt_result.get('tempo'):
            tempo = float(gpt_result['tempo'])
        
        # Get musical context from GPT if available
        key = 'C Major'
        time_signature = '4/4'
        complexity = 'moderate'
        instruments = ['guitar']
        chord_progression = []
        analysis_summary = 'Transcribed with Basic Pitch'
        
        if gpt_result:
            key = gpt_result.get('key', key)
            time_signature = gpt_result.get('time_signature', time_signature)
            complexity = self._normalize_complexity(gpt_result.get('complexity', complexity))
            instruments = gpt_result.get('instruments', instruments)
            chord_progression = gpt_result.get('chord_progression', chord_progression)
            analysis_summary = gpt_result.get('analysis_summary', analysis_summary)
        
        # Get duration from various sources
        actual_duration = (
            duration or
            (whisper_result and whisper_result.get('duration')) or
            (max(note['end_time'] for note in notes) if notes else 60.0)
        )
        
        # Calculate overall confidence
        confidence = basic_pitch_result.get('confidence', 0.8)
        if gpt_result and 'confidence' in gpt_result:
            # Average the confidences
            confidence = (confidence + float(gpt_result['confidence'])) / 2
        
        result = AIAnalysisResult(
            tempo=tempo,
            key=key,
            time_signature=time_signature,
            complexity=complexity,
            instruments=instruments,
            chord_progression=chord_progression,
            notes=notes,
            confidence=confidence,
            analysis_summary=f"{analysis_summary} ({len(notes)} notes detected)",
            duration=float(actual_duration)
        )
        
        logger.info(f"Combined results: {result.tempo}bpm, {result.key}, {len(result.notes)} notes, "
                   f"confidence: {result.confidence:.2f}")
        return result
    
    def _normalize_complexity(self, complexity: str) -> str:
        """Normalize complexity values to standard format"""
        complexity_lower = complexity.lower().strip()
        
        if complexity_lower in ['beginner', 'basic', 'easy', 'simple']:
            return 'simple'
        elif complexity_lower in ['intermediate', 'medium', 'moderate']:
            return 'moderate'
        elif complexity_lower in ['advanced', 'difficult', 'complex', 'hard']:
            return 'complex'
        else:
            return complexity_lower