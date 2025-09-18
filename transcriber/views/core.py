"""
Core views for RiffScribe
Handles main pages: index, upload, library, dashboard, profile
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.conf import settings
from ..models import Transcription, UserProfile, ConversionEvent
from ..tasks import process_transcription_advanced
from ..decorators import check_monthly_limits, track_conversion_event
import os


def index(request):
    """
    Main landing page showing recent transcriptions.
    """
    if request.user.is_authenticated:
        transcriptions = Transcription.objects.filter(user=request.user)[:10]
    else:
        transcriptions = Transcription.objects.filter(user__isnull=True)[:10]
    
    return render(request, 'transcriber/index.html', {
        'transcriptions': transcriptions
    })


@require_http_methods(["GET", "POST"])
@check_monthly_limits
@track_conversion_event('uploaded_audio')
def upload(request):
    """
    Handle audio file upload for transcription with usage tracking.
    """
    if request.method == "POST":
        is_htmx = request.headers.get('HX-Request')
        
        # Check for file
        if 'audio_file' not in request.FILES:
            error_msg = 'No file provided. Please select an audio file.'
            if is_htmx:
                return render(request, 'transcriber/partials/upload_error.html', {
                    'error': error_msg
                }, status=400)
            return JsonResponse({'error': error_msg}, status=400)
        
        audio_file = request.FILES['audio_file']
        
        # Validate file extension - OpenAI Whisper supported formats only
        # Based on OpenAI API: ['flac', 'm4a', 'mp3', 'mp4', 'mpeg', 'mpga', 'oga', 'ogg', 'wav', 'webm']
        allowed_extensions = ['.flac', '.m4a', '.mp3', '.mp4', '.mpeg', '.mpga', '.oga', '.ogg', '.wav', '.webm']
        file_ext = os.path.splitext(audio_file.name)[1].lower()
        
        if file_ext not in allowed_extensions:
            error_msg = f'Invalid file format. Allowed: {", ".join(allowed_extensions)}'
            if is_htmx:
                return render(request, 'transcriber/partials/upload_error.html', {
                    'error': error_msg
                }, status=400)
            return JsonResponse({'error': error_msg}, status=400)
        
        # Validate file size
        max_size = getattr(settings, 'MAX_AUDIO_FILE_SIZE', 100 * 1024 * 1024)  # Default 100MB
        if audio_file.size > max_size:
            error_msg = f'File too large. Maximum size: {max_size / (1024*1024):.0f}MB'
            if is_htmx:
                return render(request, 'transcriber/partials/upload_error.html', {
                    'error': error_msg
                }, status=400)
            return JsonResponse({'error': error_msg}, status=400)
        
        try:
            # Create transcription record (link to user if authenticated)
            transcription = Transcription.objects.create(
                user=request.user if request.user.is_authenticated else None,
                filename=audio_file.name,
                original_audio=audio_file,
                status='pending'
            )
            
            # Update user profile usage stats if authenticated
            if request.user.is_authenticated and hasattr(request.user, 'profile'):
                profile = request.user.profile
                if not profile.can_upload():
                    error_msg = 'Monthly upload limit reached. Please upgrade to premium.'
                    if is_htmx:
                        return render(request, 'transcriber/partials/upload_error.html', {
                            'error': error_msg
                        }, status=400)
                    return JsonResponse({'error': error_msg}, status=400)
                profile.increment_usage()
            
            # Queue advanced processing task with Celery
            try:
                # Use maximum accuracy mode for best results
                task = process_transcription_advanced.delay(
                    str(transcription.id),
                    accuracy_mode='maximum'
                )
                # Store task ID in session for tracking
                request.session[f'task_{transcription.id}'] = task.id
            except Exception as e:
                # If Celery fails, still save the transcription but mark it as failed
                transcription.status = 'failed'
                transcription.error_message = f'Failed to queue processing: {str(e)}'
                transcription.save()
                if is_htmx:
                    return render(request, 'transcriber/partials/upload_error.html', {
                        'error': 'Processing service is unavailable. Please try again later.'
                    }, status=500)
                return JsonResponse({
                    'error': 'Failed to start processing'
                }, status=500)
            
            # Return success response
            if is_htmx:
                return render(request, 'transcriber/partials/upload_success.html', {
                    'transcription': transcription
                })
            
            # For regular form submission, redirect to detail page
            return redirect('transcriber:detail', pk=transcription.pk)
            
        except Exception as e:
            error_msg = f'Upload failed: {str(e)}'
            if is_htmx:
                return render(request, 'transcriber/partials/upload_error.html', {
                    'error': error_msg
                }, status=500)
            return JsonResponse({'error': error_msg}, status=500)
    
    # GET request - show upload form
    return render(request, 'transcriber/upload.html')


def library(request):
    """
    Display library of transcriptions.
    """
    if request.user.is_authenticated:
        base_queryset = Transcription.objects.filter(user=request.user)
    else:
        base_queryset = Transcription.objects.filter(user__isnull=True)
    
    # Apply filters if provided
    search = request.GET.get('search', '').strip()
    status = request.GET.get('status', '').strip()
    sort = request.GET.get('sort', '-created_at').strip()
    
    transcriptions = base_queryset.order_by('-created_at')
    
    # Apply search filter
    if search:
        transcriptions = transcriptions.filter(filename__icontains=search)
    
    # Apply status filter  
    if status:
        transcriptions = transcriptions.filter(status=status)
    
    # Apply sorting
    if sort:
        valid_sorts = ['-created_at', 'created_at', 'title', '-title', '-duration']
        if sort in valid_sorts:
            transcriptions = transcriptions.order_by(sort)
    
    # For non-authenticated users, limit results
    if not request.user.is_authenticated:
        transcriptions = transcriptions[:20]
    
    # Calculate statistics
    total_count = base_queryset.count()
    completed_count = base_queryset.filter(status='completed').count()
    
    # Calculate favorites count (only for authenticated users)
    favorites_count = 0
    if request.user.is_authenticated and hasattr(request.user, 'profile'):
        favorites_count = request.user.profile.favorite_transcriptions.count()
    
    # Calculate total duration (approximate)
    total_duration = "0h"
    try:
        from django.db.models import Sum
        duration_sum = base_queryset.aggregate(total=Sum('duration'))['total']
        if duration_sum:
            hours = int(duration_sum // 3600)
            minutes = int((duration_sum % 3600) // 60)
            if hours > 0:
                total_duration = f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"
            else:
                total_duration = f"{minutes}m"
    except:
        total_duration = "0h"
    
    # Add favorite status for authenticated users
    if request.user.is_authenticated and hasattr(request.user, 'profile'):
        favorite_ids = list(request.user.profile.favorite_transcriptions.values_list('id', flat=True))
        for transcription in transcriptions:
            transcription.is_favorite = transcription.id in favorite_ids
    else:
        for transcription in transcriptions:
            transcription.is_favorite = False
    
    # HTMX partial response for search/filter
    if request.headers.get('HX-Request') and request.headers.get('HX-Target') == 'transcriptions-grid':
        return render(request, 'transcriber/partials/transcriptions_grid.html', {
            'transcriptions': transcriptions,
        })
    
    return render(request, 'transcriber/library.html', {
        'transcriptions': transcriptions,
        'total_count': total_count,
        'completed_count': completed_count,
        'favorites_count': favorites_count,
        'total_duration': total_duration,
        'search': search,
        'status': status,
        'sort': sort,
    })


@login_required
def dashboard(request):
    """
    User dashboard showing their transcriptions and stats.
    """
    user_profile = request.user.profile
    transcriptions = Transcription.objects.filter(user=request.user).order_by('-created_at')[:10]
    
    # Calculate stats
    total_transcriptions = Transcription.objects.filter(user=request.user).count()
    completed_transcriptions = Transcription.objects.filter(
        user=request.user,
        status='completed'
    ).count()
    processing_transcriptions = Transcription.objects.filter(
        user=request.user,
        status__in=['pending', 'processing']
    ).count()
    
    # Get favorite transcriptions
    favorites = user_profile.favorite_transcriptions.all()[:5]
    
    context = {
        'transcriptions': transcriptions,
        'total_transcriptions': total_transcriptions,
        'completed_transcriptions': completed_transcriptions,
        'processing_transcriptions': processing_transcriptions,
        'user_profile': user_profile,
        'favorites': favorites,
        'usage_percentage': (user_profile.uploads_this_month / user_profile.monthly_upload_limit * 100) if user_profile.monthly_upload_limit > 0 else 0
    }
    
    return render(request, 'transcriber/dashboard.html', context)


@login_required
def profile(request):
    """
    User profile view and edit.
    """
    user_profile = request.user.profile
    
    if request.method == 'POST':
        # Update profile
        user_profile.bio = request.POST.get('bio', '')
        user_profile.skill_level = request.POST.get('skill_level', 'intermediate')
        user_profile.preferred_difficulty = request.POST.get('preferred_difficulty', 'balanced')
        user_profile.default_tempo_adjustment = float(request.POST.get('tempo_adjustment', 1.0))
        
        # Handle genres
        genres = request.POST.getlist('genres')
        user_profile.preferred_genres = genres
        
        user_profile.save()
        
        # Update user info
        request.user.first_name = request.POST.get('first_name', '')
        request.user.last_name = request.POST.get('last_name', '')
        request.user.save()
        
        if request.headers.get('HX-Request'):
            return render(request, 'transcriber/partials/profile_updated.html', {
                'user_profile': user_profile
            })
        
        return redirect('transcriber:profile')
    
    return render(request, 'transcriber/profile.html', {
        'user_profile': user_profile
    })