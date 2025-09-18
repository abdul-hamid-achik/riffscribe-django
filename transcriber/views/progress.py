"""
Enhanced Progress Tracking Views
Provides real-time granular progress updates for multi-track transcription
"""
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import timedelta
import json

from ..models import Transcription
from ..services.metrics_service import get_transcription_progress, metrics_service
from ..services.rate_limiter import openai_limiter


@require_http_methods(["GET"])
def transcription_progress(request, transcription_id):
    """
    Get detailed progress for a transcription including individual instrument progress
    """
    transcription = get_object_or_404(Transcription, id=transcription_id)
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    # Get detailed progress
    progress_data = get_transcription_progress(str(transcription_id))
    
    # Add transcription status information
    progress_data.update({
        'transcription_status': transcription.status,
        'filename': transcription.filename,
        'created_at': transcription.created_at.isoformat(),
        'duration': transcription.duration,
        'estimated_tempo': transcription.estimated_tempo
    })
    
    # Add track information if available
    tracks = transcription.tracks.all()
    if tracks.exists():
        progress_data['tracks'] = [
            {
                'id': track.id,
                'name': track.display_name,
                'instrument': track.instrument_type,
                'confidence': track.confidence_score,
                'is_processed': track.is_processed
            }
            for track in tracks
        ]
    
    # Add multitrack data if available
    if transcription.multitrack_data:
        progress_data['multitrack_info'] = {
            'tracks_created': transcription.multitrack_data.get('tracks_created', 0),
            'successful_instruments': transcription.multitrack_data.get('successful_instruments', []),
            'failed_instruments': transcription.multitrack_data.get('failed_instruments', []),
            'partial_success': transcription.multitrack_data.get('partial_success', False)
        }
    
    return JsonResponse(progress_data)


@require_http_methods(["GET"])
def system_metrics(request):
    """
    Get system health and performance metrics
    Restricted to admin users
    """
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Admin access required'}, status=403)
    
    # Get system health
    health = metrics_service.get_system_health()
    
    # Get OpenAI usage stats
    openai_usage = metrics_service.get_openai_usage_stats()
    
    # Get rate limiting info
    rate_limit_usage = openai_limiter.get_current_usage()
    
    # Get recent transcription statistics
    recent_transcriptions = Transcription.objects.filter(
        created_at__gte=timezone.now() - timedelta(hours=24)
    )
    
    stats = {
        'system_health': health,
        'openai_usage': openai_usage,
        'rate_limits': rate_limit_usage,
        'transcription_stats': {
            'total_24h': recent_transcriptions.count(),
            'completed_24h': recent_transcriptions.filter(status='completed').count(),
            'failed_24h': recent_transcriptions.filter(status='failed').count(),
            'processing': recent_transcriptions.filter(status='processing').count()
        }
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def instrument_stats(request):
    """
    Get aggregated statistics for instrument transcription performance
    """
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Admin access required'}, status=403)
    
    instruments = ['guitar', 'bass', 'drums', 'vocals']
    stats = {}
    
    for instrument in instruments:
        instrument_stats = metrics_service.get_instrument_stats(instrument, hours=24)
        if instrument_stats:
            stats[instrument] = {
                'total_attempts': instrument_stats.total_attempts,
                'success_rate': instrument_stats.success_rate,
                'avg_duration': instrument_stats.avg_duration,
                'avg_confidence': instrument_stats.avg_confidence
            }
        else:
            stats[instrument] = {
                'total_attempts': 0,
                'success_rate': 0,
                'avg_duration': 0,
                'avg_confidence': 0
            }
    
    return JsonResponse({
        'instrument_stats': stats,
        'period': '24 hours'
    })


@require_http_methods(["GET"])
def queue_status(request):
    """
    Get current queue status and task distribution
    """
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Admin access required'}, status=403)
    
    try:
        from celery import current_app
        
        # Get active tasks
        inspect = current_app.control.inspect()
        active_tasks = inspect.active()
        scheduled_tasks = inspect.scheduled()
        reserved_tasks = inspect.reserved()
        
        # Process active tasks by queue
        queue_stats = {}
        total_active = 0
        
        if active_tasks:
            for worker, tasks in active_tasks.items():
                total_active += len(tasks)
                for task in tasks:
                    # Extract queue from routing
                    routing_key = task.get('routing_key', 'default')
                    if routing_key not in queue_stats:
                        queue_stats[routing_key] = {
                            'active': 0,
                            'tasks': []
                        }
                    queue_stats[routing_key]['active'] += 1
                    queue_stats[routing_key]['tasks'].append({
                        'id': task['id'],
                        'name': task['name'],
                        'args': task.get('args', [])[:2] if task.get('args') else [],  # Limit args for privacy
                        'worker': worker
                    })
        
        return JsonResponse({
            'total_active_tasks': total_active,
            'queue_stats': queue_stats,
            'has_scheduled': bool(scheduled_tasks),
            'has_reserved': bool(reserved_tasks),
            'timestamp': timezone.now().isoformat()
        })
        
    except Exception as e:
        return JsonResponse({
            'error': 'Failed to get queue status',
            'message': str(e)
        }, status=500)


@require_http_methods(["POST"])
@login_required
def retry_failed_transcription(request, transcription_id):
    """
    Retry a failed transcription
    """
    transcription = get_object_or_404(Transcription, id=transcription_id)
    
    # Check access permission
    if transcription.user != request.user and not request.user.is_superuser:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    if transcription.status != 'failed':
        return JsonResponse({'error': 'Transcription is not in failed state'}, status=400)
    
    # Check OpenAI rate limits before retrying
    can_proceed, retry_after = openai_limiter.can_make_request(estimated_cost=0.05)
    if not can_proceed:
        return JsonResponse({
            'error': 'Rate limit exceeded',
            'retry_after': retry_after
        }, status=429)
    
    try:
        # Reset transcription status
        transcription.status = 'pending'
        transcription.error_message = ''
        transcription.save()
        
        # Clear any existing tracks
        transcription.tracks.all().delete()
        
        # Requeue the transcription
        from ..tasks import process_transcription_advanced
        task_result = process_transcription_advanced.delay(transcription_id, accuracy_mode='maximum')
        
        # Store task ID in session for progress tracking
        request.session[f'task_{transcription_id}'] = task_result.id
        
        return JsonResponse({
            'success': True,
            'task_id': task_result.id,
            'message': 'Transcription retry started'
        })
        
    except Exception as e:
        return JsonResponse({
            'error': 'Failed to retry transcription',
            'message': str(e)
        }, status=500)


@require_http_methods(["GET"])
def cost_estimation(request):
    """
    Get cost estimation for OpenAI usage
    """
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Admin access required'}, status=403)
    
    usage_stats = metrics_service.get_openai_usage_stats()
    
    # Estimate costs based on current usage patterns
    daily_rate = usage_stats['estimated_cost_today']
    monthly_projection = daily_rate * 30
    
    from django.conf import settings
    monthly_limit = getattr(settings, 'OPENAI_MONTHLY_BUDGET_LIMIT', 100)
    
    estimation = {
        'current_usage': usage_stats,
        'daily_average': daily_rate,
        'monthly_projection': monthly_projection,
        'monthly_limit': monthly_limit,
        'projected_overage': max(0, monthly_projection - monthly_limit),
        'days_remaining_at_current_rate': (monthly_limit - usage_stats['estimated_cost_this_month']) / max(daily_rate, 0.01) if daily_rate > 0 else 999,
        'recommendations': []
    }
    
    # Generate recommendations
    if monthly_projection > monthly_limit * 0.9:
        estimation['recommendations'].append("Approaching monthly budget limit - consider rate limiting")
    
    if daily_rate > monthly_limit / 30 * 1.5:
        estimation['recommendations'].append("Daily usage is 50% above average - monitor closely")
    
    if usage_stats['requests_today'] > 100:
        estimation['recommendations'].append("High request volume today - verify efficient usage")
    
    return JsonResponse(estimation)
