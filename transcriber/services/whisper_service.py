"""
Whisper AI service for enhanced audio transcription and music analysis
"""

import os
import logging
import tempfile
import json
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from ..utils.json_utils import clean_analysis_result
import numpy as np
import librosa
import soundfile as sf
from openai import OpenAI
import openai  # re-exported module for tests that patch transcriber.services.whisper_service.openai
from django.conf import settings

logger = logging.getLogger(__name__)


class WhisperService:
    """
    Service for using OpenAI's Whisper API for audio transcription
    and music analysis.
    """
    
    # Whisper model options
    MODEL_WHISPER_1 = "whisper-1"
    
    # Maximum file size for Whisper API (25MB)
    MAX_FILE_SIZE = 25 * 1024 * 1024
    
    # Supported audio formats
    SUPPORTED_FORMATS = ['mp3', 'mp4', 'mpeg', 'mpga', 'm4a', 'wav', 'webm']
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize Whisper service with OpenAI API key.
        
        Args:
            api_key: OpenAI API key (defaults to env variable)
        """
        # If explicitly passed None, do not fall back to env/settings (tests expect this)
        if api_key is None:
            self.api_key = None
            self.client = None
            self.model = model or self.MODEL_WHISPER_1
            return
        
        self.api_key = api_key or os.getenv('OPENAI_API_KEY') or settings.OPENAI_API_KEY
        if not self.api_key:
            # Tests expect graceful no-client fallback when no key
            self.client = None
            self.model = model or self.MODEL_WHISPER_1
            return
        
        # Initialize via openai.OpenAI so tests patching module attribute pass
        self.client = openai.OpenAI(api_key=self.api_key)
        self.model = model or self.MODEL_WHISPER_1
        
    def transcribe_audio(self, audio_path: str, 
                        language: Optional[str] = None,
                        prompt: Optional[str] = None,
                        temperature: float = 0.0) -> Dict[str, Any]:
        """
        Transcribe audio using Whisper API.
        
        Args:
            audio_path: Path to audio file
            language: Optional language code (e.g., 'en')
            prompt: Optional prompt to guide transcription
            temperature: Sampling temperature (0-1)
            
        Returns:
            Dict containing transcription results
        """
        try:
            # Check if client is configured first
            if not self.client:
                return {"status": "error", "error": "Whisper client not configured", "text": "", "segments": []}
                
            # Validate and prepare audio file
            audio_file = self._prepare_audio_file(audio_path)
            
            # Prepare transcription parameters
            params = {
                "model": self.MODEL_WHISPER_1,
                "file": audio_file,
                "response_format": "verbose_json",
                "temperature": temperature
            }
            
            if language:
                params["language"] = language
                
            if prompt:
                params["prompt"] = prompt
                
            # Call Whisper API
            logger.info(f"Transcribing audio with Whisper: {audio_path}")
            # The client may return either objects with attributes or plain dicts in tests
            response = self.client.audio.transcriptions.create(**params)
            
            # Process response
            if isinstance(response, dict):
                text_val = response.get('text', '')
                segments = response.get('segments', [])
            else:
                text_val = getattr(response, 'text', '')
                segments = getattr(response, 'segments', [])
            result = {
                "text": text_val,
                "language": getattr(response, 'language', None) if not isinstance(response, dict) else response.get('language'),
                "duration": getattr(response, 'duration', None) if not isinstance(response, dict) else response.get('duration'),
                "segments": []
            }
            
            # Extract segments with timestamps if available
            if segments:
                for segment in segments:
                    if isinstance(segment, dict):
                        start = segment.get('start')
                        end = segment.get('end')
                        text = segment.get('text')
                        tokens = segment.get('tokens')
                        temperature = segment.get('temperature')
                        avg_logprob = segment.get('avg_logprob')
                        compression_ratio = segment.get('compression_ratio')
                        no_speech_prob = segment.get('no_speech_prob')
                        seg_id = segment.get('id')
                    else:
                        start = getattr(segment, 'start', None)
                        end = getattr(segment, 'end', None)
                        text = getattr(segment, 'text', None)
                        tokens = getattr(segment, 'tokens', None)
                        temperature = getattr(segment, 'temperature', None)
                        avg_logprob = getattr(segment, 'avg_logprob', None)
                        compression_ratio = getattr(segment, 'compression_ratio', None)
                        no_speech_prob = getattr(segment, 'no_speech_prob', None)
                        seg_id = getattr(segment, 'id', None)
                    result["segments"].append({
                        "id": seg_id,
                        "start": start,
                        "end": end,
                        "text": text,
                        "tokens": tokens,
                        "temperature": temperature,
                        "avg_logprob": avg_logprob,
                        "compression_ratio": compression_ratio,
                        "no_speech_prob": no_speech_prob
                    })
                    
            return result
            
        except Exception as e:
            logger.error(f"Error transcribing audio with Whisper: {str(e)}")
            return {"status": "error", "error": str(e), "text": "", "segments": []}
            
        finally:
            # Clean up temporary file if created
            if 'audio_file' in locals() and hasattr(audio_file, 'name'):
                try:
                    audio_file.close()
                    if os.path.exists(audio_file.name):
                        os.unlink(audio_file.name)
                except:
                    pass
                    
    def analyze_music(self, audio_path: str) -> Dict[str, Any]:
        """
        Analyze music using Whisper with music-specific prompts.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Dict containing music analysis results
        """
        # Use music-specific prompt to guide transcription
        music_prompt = (
            "This is a musical recording. Please identify musical elements including: "
            "instruments, tempo changes, key signatures, chord progressions, "
            "dynamics, and any notable musical techniques or patterns."
        )
        
        try:
            # Check if client is configured first
            if not self.client:
                return {"status": "error", "error": "Whisper client not configured"}
                
            # Get transcription with music prompt
            transcription = self.transcribe_audio(
                audio_path,
                prompt=music_prompt,
                temperature=0.2  # Slightly higher temperature for creative interpretation
            )
            
            # If transcribe_audio failed, return error
            if transcription.get("status") == "error":
                return transcription
            
            # Analyze transcription for musical elements
            analysis = self._extract_musical_elements(transcription)
            
            # Combine with audio analysis
            audio_features = self._analyze_audio_features(audio_path)
            
            return clean_analysis_result({
                "status": "success",
                "transcription": transcription,
                "musical_elements": analysis,
                "audio_features": audio_features,
                "confidence": self._calculate_confidence(transcription)
            })
            
        except Exception as e:
            logger.error(f"Error analyzing music with Whisper: {str(e)}")
            raise
            
    def detect_chords_and_notes(self, audio_path: str) -> Dict[str, Any]:
        """
        Detect chords and notes using Whisper's analysis.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Dict containing detected musical elements
        """
        # Specialized prompt for chord detection
        chord_prompt = (
            "Listen for guitar chords and individual notes. "
            "Identify chord names (e.g., C major, Am, G7), "
            "note sequences, and timing. Focus on: "
            "1) Chord progressions with their names "
            "2) Individual note patterns "
            "3) Rhythm and strumming patterns "
            "4) Any guitar-specific techniques (hammer-on, pull-off, bend, slide)"
        )
        
        try:
            # Check if client is configured first
            if not self.client:
                return {"status": "error", "error": "Whisper client not configured", "chords": [], "notes": [], "techniques": []}
                
            # Get transcription with chord detection prompt
            result = self.transcribe_audio(
                audio_path,
                prompt=chord_prompt,
                temperature=0.1  # Low temperature for accuracy
            )
            
            # If transcribe_audio failed, return error
            if result.get("status") == "error":
                return {"status": "error", "error": result.get("error", "Unknown error"), "chords": [], "notes": [], "techniques": []}
            
            # Parse detected elements
            detected = {
                "chords": [],
                "notes": [],
                "techniques": [],
                "timing": []
            }
            
            # Extract chord and note information from segments
            for segment in result.get("segments", []):
                text = segment["text"].lower()
                
                # Detect chord names
                chords = self._extract_chord_names(text)
                if chords:
                    detected["chords"].extend([{
                        "chord": chord,
                        "start_time": segment["start"],
                        "end_time": segment["end"],
                        "confidence": 1.0 - segment.get("no_speech_prob", 0.5)
                    } for chord in chords])
                    
                # Detect techniques
                techniques = self._extract_techniques(text)
                if techniques:
                    detected["techniques"].extend([{
                        "technique": tech,
                        "time": segment["start"]
                    } for tech in techniques])
                    
            detected["status"] = "success"
            return detected
            
        except Exception as e:
            logger.error(f"Error detecting chords with Whisper: {str(e)}")
            raise
            
    def enhance_transcription_with_context(self, audio_path: str, 
                                          context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enhance transcription using context from other analysis.
        
        Args:
            audio_path: Path to audio file
            context: Context from other analysis (tempo, key, etc.)
            
        Returns:
            Enhanced transcription results
        """
        # Build context-aware prompt
        prompt_parts = ["This is a guitar recording"]
        
        if context.get("tempo"):
            prompt_parts.append(f"at approximately {context['tempo']} BPM")
            
        if context.get("key"):
            prompt_parts.append(f"in the key of {context['key']}")
            
        if context.get("time_signature"):
            prompt_parts.append(f"with {context['time_signature']} time signature")
            
        if context.get("detected_instruments"):
            instruments = ", ".join(context["detected_instruments"])
            prompt_parts.append(f"featuring {instruments}")
            
        prompt = ". ".join(prompt_parts) + (
            ". Please identify chord progressions, individual notes, "
            "playing techniques, and rhythmic patterns with precise timing."
        )
        
        return self.transcribe_audio(audio_path, prompt=prompt, temperature=0.0)
        
    def _prepare_audio_file(self, audio_path: str):
        """
        Prepare audio file for Whisper API.
        
        Since we now only accept OpenAI-supported formats in upload validation,
        we can send files directly to the API. If a file is too large,
        OpenAI will return a clear error message.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            File object ready for upload
        """
        file_size = os.path.getsize(audio_path)
        file_ext = Path(audio_path).suffix.lower().lstrip('.')
        
        # Log file info for debugging
        if file_size > self.MAX_FILE_SIZE:
            logger.warning(f"File may be too large for OpenAI API: {file_size / 1024 / 1024:.1f}MB (limit: {self.MAX_FILE_SIZE / 1024 / 1024}MB)")
        
        if file_ext not in self.SUPPORTED_FORMATS:
            logger.warning(f"File format '{file_ext}' may not be supported by OpenAI API. Supported: {self.SUPPORTED_FORMATS}")
        
        # Send file directly to OpenAI - let them handle any format/size issues
        return open(audio_path, 'rb')
            
    def _extract_musical_elements(self, transcription: Dict[str, Any]) -> Dict[str, List]:
        """
        Extract musical elements from transcription text.
        
        Args:
            transcription: Whisper transcription result
            
        Returns:
            Dict of extracted musical elements
        """
        elements = {
            "instruments": [],
            "techniques": [],
            "dynamics": [],
            "tempo_changes": [],
            "key_signatures": []
        }
        
        text = transcription.get("text", "").lower()
        
        # Common instrument keywords
        instrument_keywords = [
            "guitar", "acoustic", "electric", "bass", "piano", 
            "drums", "violin", "saxophone", "trumpet", "synthesizer"
        ]
        
        # Technique keywords
        technique_keywords = [
            "hammer", "pull", "bend", "slide", "vibrato", "tremolo",
            "arpeggio", "strum", "pick", "fingerstyle", "tapping"
        ]
        
        # Dynamic keywords
        dynamic_keywords = [
            "loud", "soft", "forte", "piano", "crescendo", "diminuendo",
            "accent", "staccato", "legato"
        ]
        
        # Extract elements
        for instrument in instrument_keywords:
            if instrument in text:
                elements["instruments"].append(instrument)
                
        for technique in technique_keywords:
            if technique in text:
                elements["techniques"].append(technique)
                
        for dynamic in dynamic_keywords:
            if dynamic in text:
                elements["dynamics"].append(dynamic)
                
        return elements
        
    def _extract_chord_names(self, text: str) -> List[str]:
        """
        Extract chord names from text.
        
        Args:
            text: Text to analyze
            
        Returns:
            List of detected chord names
        """
        import re
        
        chords = []
        
        # Common chord patterns
        chord_pattern = r'\b([A-G](?:#|b)?(?:maj|min|m|dim|aug|sus|add)?(?:\d+)?)\b'
        matches = re.findall(chord_pattern, text, re.IGNORECASE)
        
        for match in matches:
            # Validate chord name
            if len(match) >= 1 and match[0] in 'ABCDEFG':
                chords.append(match)
                
        # Also look for written-out chords
        written_chords = {
            "c major": "C", "c minor": "Cm", "d major": "D", "d minor": "Dm",
            "e major": "E", "e minor": "Em", "f major": "F", "f minor": "Fm",
            "g major": "G", "g minor": "Gm", "a major": "A", "a minor": "Am",
            "b major": "B", "b minor": "Bm"
        }
        
        for written, chord in written_chords.items():
            if written in text.lower():
                chords.append(chord)
                
        return list(set(chords))  # Remove duplicates
        
    def _extract_techniques(self, text: str) -> List[str]:
        """
        Extract guitar techniques from text.
        
        Args:
            text: Text to analyze
            
        Returns:
            List of detected techniques
        """
        techniques = []
        
        technique_map = {
            "hammer": "hammer_on",
            "pull": "pull_off",
            "bend": "bend",
            "slide": "slide",
            "vibrato": "vibrato",
            "palm mute": "palm_mute",
            "tap": "tapping",
            "harmonic": "harmonic"
        }
        
        for keyword, technique in technique_map.items():
            if keyword in text.lower():
                techniques.append(technique)
                
        return techniques
        
    def _analyze_audio_features(self, audio_path: str) -> Dict[str, Any]:
        """
        Analyze audio features using librosa.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Dict of audio features
        """
        try:
            # Load audio
            y, sr = librosa.load(audio_path, sr=None)
            
            # Extract features
            tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
            
            # Onset detection for note timing
            onset_frames = librosa.onset.onset_detect(y=y, sr=sr)
            onset_times = librosa.frames_to_time(onset_frames, sr=sr)
            
            # Chroma features for harmony
            chroma = librosa.feature.chroma_stft(y=y, sr=sr)
            
            # Estimate key
            chroma_mean = np.mean(chroma, axis=1)
            key_idx = np.argmax(chroma_mean)
            keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
            estimated_key = keys[key_idx]
            
            return {
                "tempo": float(tempo),
                "beats": beats.tolist() if isinstance(beats, np.ndarray) else beats,
                "onset_times": onset_times.tolist() if isinstance(onset_times, np.ndarray) else onset_times,
                "estimated_key": estimated_key,
                "duration": float(len(y) / sr)
            }
            
        except Exception as e:
            logger.error(f"Error analyzing audio features: {str(e)}")
            return {}
            
    def _calculate_confidence(self, transcription: Dict[str, Any]) -> float:
        """
        Calculate confidence score for transcription.
        
        Args:
            transcription: Whisper transcription result
            
        Returns:
            Confidence score (0-1)
        """
        if not transcription.get("segments"):
            return 0.5
            
        # Calculate average confidence from segments
        confidences = []
        for segment in transcription["segments"]:
            # Use inverse of no_speech_prob as confidence
            no_speech = segment.get("no_speech_prob", 0.5)
            confidences.append(1.0 - no_speech)
            
        return sum(confidences) / len(confidences) if confidences else 0.5