"""
Library Management Views
Enhanced search, filter, and organization features for transcription library
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count, Avg
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from datetime import timedelta

from ..models import Transcription


@require_http_methods(["GET"])
def library_search(request):
    """
    Enhanced HTMX endpoint for library search with music-specific filters
    """
    if not request.user.is_authenticated:
        # For anonymous users, show public transcriptions (if any)
        transcriptions = Transcription.objects.filter(
            status='completed'
        )
    else:
        transcriptions = Transcription.objects.filter(user=request.user)
    
    # Get search parameters
    search_query = request.GET.get('search', '').strip()
    quick_filters = request.GET.get('quick_filters', '').split(',') if request.GET.get('quick_filters') else []
    key_filter = request.GET.get('key_filter', '').strip()
    tempo_min = request.GET.get('tempo_min', '').strip()
    tempo_max = request.GET.get('tempo_max', '').strip()
    difficulty = request.GET.get('difficulty', '').strip()
    instruments = request.GET.get('instruments', '').split(',') if request.GET.get('instruments') else []
    sort_by = request.GET.get('sort', '-created_at')
    
    # Apply text search
    if search_query:
        transcriptions = transcriptions.filter(
            Q(filename__icontains=search_query) |
            Q(estimated_key__icontains=search_query) |
            Q(detected_instruments__icontains=search_query) |
            Q(complexity__icontains=search_query)
        )
    
    # Apply quick filters
    for quick_filter in quick_filters:
        if quick_filter == 'favorites':
            transcriptions = transcriptions.filter(is_favorite=True)
        elif quick_filter == 'recent':
            last_week = timezone.now() - timedelta(days=7)
            transcriptions = transcriptions.filter(created_at__gte=last_week)
        elif quick_filter == 'completed':
            transcriptions = transcriptions.filter(status='completed')
    
    # Apply key filter
    if key_filter:
        transcriptions = transcriptions.filter(estimated_key__iexact=key_filter)
    
    # Apply tempo filters
    if tempo_min:
        try:
            transcriptions = transcriptions.filter(estimated_tempo__gte=int(tempo_min))
        except ValueError:
            pass
    
    if tempo_max:
        try:
            transcriptions = transcriptions.filter(estimated_tempo__lte=int(tempo_max))
        except ValueError:
            pass
    
    # Apply difficulty filter
    if difficulty:
        transcriptions = transcriptions.filter(complexity__iexact=difficulty)
    
    # Apply instruments filter
    if instruments:
        for instrument in instruments:
            if instrument.strip():
                transcriptions = transcriptions.filter(
                    detected_instruments__icontains=instrument.strip()
                )
    
    # Apply sorting
    valid_sort_fields = [
        'created_at', '-created_at', 
        'filename', '-filename', 
        'estimated_tempo', '-estimated_tempo',
        'duration', '-duration',
        'playability_score', '-playability_score'
    ]
    
    if sort_by in valid_sort_fields:
        if sort_by in ['playability_score', '-playability_score']:
            # Sort by playability score from metrics
            transcriptions = transcriptions.select_related('metrics').annotate(
                playability_score=Avg('metrics__playability_score')
            ).order_by(sort_by)
        else:
            transcriptions = transcriptions.order_by(sort_by)
    else:
        transcriptions = transcriptions.order_by('-created_at')
    
    # Select related data for efficiency
    transcriptions = transcriptions.select_related('metrics').prefetch_related('variants')
    
    # Pagination for performance
    paginator = Paginator(transcriptions, 12)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'transcriptions': page_obj,
        'total_count': paginator.count,
        'search_query': search_query,
        'quick_filters': quick_filters,
        'key_filter': key_filter,
        'tempo_min': tempo_min,
        'tempo_max': tempo_max,
        'difficulty': difficulty,
        'instruments': instruments,
        'sort_by': sort_by,
    }
    
    # Return the enhanced transcriptions grid
    return render(request, 'transcriber/partials/transcriptions_grid.html', context)


@require_http_methods(["GET"])
def library_stats(request):
    """
    Get library statistics for the current user
    """
    if not request.user.is_authenticated:
        return JsonResponse({
            'total_count': 0,
            'completed_count': 0,
            'favorites_count': 0,
            'total_duration': '0h',
            'avg_tempo': 0,
            'most_common_key': '',
        })
    
    transcriptions = Transcription.objects.filter(user=request.user)
    
    # Calculate stats
    total_count = transcriptions.count()
    completed_count = transcriptions.filter(status='completed').count()
    favorites_count = transcriptions.filter(is_favorite=True).count()
    
    # Calculate total duration
    total_seconds = sum([
        t.duration or 0 for t in transcriptions.filter(duration__isnull=False)
    ])
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    total_duration = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
    
    # Average tempo
    tempo_values = transcriptions.filter(
        estimated_tempo__isnull=False
    ).values_list('estimated_tempo', flat=True)
    avg_tempo = sum(tempo_values) / len(tempo_values) if tempo_values else 0
    
    # Most common key
    key_counts = transcriptions.filter(
        estimated_key__isnull=False
    ).values('estimated_key').annotate(
        count=Count('estimated_key')
    ).order_by('-count').first()
    
    most_common_key = key_counts['estimated_key'] if key_counts else ''
    
    return JsonResponse({
        'total_count': total_count,
        'completed_count': completed_count,
        'favorites_count': favorites_count,
        'total_duration': total_duration,
        'avg_tempo': round(avg_tempo, 1),
        'most_common_key': most_common_key,
    })


@require_http_methods(["POST"])
@login_required
def bulk_operations(request):
    """
    Handle bulk operations on transcriptions
    """
    action = request.POST.get('action')
    transcription_ids = request.POST.getlist('transcription_ids')
    
    if not action or not transcription_ids:
        return JsonResponse({'error': 'Missing action or transcription IDs'}, status=400)
    
    # Get user's transcriptions only
    transcriptions = Transcription.objects.filter(
        user=request.user,
        pk__in=transcription_ids
    )
    
    if action == 'delete':
        count = transcriptions.count()
        transcriptions.delete()
        return JsonResponse({'success': True, 'message': f'Deleted {count} transcriptions'})
    
    elif action == 'favorite':
        count = transcriptions.update(is_favorite=True)
        return JsonResponse({'success': True, 'message': f'Favorited {count} transcriptions'})
    
    elif action == 'unfavorite':
        count = transcriptions.update(is_favorite=False)
        return JsonResponse({'success': True, 'message': f'Unfavorited {count} transcriptions'})
    
    elif action == 'export_all':
        # TODO: Implement bulk export
        return JsonResponse({'success': True, 'message': 'Bulk export started'})
    
    else:
        return JsonResponse({'error': 'Invalid action'}, status=400)


@require_http_methods(["GET"])
def library_suggestions(request):
    """
    Get search suggestions based on user's library content
    """
    if not request.user.is_authenticated:
        return JsonResponse({'suggestions': []})
    
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'suggestions': []})
    
    transcriptions = Transcription.objects.filter(user=request.user)
    
    # Get suggestions from different fields
    suggestions = set()
    
    # Filename suggestions
    filenames = transcriptions.filter(
        filename__icontains=query
    ).values_list('filename', flat=True)[:5]
    suggestions.update([f['filename'] for f in filenames])
    
    # Key suggestions
    keys = transcriptions.filter(
        estimated_key__icontains=query,
        estimated_key__isnull=False
    ).values_list('estimated_key', flat=True).distinct()[:5]
    suggestions.update(keys)
    
    # Instrument suggestions
    instruments_qs = transcriptions.filter(
        detected_instruments__icontains=query,
        detected_instruments__isnull=False
    ).values_list('detected_instruments', flat=True)
    
    for instrument_list in instruments_qs:
        if instrument_list:
            for instrument in instrument_list:
                if query.lower() in instrument.lower():
                    suggestions.add(instrument.title())
    
    return JsonResponse({
        'suggestions': list(suggestions)[:10]
    })


@require_http_methods(["GET"])
def library_analytics(request):
    """
    Get detailed analytics about the user's library
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    transcriptions = Transcription.objects.filter(user=request.user)
    
    # Tempo distribution
    tempo_ranges = {
        'slow': transcriptions.filter(estimated_tempo__lt=90).count(),
        'moderate': transcriptions.filter(estimated_tempo__gte=90, estimated_tempo__lt=120).count(),
        'fast': transcriptions.filter(estimated_tempo__gte=120, estimated_tempo__lt=160).count(),
        'very_fast': transcriptions.filter(estimated_tempo__gte=160).count(),
    }
    
    # Key distribution
    key_distribution = list(
        transcriptions.filter(estimated_key__isnull=False)
        .values('estimated_key')
        .annotate(count=Count('estimated_key'))
        .order_by('-count')[:10]
    )
    
    # Difficulty distribution
    difficulty_distribution = list(
        transcriptions.filter(complexity__isnull=False)
        .values('complexity')
        .annotate(count=Count('complexity'))
    )
    
    # Monthly activity
    from django.db.models import TruncMonth
    monthly_activity = list(
        transcriptions.annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')[-12:]  # Last 12 months
    )
    
    # Average playability by difficulty
    playability_by_difficulty = list(
        transcriptions.select_related('metrics')
        .filter(complexity__isnull=False, metrics__playability_score__isnull=False)
        .values('complexity')
        .annotate(avg_playability=Avg('metrics__playability_score'))
    )
    
    return JsonResponse({
        'tempo_distribution': tempo_ranges,
        'key_distribution': key_distribution,
        'difficulty_distribution': difficulty_distribution,
        'monthly_activity': monthly_activity,
        'playability_by_difficulty': playability_by_difficulty,
    })
