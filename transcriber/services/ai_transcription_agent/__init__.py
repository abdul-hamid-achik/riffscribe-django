"""
AI Transcription Agent Service
Main orchestrator for spawning workers and managing transcription tasks
"""
import asyncio
import logging
import os
from typing import Dict, Optional, List
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .tools.audio_prep import AudioPrepTool
from .tools.whisper_tool import WhisperTool
from .tools.gpt_analysis import GPTAnalysisTool
from .tools.result_combiner import ResultCombinerTool, AIAnalysisResult

logger = logging.getLogger(__name__)


@dataclass
class WorkerTask:
    """Represents a worker task"""
    task_id: str
    task_type: str
    audio_path: str
    status: str = "pending"
    result: Optional[Dict] = None
    error: Optional[str] = None


class AITranscriptionService:
    """
    Main AI Transcription Service
    Spawns workers, manages tasks, and provides self-checking capabilities
    """
    
    def __init__(self, api_key: Optional[str] = None):
        from django.conf import settings
        
        self.api_key = api_key or getattr(settings, 'OPENAI_API_KEY', '')
        if not self.api_key:
            raise ValueError("OpenAI API key is required")
        
        # Initialize tools
        self.audio_prep = AudioPrepTool()
        self.whisper_tool = WhisperTool(self.api_key)
        self.gpt_tool = GPTAnalysisTool(self.api_key)
        self.combiner = ResultCombinerTool()
        
        # Worker management
        self.executor = ThreadPoolExecutor(max_workers=3)
        self.active_tasks: Dict[str, WorkerTask] = {}
        
        logger.info("AI Transcription Service initialized")
    
    async def transcribe_audio(self, audio_path: str, task_id: Optional[str] = None) -> AIAnalysisResult:
        """Main transcription method with worker spawning"""
        task_id = task_id or f"task_{len(self.active_tasks)}"
        
        logger.info(f"Starting transcription task {task_id} for: {audio_path}")
        
        # Create task
        task = WorkerTask(
            task_id=task_id,
            task_type="transcription",
            audio_path=audio_path
        )
        self.active_tasks[task_id] = task
        
        try:
            # Spawn workers for different parts
            prepared_audio = await self._spawn_audio_prep_worker(task)
            
            # Spawn parallel workers for whisper and gpt analysis
            whisper_task = asyncio.create_task(self._spawn_whisper_worker(task, prepared_audio))
            gpt_task = asyncio.create_task(self._spawn_gpt_worker(task, prepared_audio))
            
            # Wait for both workers
            whisper_result, gpt_result = await asyncio.gather(whisper_task, gpt_task)
            
            # Get actual audio duration
            actual_duration = self._get_audio_duration(audio_path)
            
            # Combine results with actual duration
            result = self.combiner.combine(whisper_result, gpt_result, duration=actual_duration)
            
            # Self-check the result
            if await self._self_check_result(result):
                task.status = "completed"
                task.result = result.__dict__
                logger.info(f"Task {task_id} completed successfully")
            else:
                logger.warning(f"Task {task_id} failed self-check, but proceeding")
                task.status = "completed_with_warnings"
                task.result = result.__dict__
            
            return result
            
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            logger.error(f"Task {task_id} failed: {e}")
            raise
        finally:
            # Cleanup
            if prepared_audio != audio_path and os.path.exists(prepared_audio):
                os.remove(prepared_audio)
    
    async def _spawn_audio_prep_worker(self, task: WorkerTask) -> str:
        """Spawn worker for audio preparation"""
        logger.info(f"Spawning audio prep worker for task {task.task_id}")
        return await self.audio_prep.prepare(task.audio_path)
    
    async def _spawn_whisper_worker(self, task: WorkerTask, audio_path: str) -> Dict:
        """Spawn worker for Whisper transcription"""
        logger.info(f"Spawning Whisper worker for task {task.task_id}")
        return await self.whisper_tool.transcribe(audio_path)
    
    async def _spawn_gpt_worker(self, task: WorkerTask, audio_path: str) -> Dict:
        """Spawn worker for GPT analysis"""
        logger.info(f"Spawning GPT analysis worker for task {task.task_id}")
        return await self.gpt_tool.analyze(audio_path)
    
    async def _self_check_result(self, result: AIAnalysisResult) -> bool:
        """Self-check the transcription result quality"""
        logger.info("Running self-check on transcription result...")
        
        checks = []
        
        # Check if we have notes
        checks.append(len(result.notes) > 0)
        
        # Check if tempo is reasonable
        checks.append(60 <= result.tempo <= 200)
        
        # Check if confidence is reasonable
        checks.append(result.confidence > 0.3)
        
        # Check if we have instruments detected
        checks.append(len(result.instruments) > 0)
        
        # Check if complexity is valid
        checks.append(result.complexity in ['simple', 'moderate', 'complex'])
        
        passed_checks = sum(checks)
        total_checks = len(checks)
        
        logger.info(f"Self-check passed {passed_checks}/{total_checks} tests")
        return passed_checks >= (total_checks * 0.6)  # 60% pass rate
    
    def get_task_status(self, task_id: str) -> Optional[WorkerTask]:
        """Get status of a specific task"""
        return self.active_tasks.get(task_id)
    
    def get_all_tasks(self) -> List[WorkerTask]:
        """Get all tasks"""
        return list(self.active_tasks.values())
    
    def cleanup_completed_tasks(self):
        """Clean up completed tasks to free memory"""
        completed_tasks = [
            task_id for task_id, task in self.active_tasks.items() 
            if task.status in ["completed", "failed", "completed_with_warnings"]
        ]
        
        for task_id in completed_tasks:
            del self.active_tasks[task_id]
        
        logger.info(f"Cleaned up {len(completed_tasks)} completed tasks")
    
    def _get_audio_duration(self, audio_path: str) -> float:
        """Get actual audio duration using librosa with fallback"""
        try:
            import librosa
            duration = librosa.get_duration(path=audio_path)
            logger.info(f"Actual audio duration: {duration:.1f}s")
            return duration
        except Exception as e:
            logger.warning(f"Could not get actual duration with librosa: {e}, falling back to file size estimation")
            # Fallback to file size estimation
            try:
                file_size = os.path.getsize(audio_path)
                file_ext = os.path.splitext(audio_path)[1].lower()
                
                # Rough estimates based on typical bitrates (in bytes per second)
                bitrate_estimates = {
                    '.mp3': 16000,   # ~128kbps
                    '.wav': 176400,  # ~1.4Mbps uncompressed
                    '.m4a': 16000,   # ~128kbps
                    '.mp4': 16000,   # ~128kbps
                    '.flac': 100000, # ~800kbps lossless
                    '.ogg': 16000,   # ~128kbps
                    '.webm': 16000,  # ~128kbps
                }
                
                bytes_per_second = bitrate_estimates.get(file_ext, 20000)  # Default
                estimated_duration = file_size / bytes_per_second
                
                # Reasonable bounds (5 seconds to 20 minutes)
                estimated_duration = max(5.0, min(estimated_duration, 1200.0))
                
                logger.info(f"Estimated duration: {estimated_duration:.1f}s based on file size")
                return estimated_duration
            except Exception as e:
                logger.warning(f"Could not estimate duration: {str(e)}, using default")
                return 60.0  # Default fallback


# Clean new implementation - no legacy dependencies

# Main service instance
transcription_service = None

def get_transcription_service(api_key: Optional[str] = None) -> AITranscriptionService:
    """Get or create the main transcription service instance"""
    global transcription_service
    if transcription_service is None:
        transcription_service = AITranscriptionService(api_key)
    return transcription_service


# Export main service and result type
__all__ = [
    'AITranscriptionService',
    'AIAnalysisResult', 
    'WorkerTask',
    'get_transcription_service'
]