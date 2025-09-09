"""
Whisper Transcription Tool
Handles OpenAI Whisper API calls for audio transcription
"""
import asyncio
import logging
from typing import Dict
from openai import OpenAI

logger = logging.getLogger(__name__)


class WhisperTool:
    """Tool for Whisper transcription"""
    
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)
    
    async def transcribe(self, audio_path: str) -> Dict:
        """Transcribe audio using Whisper"""
        logger.info("Starting Whisper transcription...")
        
        try:
            with open(audio_path, 'rb') as audio_file:
                response = await asyncio.to_thread(
                    self.client.audio.transcriptions.create,
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["word", "segment"]
                )
            
            result = {
                'text': response.text,
                'segments': response.segments,
                'words': getattr(response, 'words', []),
                'language': response.language,
                'duration': response.duration
            }
            
            logger.info("Whisper transcription completed")
            return result
            
        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            raise