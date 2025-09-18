"""
Whisper Transcription Tool
Handles OpenAI Whisper API calls for audio transcription with audio preprocessing
"""
import asyncio
import logging
import os
import tempfile
from typing import Dict, Optional
from pathlib import Path
from openai import OpenAI
import librosa
import soundfile as sf

logger = logging.getLogger(__name__)


class WhisperTool:
    """Tool for Whisper transcription with audio preprocessing"""

    # Whisper model options
    MODEL_WHISPER_1 = "whisper-1"

    # Maximum file size for Whisper API (25MB)
    MAX_FILE_SIZE = 25 * 1024 * 1024

    # Supported audio formats
    SUPPORTED_FORMATS = ['mp3', 'mp4', 'mpeg', 'mpga', 'm4a', 'wav', 'webm']

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("OpenAI API key is required")
        self.client = OpenAI(api_key=api_key)
        self.api_key = api_key
        self.model = self.MODEL_WHISPER_1

    async def transcribe(self, audio_path: str,
                        language: Optional[str] = None,
                        prompt: Optional[str] = None,
                        temperature: float = 0.0) -> Dict:
        """
        Transcribe audio using Whisper with preprocessing.

        Args:
            audio_path: Path to audio file
            language: Optional language code (e.g., 'en')
            prompt: Optional prompt to guide transcription
            temperature: Sampling temperature (0-1)
        """
        logger.info(f"Starting Whisper transcription for: {audio_path}")

        try:
            # Validate and prepare audio file
            audio_file_path = await self._prepare_audio_file(audio_path)

            # Prepare transcription parameters
            params = {
                "model": self.MODEL_WHISPER_1,
                "response_format": "verbose_json",
                "timestamp_granularities": ["word", "segment"],
                "temperature": temperature
            }

            if language:
                params["language"] = language

            if prompt:
                params["prompt"] = prompt

            # Call Whisper API
            with open(audio_file_path, 'rb') as audio_file:
                response = await asyncio.to_thread(
                    self.client.audio.transcriptions.create,
                    file=audio_file,
                    **params
                )

            # Clean up temporary file if created
            if audio_file_path != audio_path and os.path.exists(audio_file_path):
                os.unlink(audio_file_path)

            result = {
                'text': response.text,
                'segments': getattr(response, 'segments', []),
                'words': getattr(response, 'words', []),
                'language': getattr(response, 'language', 'unknown'),
                'duration': getattr(response, 'duration', 0.0)
            }

            logger.info(f"Whisper transcription completed: {len(result['text'])} characters")
            return result

        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            raise

    async def _prepare_audio_file(self, audio_path: str) -> str:
        """
        Prepare audio file for Whisper API.
        Handles file size limits and format conversion.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        file_size = os.path.getsize(audio_path)
        file_ext = Path(audio_path).suffix.lower().lstrip('.')

        # Check if file is within size limit and supported format
        if file_size <= self.MAX_FILE_SIZE and file_ext in self.SUPPORTED_FORMATS:
            return audio_path

        # Need to preprocess the file
        logger.info(f"Preprocessing audio file (size: {file_size / 1024 / 1024:.1f}MB)")

        # Load audio with librosa
        try:
            y, sr = librosa.load(audio_path, sr=None, mono=False)
        except Exception as e:
            raise ValueError(f"Failed to load audio file: {e}")

        # Convert to mono if stereo (reduces file size)
        if y.ndim > 1:
            y = librosa.to_mono(y)

        # If still too large, reduce sample rate
        if file_size > self.MAX_FILE_SIZE:
            target_sr = min(sr, 22050)  # Reduce to 22kHz max
            if target_sr < sr:
                y = librosa.resample(y, orig_sr=sr, target_sr=target_sr)
                sr = target_sr
                logger.info(f"Reduced sample rate to {sr}Hz")

        # Save to temporary WAV file
        temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        temp_file.close()

        try:
            sf.write(temp_file.name, y, sr)
            new_size = os.path.getsize(temp_file.name)
            logger.info(f"Created preprocessed file: {new_size / 1024 / 1024:.1f}MB")

            if new_size > self.MAX_FILE_SIZE:
                raise ValueError(f"File still too large after preprocessing: {new_size / 1024 / 1024:.1f}MB")

            return temp_file.name

        except Exception as e:
            # Clean up on error
            if os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
            raise ValueError(f"Failed to preprocess audio: {e}")

    def is_file_supported(self, audio_path: str) -> bool:
        """Check if audio file is supported by Whisper."""
        if not os.path.exists(audio_path):
            return False

        file_size = os.path.getsize(audio_path)
        file_ext = Path(audio_path).suffix.lower().lstrip('.')

        return file_ext in self.SUPPORTED_FORMATS and file_size <= self.MAX_FILE_SIZE * 2  # Allow some preprocessing headroom