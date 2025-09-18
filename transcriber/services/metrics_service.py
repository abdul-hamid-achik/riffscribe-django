"""
Metrics and Monitoring Service
Tracks transcription performance, success rates, and system health
"""
import time
import logging
import json
from typing import Dict, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from django.core.cache import cache
from django.conf import settings
import psutil

logger = logging.getLogger(__name__)


@dataclass
class TaskMetrics:
    """Metrics for a single task execution"""
    task_id: str
    task_type: str
    instrument: Optional[str]
    start_time: float
    end_time: Optional[float]
    duration: Optional[float]
    status: str  # 'started', 'success', 'failed'
    error_type: Optional[str]
    memory_peak_mb: Optional[float]
    transcription_id: str


@dataclass
class InstrumentStats:
    """Statistics for a specific instrument"""
    instrument: str
    total_attempts: int
    successful: int
    failed: int
    avg_duration: float
    avg_confidence: float
    success_rate: float


class MetricsService:
    """Service for collecting and analyzing transcription metrics"""
    
    CACHE_PREFIX = "metrics:"
    METRICS_RETENTION_HOURS = 24
    
    def __init__(self):
        self.start_time = time.time()
    
    def start_task_metrics(self, task_id: str, task_type: str, 
                          instrument: Optional[str] = None, 
                          transcription_id: str = None) -> TaskMetrics:
        """Start tracking metrics for a task"""
        metrics = TaskMetrics(
            task_id=task_id,
            task_type=task_type,
            instrument=instrument,
            start_time=time.time(),
            end_time=None,
            duration=None,
            status='started',
            error_type=None,
            memory_peak_mb=self._get_memory_usage(),
            transcription_id=transcription_id or 'unknown'
        )
        
        # Store in cache
        cache_key = f"{self.CACHE_PREFIX}task:{task_id}"
        cache.set(cache_key, asdict(metrics), timeout=3600 * self.METRICS_RETENTION_HOURS)
        
        logger.info(f"Started metrics tracking for task {task_id} ({task_type})")
        return metrics
    
    def complete_task_metrics(self, task_id: str, status: str = 'success', 
                             error_type: Optional[str] = None, 
                             additional_data: Optional[Dict] = None):
        """Complete metrics tracking for a task"""
        cache_key = f"{self.CACHE_PREFIX}task:{task_id}"
        metrics_data = cache.get(cache_key)
        
        if not metrics_data:
            logger.warning(f"No metrics found for task {task_id}")
            return
        
        # Update metrics
        end_time = time.time()
        metrics_data.update({
            'end_time': end_time,
            'duration': end_time - metrics_data['start_time'],
            'status': status,
            'error_type': error_type,
            'memory_peak_mb': max(metrics_data.get('memory_peak_mb', 0), self._get_memory_usage())
        })
        
        if additional_data:
            metrics_data.update(additional_data)
        
        # Update cache
        cache.set(cache_key, metrics_data, timeout=3600 * self.METRICS_RETENTION_HOURS)
        
        # Update aggregated stats
        self._update_aggregate_stats(metrics_data)
        
        logger.info(f"Completed metrics for task {task_id}: {status} in {metrics_data['duration']:.2f}s")
    
    def get_task_metrics(self, task_id: str) -> Optional[Dict]:
        """Get metrics for a specific task"""
        cache_key = f"{self.CACHE_PREFIX}task:{task_id}"
        return cache.get(cache_key)
    
    def get_instrument_stats(self, instrument: str, hours: int = 24) -> Optional[InstrumentStats]:
        """Get aggregated statistics for an instrument"""
        cache_key = f"{self.CACHE_PREFIX}instrument:{instrument}:{hours}h"
        stats_data = cache.get(cache_key)
        
        if not stats_data:
            return None
        
        return InstrumentStats(**stats_data)
    
    def get_system_health(self) -> Dict[str, Any]:
        """Get current system health metrics"""
        try:
            memory = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent(interval=1)
            disk = psutil.disk_usage('/')
            
            return {
                'timestamp': datetime.now().isoformat(),
                'memory': {
                    'total_gb': memory.total / (1024**3),
                    'available_gb': memory.available / (1024**3),
                    'used_percent': memory.percent
                },
                'cpu': {
                    'usage_percent': cpu_percent,
                    'cores': psutil.cpu_count()
                },
                'disk': {
                    'total_gb': disk.total / (1024**3),
                    'free_gb': disk.free / (1024**3),
                    'used_percent': (disk.used / disk.total) * 100
                },
                'uptime_hours': (time.time() - self.start_time) / 3600
            }
        except Exception as e:
            logger.error(f"Failed to get system health: {e}")
            return {'error': str(e)}
    
    def get_transcription_progress(self, transcription_id: str) -> Dict[str, Any]:
        """Get detailed progress for a multi-track transcription"""
        progress_key = f"{self.CACHE_PREFIX}progress:{transcription_id}"
        progress_data = cache.get(progress_key, {})
        
        # Calculate overall progress
        if not progress_data:
            return {'overall': 0, 'status': 'not_started'}
        
        stages = ['separation', 'guitar', 'bass', 'drums', 'vocals', 'combining', 'exports']
        completed_stages = sum(1 for stage in stages if progress_data.get(stage, 0) >= 100)
        overall_progress = (completed_stages / len(stages)) * 100
        
        return {
            'overall': int(overall_progress),
            'stages': progress_data,
            'status': self._determine_status(progress_data),
            'estimated_completion': self._estimate_completion(progress_data)
        }
    
    def update_transcription_progress(self, transcription_id: str, 
                                    stage: str, progress: int, 
                                    status: Optional[str] = None):
        """Update progress for a specific stage"""
        progress_key = f"{self.CACHE_PREFIX}progress:{transcription_id}"
        progress_data = cache.get(progress_key, {})
        
        progress_data[stage] = progress
        if status:
            progress_data[f"{stage}_status"] = status
        
        progress_data['last_updated'] = time.time()
        
        cache.set(progress_key, progress_data, timeout=3600 * 2)  # 2 hour timeout
        
        logger.debug(f"Updated progress for {transcription_id}: {stage} = {progress}%")
    
    def get_openai_usage_stats(self) -> Dict[str, Any]:
        """Get OpenAI API usage statistics"""
        usage_key = f"{self.CACHE_PREFIX}openai_usage"
        usage_data = cache.get(usage_key, {
            'requests_today': 0,
            'requests_this_month': 0,
            'estimated_cost_today': 0.0,
            'estimated_cost_this_month': 0.0,
            'rate_limit_hits': 0,
            'last_reset_date': datetime.now().date().isoformat()
        })
        
        # Reset daily counters if needed
        today = datetime.now().date().isoformat()
        if usage_data.get('last_reset_date') != today:
            usage_data.update({
                'requests_today': 0,
                'estimated_cost_today': 0.0,
                'last_reset_date': today
            })
            cache.set(usage_key, usage_data, timeout=3600 * 24 * 32)  # 32 days
        
        return usage_data
    
    def track_openai_request(self, model: str, tokens_used: int, cost: float):
        """Track an OpenAI API request"""
        usage_key = f"{self.CACHE_PREFIX}openai_usage"
        usage_data = self.get_openai_usage_stats()
        
        usage_data['requests_today'] += 1
        usage_data['requests_this_month'] += 1
        usage_data['estimated_cost_today'] += cost
        usage_data['estimated_cost_this_month'] += cost
        
        cache.set(usage_key, usage_data, timeout=3600 * 24 * 32)
        
        # Check if we're approaching limits
        if usage_data['estimated_cost_this_month'] > settings.OPENAI_MONTHLY_BUDGET_LIMIT * 0.9:
            logger.warning(f"Approaching OpenAI monthly budget limit: ${usage_data['estimated_cost_this_month']:.2f}")
    
    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB"""
        try:
            process = psutil.Process()
            return process.memory_info().rss / (1024 * 1024)  # Convert to MB
        except:
            return 0.0
    
    def _update_aggregate_stats(self, metrics_data: Dict):
        """Update aggregated statistics"""
        if not metrics_data.get('instrument'):
            return
        
        instrument = metrics_data['instrument']
        stats_key = f"{self.CACHE_PREFIX}instrument:{instrument}:24h"
        
        # Get existing stats or create new ones
        stats = cache.get(stats_key, {
            'instrument': instrument,
            'total_attempts': 0,
            'successful': 0,
            'failed': 0,
            'total_duration': 0.0,
            'total_confidence': 0.0,
            'avg_duration': 0.0,
            'avg_confidence': 0.0,
            'success_rate': 0.0
        })
        
        # Update stats
        stats['total_attempts'] += 1
        if metrics_data['status'] == 'success':
            stats['successful'] += 1
            if metrics_data.get('duration'):
                stats['total_duration'] += metrics_data['duration']
            if metrics_data.get('confidence'):
                stats['total_confidence'] += metrics_data['confidence']
        else:
            stats['failed'] += 1
        
        # Calculate averages
        if stats['successful'] > 0:
            stats['avg_duration'] = stats['total_duration'] / stats['successful']
            stats['avg_confidence'] = stats['total_confidence'] / stats['successful']
        
        stats['success_rate'] = (stats['successful'] / stats['total_attempts']) * 100
        
        cache.set(stats_key, stats, timeout=3600 * 25)  # 25 hours
    
    def _determine_status(self, progress_data: Dict) -> str:
        """Determine overall status from progress data"""
        if not progress_data:
            return 'not_started'
        
        if progress_data.get('separation', 0) > 0:
            if progress_data.get('exports', 0) >= 100:
                return 'completed'
            elif any(progress_data.get(f'{stage}_status') == 'failed' 
                    for stage in ['separation', 'guitar', 'bass', 'drums', 'vocals']):
                return 'partially_failed'
            else:
                return 'processing'
        
        return 'starting'
    
    def _estimate_completion(self, progress_data: Dict) -> Optional[str]:
        """Estimate completion time based on progress"""
        if not progress_data or not progress_data.get('last_updated'):
            return None
        
        # Simple estimation based on average stage duration
        stages_completed = sum(1 for stage in ['separation', 'guitar', 'bass', 'drums', 'vocals', 'combining', 'exports'] 
                              if progress_data.get(stage, 0) >= 100)
        total_stages = 7
        
        if stages_completed >= total_stages:
            return None  # Already completed
        
        # Estimate based on typical durations (in minutes)
        stage_estimates = {
            'separation': 2,
            'guitar': 3,
            'bass': 2,
            'drums': 1,
            'vocals': 2,
            'combining': 0.5,
            'exports': 1
        }
        
        remaining_time = sum(stage_estimates.get(stage, 1) 
                           for stage in ['separation', 'guitar', 'bass', 'drums', 'vocals', 'combining', 'exports']
                           if progress_data.get(stage, 0) < 100)
        
        if remaining_time <= 0:
            return "Almost complete"
        elif remaining_time <= 1:
            return "< 1 minute"
        else:
            return f"~ {int(remaining_time)} minutes"


# Global service instance
metrics_service = MetricsService()


# Convenience functions
def start_task_metrics(task_id: str, task_type: str, **kwargs) -> TaskMetrics:
    return metrics_service.start_task_metrics(task_id, task_type, **kwargs)

def complete_task_metrics(task_id: str, status: str = 'success', **kwargs):
    return metrics_service.complete_task_metrics(task_id, status, **kwargs)

def update_progress(transcription_id: str, stage: str, progress: int, status: str = None):
    return metrics_service.update_transcription_progress(transcription_id, stage, progress, status)

def get_transcription_progress(transcription_id: str) -> Dict:
    return metrics_service.get_transcription_progress(transcription_id)
