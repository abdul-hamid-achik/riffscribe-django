"""
Demucs Source Separation Tool
Isolates individual instruments from mixed audio
"""
import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


class DemucsTool:
    """Tool for Demucs source separation"""
    
    def __init__(self):
        self.model = None
        self.model_loaded = False
        self.separator = None
    
    def _ensure_model_loaded(self):
        """Lazy load Demucs model"""
        if not self.model_loaded:
            try:
                import demucs.separate
                from demucs.pretrained import get_model
                from demucs.apply import apply_model
                
                self.demucs_separate = demucs.separate
                self.get_model = get_model
                self.apply_model = apply_model
                self.model_loaded = True
                logger.info("Demucs model loaded successfully")
            except ImportError as e:
                logger.error(f"Demucs not available: {e}")
                raise ImportError("Install demucs: pip install demucs")
    
    async def separate(self, audio_path: str, 
                      model_name: str = "htdemucs",
                      device: str = "cpu",
                      shifts: int = 1) -> Dict[str, str]:
        """
        Separate audio into stems using Demucs
        
        Args:
            audio_path: Path to input audio file
            model_name: Demucs model to use (htdemucs, htdemucs_ft, htdemucs_6s)
            device: Device to run on (cpu, cuda, mps)
            shifts: Number of random shifts for better quality (1-5)
        
        Returns:
            Dictionary with paths to separated stems
        """
        logger.info(f"Starting Demucs separation for: {audio_path}")
        self._ensure_model_loaded()
        
        try:
            # Create output directory
            output_dir = tempfile.mkdtemp(prefix="demucs_")
            
            # Run separation
            stems = await self._run_separation(
                audio_path, 
                output_dir,
                model_name,
                device,
                shifts
            )
            
            logger.info(f"Demucs separation completed: {len(stems)} stems extracted")
            return stems
            
        except Exception as e:
            logger.error(f"Demucs separation failed: {e}")
            # Return original audio as fallback
            return {'mixed': audio_path}
    
    async def _run_separation(self, audio_path: str, output_dir: str,
                            model_name: str, device: str, shifts: int) -> Dict[str, str]:
        """Run the actual separation process"""
        import torch
        import torchaudio
        
        # Load model
        model = self.get_model(model_name)
        model.eval()
        
        if device == "cuda" and torch.cuda.is_available():
            model = model.cuda()
        elif device == "mps" and torch.backends.mps.is_available():
            model = model.to("mps")
        else:
            model = model.cpu()
        
        # Load audio
        wav, sr = torchaudio.load(audio_path)
        
        # Ensure stereo
        if wav.dim() == 1:
            wav = wav.unsqueeze(0)
        if wav.shape[0] == 1:
            wav = wav.repeat(2, 1)
        elif wav.shape[0] > 2:
            wav = wav[:2]  # Take first 2 channels
        
        # Resample if needed (Demucs expects 44.1kHz)
        if sr != model.samplerate:
            resampler = torchaudio.transforms.Resample(sr, model.samplerate)
            wav = resampler(wav)
        
        # Apply model with shifts for better quality
        with torch.no_grad():
            sources = self.apply_model(
                model, 
                wav.unsqueeze(0),
                shifts=shifts,
                device=device
            )[0]
        
        # Save separated sources
        stems = {}
        source_names = model.sources
        
        for idx, source_name in enumerate(source_names):
            stem_path = os.path.join(output_dir, f"{source_name}.wav")
            torchaudio.save(
                stem_path,
                sources[idx].cpu(),
                model.samplerate
            )
            stems[source_name] = stem_path
            logger.info(f"Saved {source_name} stem to: {stem_path}")
        
        return stems
    
    async def separate_guitar_optimized(self, audio_path: str) -> Dict[str, str]:
        """
        Separate with settings optimized for guitar extraction
        
        Returns paths to guitar and other stems
        """
        logger.info("Running guitar-optimized separation")
        
        # Use htdemucs_ft which is fine-tuned and better for guitars
        stems = await self.separate(
            audio_path,
            model_name="htdemucs_ft",  # Fine-tuned model
            device="cpu",  # Use CPU for stability
            shifts=2  # Balance between quality and speed
        )
        
        # Map Demucs outputs to guitar-relevant stems
        result = {}
        
        # Demucs typically outputs: drums, bass, other, vocals
        # "other" usually contains guitar
        if 'other' in stems:
            result['guitar'] = stems['other']
        
        # Also keep bass as it might contain low guitar notes
        if 'bass' in stems:
            result['bass'] = stems['bass']
        
        # Keep vocals in case of vocal guitar effects
        if 'vocals' in stems:
            result['vocals'] = stems['vocals']
        
        # Keep the mixed version as fallback
        result['mixed'] = audio_path
        
        return result
    
    async def extract_guitar_only(self, audio_path: str) -> str:
        """
        Extract only the guitar track from mixed audio
        
        Returns:
            Path to isolated guitar audio
        """
        stems = await self.separate_guitar_optimized(audio_path)
        
        # Return guitar stem if found, otherwise return original
        return stems.get('guitar', stems.get('mixed', audio_path))
    
    def cleanup_temp_files(self, stems: Dict[str, str]):
        """Clean up temporary stem files"""
        for stem_path in stems.values():
            if stem_path and os.path.exists(stem_path) and '/tmp/' in stem_path:
                try:
                    os.remove(stem_path)
                    logger.debug(f"Cleaned up: {stem_path}")
                except Exception as e:
                    logger.warning(f"Could not clean up {stem_path}: {e}")