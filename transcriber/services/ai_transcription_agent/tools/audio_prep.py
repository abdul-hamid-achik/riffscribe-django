"""
Audio Preparation Tool
Handles audio file preparation and chunking for AI processing
"""
import os
import logging
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)


class AudioPrepTool:
    """Tool for preparing audio files for AI processing"""
    
    def __init__(self, max_file_size: int = 25 * 1024 * 1024):
        self.max_file_size = max_file_size
        
    async def prepare(self, audio_path: str) -> str:
        """Prepare audio for AI processing"""
        file_size = os.path.getsize(audio_path)
        file_ext = os.path.splitext(audio_path)[1].lower()
        
        logger.info(f"Preparing audio: {file_size / 1024 / 1024:.1f}MB, format: {file_ext}")
        
        if file_size <= self.max_file_size:
            return audio_path
        
        logger.info(f"File size ({file_size / 1024 / 1024:.1f}MB) exceeds limit. Creating chunk.")
        return await self._create_chunk(audio_path)
    
    async def _create_chunk(self, audio_path: str) -> str:
        """Create a representative chunk from large audio file"""
        try:
            from pydub import AudioSegment
            
            audio = AudioSegment.from_file(audio_path)
            temp_dir = tempfile.gettempdir()
            chunk_path = os.path.join(temp_dir, f"chunk_{os.path.basename(audio_path)}")
            
            # Try different durations and qualities
            durations = [5 * 60 * 1000, 3 * 60 * 1000, 2 * 60 * 1000, 1 * 60 * 1000]
            bitrates = ["64k", "48k", "32k", "24k"]
            
            for duration_ms in durations:
                chunk_duration = min(len(audio), duration_ms)
                chunk = audio[:chunk_duration]
                
                for bitrate in bitrates:
                    try:
                        chunk.export(chunk_path, format="mp3", bitrate=bitrate)
                        chunk_size = os.path.getsize(chunk_path)
                        
                        if chunk_size < 24 * 1024 * 1024:  # 24MB buffer
                            logger.info(f"Created chunk: {chunk_size / 1024 / 1024:.1f}MB")
                            return chunk_path
                    except Exception:
                        continue
            
            # Fallback: minimal chunk
            minimal_chunk = audio[:30000]  # 30 seconds
            minimal_chunk.export(chunk_path, format="mp3", bitrate="16k")
            logger.info("Created minimal 30s chunk")
            return chunk_path
            
        except Exception as e:
            logger.error(f"Failed to create chunk: {e}")
            return audio_path