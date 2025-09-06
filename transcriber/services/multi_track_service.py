"""
Multi-track audio separation service using Demucs v4.
Handles source separation, track analysis, and multi-track transcription.
"""

import os
import logging
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
import librosa
import soundfile as sf
import torch
from django.conf import settings
from django.core.files.base import ContentFile

try:
    from demucs import pretrained
    from demucs.apply import apply_model
    from demucs.audio import convert_audio
    demucs = True  # Set to True if imports succeed
except ImportError:
    demucs = None

from ..models import Track, Transcription
from .whisper_service import WhisperService
from .drum_transcriber import DrumTranscriber

logger = logging.getLogger(__name__)


class MultiTrackService:
    """
    Service for multi-track audio processing using Demucs source separation.
    """
    
    # Demucs v4 model outputs these 4 stems
    DEMUCS_STEMS = ['drums', 'bass', 'other', 'vocals']
    
    # Default model name (htdemucs_ft uses fine-tuned transformers)
    DEFAULT_MODEL = 'htdemucs_ft'
    
    def __init__(self, model_name: str = None, use_gpu: bool = True):
        """
        Initialize the multi-track service.
        
        Args:
            model_name: Demucs model to use (default: htdemucs_ft)
            use_gpu: Whether to use GPU acceleration
        """
        self.model_name = model_name or self.DEFAULT_MODEL
        self.device = 'cuda' if use_gpu and torch.cuda.is_available() else 'cpu'
        self.model = None
        
        # Initialize Whisper service for enhanced analysis
        self.whisper_service = None
        if getattr(settings, 'USE_WHISPER', False) and getattr(settings, 'OPENAI_API_KEY', ''):
            try:
                self.whisper_service = WhisperService(
                    api_key=settings.OPENAI_API_KEY
                )
            except Exception as e:
                logger.warning(f"Failed to initialize Whisper service: {str(e)}")
                self.whisper_service = None
        
        # Initialize drum transcriber
        self.drum_transcriber = DrumTranscriber()
    
    def _load_model(self) -> None:
        """Load the Demucs model if not already loaded."""
        if not demucs:
            raise RuntimeError("Demucs not installed. Run: pip install demucs")
        
        if self.model is None:
            logger.info(f"Loading Demucs model: {self.model_name}")
            try:
                self.model = pretrained.get_model(self.model_name)
                self.model.to(self.device)
                self.model.eval()
                logger.info(f"Demucs model loaded successfully on {self.device}")
            except Exception as e:
                logger.error(f"Failed to load Demucs model: {str(e)}")
                raise
    
    def separate_audio(self, audio_path: str, output_dir: Optional[str] = None) -> Dict[str, str]:
        """
        Separate audio into individual tracks using Demucs.
        
        Args:
            audio_path: Path to the audio file to separate
            output_dir: Directory to save separated tracks (optional, creates temp dir)
            
        Returns:
            Dict mapping track names to file paths
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        self._load_model()
        
        # Create output directory
        if output_dir is None:
            output_dir = tempfile.mkdtemp(prefix='demucs_separation_')
        else:
            os.makedirs(output_dir, exist_ok=True)
        
        try:
            logger.info(f"Separating audio: {audio_path}")
            
            # Load and preprocess audio
            wav, sr = librosa.load(audio_path, sr=self.model.samplerate, mono=False)
            
            # Convert to stereo if mono
            if len(wav.shape) == 1:
                wav = np.stack([wav, wav])
            elif wav.shape[0] == 1:
                wav = np.repeat(wav, 2, axis=0)
            
            # Convert to torch tensor
            wav_tensor = torch.from_numpy(wav).float().unsqueeze(0).to(self.device)
            
            # Apply source separation
            logger.info("Running Demucs source separation...")
            with torch.no_grad():
                sources = apply_model(self.model, wav_tensor, device=self.device, progress=True)[0]
            
            # Save separated tracks
            separated_files = {}
            for i, stem_name in enumerate(self.DEMUCS_STEMS):
                stem_audio = sources[i].cpu().numpy()
                
                # Save as WAV file
                stem_path = os.path.join(output_dir, f"{stem_name}.wav")
                sf.write(stem_path, stem_audio.T, self.model.samplerate)
                separated_files[stem_name] = stem_path
                
                logger.info(f"Saved {stem_name} track: {stem_path}")
            
            # Also save the original mix
            original_path = os.path.join(output_dir, "original.wav")
            shutil.copy2(audio_path, original_path)
            separated_files['original'] = original_path
            
            logger.info(f"Source separation completed. Output directory: {output_dir}")
            return separated_files
            
        except Exception as e:
            logger.error(f"Source separation failed: {str(e)}")
            # Clean up on failure
            if output_dir and os.path.exists(output_dir):
                shutil.rmtree(output_dir, ignore_errors=True)
            raise
    
    def analyze_track_prominence(self, separated_files: Dict[str, str]) -> Dict[str, float]:
        """
        Analyze the prominence/volume level of each separated track.
        
        Args:
            separated_files: Dict mapping track names to file paths
            
        Returns:
            Dict mapping track names to prominence scores (0-1)
        """
        prominence_scores = {}
        
        for track_name, file_path in separated_files.items():
            if track_name == 'original':
                continue
                
            try:
                # Load audio and calculate RMS
                audio, _ = librosa.load(file_path, sr=22050)
                rms = np.sqrt(np.mean(audio ** 2))
                
                # Normalize to 0-1 scale (typical RMS range is 0-0.3 for music)
                prominence = min(rms / 0.3, 1.0)
                prominence_scores[track_name] = float(prominence)
                
                logger.debug(f"{track_name} prominence: {prominence:.3f}")
                
            except Exception as e:
                logger.warning(f"Failed to analyze prominence for {track_name}: {str(e)}")
                prominence_scores[track_name] = 0.0
        
        return prominence_scores
    
    def classify_track_instruments(self, separated_files: Dict[str, str]) -> Dict[str, str]:
        """
        Classify the instrument type for each track using audio analysis.
        
        Args:
            separated_files: Dict mapping track names to file paths
            
        Returns:
            Dict mapping track names to instrument classifications
        """
        instrument_classifications = {}
        
        for track_name, file_path in separated_files.items():
            if track_name == 'original':
                continue
            
            # Default mapping based on Demucs stem names
            default_mapping = {
                'drums': 'drums',
                'bass': 'bass',
                'vocals': 'vocals',
                'other': 'electric_guitar'  # Assume guitar for "other" category
            }
            
            # Start with default classification
            instrument_type = default_mapping.get(track_name, 'other')
            
            try:
                # Enhanced classification using Whisper if available
                if self.whisper_service and track_name in ['other', 'bass']:
                    result = self.whisper_service.analyze_music(file_path)
                    
                    if result['status'] == 'success' and 'analysis' in result:
                        analysis_text = result['analysis'].lower()
                        
                        # Look for instrument mentions in Whisper analysis
                        if 'guitar' in analysis_text:
                            if 'acoustic' in analysis_text:
                                instrument_type = 'acoustic_guitar'
                            elif 'electric' in analysis_text:
                                instrument_type = 'electric_guitar'
                            else:
                                instrument_type = 'electric_guitar'
                        elif 'piano' in analysis_text or 'keyboard' in analysis_text:
                            instrument_type = 'piano'
                        elif 'synth' in analysis_text:
                            instrument_type = 'synthesizer'
                        elif 'strings' in analysis_text and 'violin' in analysis_text:
                            instrument_type = 'strings'
                
                # Spectral analysis for additional classification hints
                audio, sr = librosa.load(file_path, sr=22050)
                
                # Analyze frequency content
                S = np.abs(librosa.stft(audio))
                freqs = librosa.fft_frequencies(sr=sr)
                
                # Calculate spectral centroid (brightness)
                spectral_centroid = librosa.feature.spectral_centroid(S=S)[0]
                avg_brightness = np.mean(spectral_centroid)
                
                # Refine classification based on spectral features
                if track_name == 'other':
                    if avg_brightness > 3000:  # Bright sound, likely guitar
                        if instrument_type == 'other':
                            instrument_type = 'electric_guitar'
                    elif avg_brightness < 1000:  # Dark sound, could be bass or low instruments
                        if instrument_type == 'other':
                            instrument_type = 'bass'
                
                instrument_classifications[track_name] = instrument_type
                logger.debug(f"{track_name} classified as: {instrument_type}")
                
            except Exception as e:
                logger.warning(f"Classification failed for {track_name}: {str(e)}")
                instrument_classifications[track_name] = default_mapping.get(track_name, 'other')
        
        return instrument_classifications
    
    def create_track_objects(
        self, 
        transcription: Transcription, 
        separated_files: Dict[str, str],
        prominence_scores: Dict[str, float],
        instrument_classifications: Dict[str, str]
    ) -> List[Track]:
        """
        Create Track model objects from separated audio files.
        
        Args:
            transcription: Parent Transcription object
            separated_files: Dict mapping track names to file paths
            prominence_scores: Prominence scores for each track
            instrument_classifications: Instrument classifications
            
        Returns:
            List of created Track objects
        """
        created_tracks = []
        track_order = 0
        
        # Define preferred order for track display
        track_order_map = {
            'drums': 0,
            'bass': 1, 
            'other': 2,
            'vocals': 3,
            'original': 4
        }
        
        for track_name, file_path in separated_files.items():
            try:
                # Read audio file
                with open(file_path, 'rb') as f:
                    audio_content = f.read()
                
                # Create Track object
                track = Track(
                    transcription=transcription,
                    track_type=track_name,
                    track_order=track_order_map.get(track_name, 999),
                    volume_level=prominence_scores.get(track_name, 0.0),
                    prominence_score=prominence_scores.get(track_name, 0.0),
                )
                
                # Set instrument type if available
                if track_name in instrument_classifications:
                    track.instrument_type = instrument_classifications[track_name]
                
                # Save audio file to model
                filename = f"{transcription.filename}_{track_name}.wav"
                track.separated_audio.save(
                    filename,
                    ContentFile(audio_content),
                    save=False
                )
                
                track.save()
                created_tracks.append(track)
                
                logger.info(f"Created track: {track}")
                
            except Exception as e:
                logger.error(f"Failed to create track for {track_name}: {str(e)}")
        
        return created_tracks
    
    def process_transcription(
        self, 
        transcription: Transcription, 
        cleanup_temp_files: bool = True
    ) -> List[Track]:
        """
        Complete multi-track processing pipeline.
        
        Args:
            transcription: Transcription object to process
            cleanup_temp_files: Whether to clean up temporary files
            
        Returns:
            List of created Track objects
        """
        if not transcription.original_audio:
            raise ValueError("Transcription has no audio file")
        
        temp_dir = None
        try:
            logger.info(f"Starting multi-track processing for: {transcription.filename}")
            
            # Step 1: Separate audio
            separated_files = self.separate_audio(transcription.original_audio.path)
            temp_dir = os.path.dirname(list(separated_files.values())[0])
            
            # Step 2: Analyze track prominence
            prominence_scores = self.analyze_track_prominence(separated_files)
            
            # Step 3: Classify instruments
            instrument_classifications = self.classify_track_instruments(separated_files)
            
            # Step 4: Create Track objects
            tracks = self.create_track_objects(
                transcription,
                separated_files,
                prominence_scores,
                instrument_classifications
            )
            
            # Step 5: Process drum track if present
            drum_track = next((t for t in tracks if t.track_type == 'drums'), None)
            if drum_track and drum_track.separated_audio:
                try:
                    self.process_drum_track(drum_track)
                except Exception as e:
                    logger.error(f"Drum processing failed: {str(e)}")
            
            logger.info(f"Multi-track processing completed. Created {len(tracks)} tracks.")
            return tracks
            
        except Exception as e:
            logger.error(f"Multi-track processing failed: {str(e)}")
            raise
        finally:
            # Clean up temporary files
            if cleanup_temp_files and temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.debug(f"Cleaned up temporary directory: {temp_dir}")
    
    def process_drum_track(self, drum_track: Track) -> None:
        """
        Process a drum track to extract drum patterns and notation.
        
        Args:
            drum_track: Track object containing drum audio
        """
        logger.info(f"Processing drum track: {drum_track}")
        
        try:
            # Get path to drum audio file
            audio_path = drum_track.separated_audio.path
            
            # Transcribe drums
            drum_data = self.drum_transcriber.transcribe(audio_path)
            
            if 'error' in drum_data:
                logger.error(f"Drum transcription error: {drum_data['error']}")
                return
            
            # Store drum-specific data
            drum_track.midi_data = {
                'tempo': drum_data['tempo'],
                'drum_hits': drum_data['drum_hits'],
                'measures': drum_data['measures']
            }
            
            # Store patterns and notation
            drum_track.chord_progressions = {
                'patterns': drum_data['patterns'],
                'notation': drum_data['notation'],
                'fills': drum_data['patterns'].get('fills', [])
            }
            
            # Generate and store drum tab
            if drum_data.get('drum_hits'):
                drum_tab = self.drum_transcriber.generate_drum_tab(
                    drum_data['drum_hits'],
                    drum_data['tempo']
                )
                drum_track.guitar_notes = {
                    'drum_tab': drum_tab,
                    'format': 'drum_notation',
                    'measures': drum_data['measures']
                }
            
            drum_track.is_processed = True
            drum_track.save()
            
            logger.info(f"Drum track processed successfully. Found {len(drum_data.get('drum_hits', []))} hits")
            
        except Exception as e:
            logger.error(f"Failed to process drum track: {str(e)}")
            drum_track.processing_error = str(e)
            drum_track.save()
    
    def get_model_info(self) -> Dict[str, str]:
        """Get information about the loaded model."""
        return {
            'model_name': self.model_name,
            'device': self.device,
            'stems': self.DEMUCS_STEMS,
            'loaded': self.model is not None
        }