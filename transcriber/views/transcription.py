"""
Transcription management views
Handles transcription details, status, and management operations
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from . import AsyncResult
from ..models import Transcription
from ..decorators import htmx_login_required
import json


def detail(request, pk):
    """
    Display transcription details page.
    """
    # Only fetch necessary fields, defer large JSON fields for performance
    transcription = get_object_or_404(
        Transcription.objects.defer('midi_data', 'guitar_notes', 'whisper_analysis', 'musicxml_content'), 
        pk=pk
    )
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    # Get all fingering variants
    variants = transcription.variants.all().order_by('difficulty_score')
    
    # Get playability metrics if available
    metrics = getattr(transcription, 'metrics', None)
    
    # Get task status if processing
    task_id = request.session.get(f'task_{transcription.id}')
    task_status = None
    if task_id and transcription.status == 'processing':
        result = AsyncResult(task_id)
        if result.info:
            # Handle case where result.info is an error object (like WorkerLostError)
            if isinstance(result.info, dict):
                task_status = result.info.get('status', 'Processing...')
            else:
                # Worker failed - mark transcription as failed
                transcription.status = 'failed'
                transcription.error_message = f"Worker error: {str(result.info)}"
                transcription.save()
                task_status = None
    
    # Calculate additional metrics for improved UX
    if transcription.complexity:
        complexity_map = {'simple': 1, 'moderate': 2, 'complex': 3, 'advanced': 4, 'virtuoso': 5}
        transcription.complexity_level = complexity_map.get(transcription.complexity, 3)
    
    # Get file size in MB
    if transcription.original_audio.name:
        try:
            transcription.file_size_mb = transcription.original_audio.size / (1024 * 1024)
        except:
            transcription.file_size_mb = 0
    
    # Get exports for this transcription
    exports = transcription.exports.all()
    
    # Get existing exports by format for the export_section.html template
    export_musicxml = transcription.exports.filter(format='musicxml').first()
    export_gp5 = transcription.exports.filter(format='gp5').first()
    export_midi = transcription.exports.filter(format='midi').first()
    export_ascii = transcription.exports.filter(format='ascii').first()
    export_pdf = transcription.exports.filter(format='pdf').first()
    
    # Check for existing exports by format (for backward compatibility)
    export_checks = {
        'has_musicxml': export_musicxml is not None,
        'has_gp5': export_gp5 is not None,
        'has_midi': export_midi is not None,
        'has_ascii': export_ascii is not None,
        'has_pdf': export_pdf is not None,
    }
    
    # Export format definitions for the UI
    export_formats = {
        'musicxml': {
            'name': 'MusicXML',
            'description': 'Universal format for notation software',
            'icon': '<svg class="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>'
        },
        'gp5': {
            'name': 'Guitar Pro',
            'description': 'For Guitar Pro 5 and compatible apps',
            'icon': '<svg class="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7"/></svg>'
        },
        'midi': {
            'name': 'MIDI',
            'description': 'For DAWs and music production',
            'icon': '<svg class="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2z"/></svg>'
        },
        'ascii': {
            'name': 'ASCII Tab',
            'description': 'Plain text format for sharing',
            'icon': '<svg class="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"/></svg>'
        }
    }
    
    context = {
        'transcription': transcription,
        'variants': variants,
        'metrics': metrics,
        'task_status': task_status,
        'has_variants': variants.exists(),
        'selected_variant': variants.filter(is_selected=True).first() if variants.exists() else None,
        'exports': exports,
        'export_formats': export_formats,
        # Add individual export instances for the template
        'export_musicxml': export_musicxml,
        'export_gp5': export_gp5,
        'export_midi': export_midi,
        'export_ascii': export_ascii,
        'export_pdf': export_pdf,
        **export_checks  # Add the export format checks to context
    }
    
    return render(request, 'transcriber/detail.html', context)


@require_http_methods(["GET"])
def status(request, pk):
    """
    Get transcription processing status.
    Returns appropriate partial HTML for HTMX requests.
    """
    # Only need basic fields for status checking, defer large data
    transcription = get_object_or_404(
        Transcription.objects.defer('midi_data', 'guitar_notes', 'whisper_analysis', 'musicxml_content'), 
        pk=pk
    )
    
    # Get task ID from session
    task_id = request.session.get(f'task_{transcription.id}')
    
    # Check if this is an HTMX request
    is_htmx = request.headers.get('HX-Request')
    
    # Get processing context for unified status
    context = {
        'transcription': transcription,
        'current_step': 1,  # Default step
        'task_progress': 'Queued...',
        'progress_percent': 5,
        'time_remaining': '2-3 minutes',
        'task_state': 'PENDING'
    }
    
    if task_id and transcription.status in ['pending', 'processing']:
        result = AsyncResult(task_id)
        context['task_state'] = result.state
        
        if result.info:
            if isinstance(result.info, dict):
                # Extract detailed progress from Celery task
                context['task_progress'] = result.info.get('step', 'Processing...')
                
                # Map step number or calculate progress
                step_info = result.info.get('step', 1)
                if isinstance(step_info, int):
                    context['current_step'] = step_info
                    # Calculate progress based on step (8 total steps)
                    context['progress_percent'] = min(90, (step_info / 8.0) * 100)
                else:
                    # Extract step from progress messages
                    context['current_step'] = context.get('current_step', 1)
                    context['progress_percent'] = result.info.get('progress', context['progress_percent'])
                
                # More accurate time estimates based on actual progress
                progress = context['progress_percent']
                if progress > 85:
                    context['time_remaining'] = '10-30 seconds'
                elif progress > 60:
                    context['time_remaining'] = '30-60 seconds' 
                elif progress > 30:
                    context['time_remaining'] = '1-2 minutes'
                elif progress > 10:
                    context['time_remaining'] = '2-3 minutes'
                else:
                    context['time_remaining'] = '3-4 minutes'
                    
            else:
                # Worker failed - update transcription status
                transcription.status = 'failed'
                transcription.error_message = f"Worker error: {str(result.info)}"
                transcription.save()
    elif transcription.status == 'completed':
        # Set completed progress
        context['current_step'] = 8
        context['progress_percent'] = 100
        context['task_progress'] = 'Complete!'
    
    if is_htmx:
        # Always return status for HTMX requests
        return render(request, 'transcriber/partials/status.html', context)
    
    # For non-HTMX requests, return JSON status
    return JsonResponse({
        'id': str(transcription.id),
        'status': transcription.status,
        'error_message': transcription.error_message if transcription.status == 'failed' else None,
    })


def get_task_status(request, task_id):
    """
    Get Celery task status by ID.
    Used for tracking export and processing tasks.
    """
    try:
        result = AsyncResult(task_id)
        
        if result.state == 'PENDING':
            response = {
                'state': result.state,
                'status': 'Pending...',
                'task_id': task_id
            }
        elif result.state != 'FAILURE':
            response = {
                'state': result.state,
                'status': result.info.get('status', '') if isinstance(result.info, dict) else str(result.info),
                'current': result.info.get('current', 0) if isinstance(result.info, dict) else 0,
                'total': result.info.get('total', 1) if isinstance(result.info, dict) else 1,
                'task_id': task_id
            }
            if result.state == 'SUCCESS':
                response['result'] = result.info
        else:
            # Task failed
            response = {
                'state': result.state,
                'status': str(result.info),
                'task_id': task_id
            }
        
        return JsonResponse(response)
        
    except Exception as e:
        return JsonResponse({
            'state': 'ERROR',
            'status': str(e)
        }, status=500)


@htmx_login_required
@require_http_methods(["POST"])
def toggle_favorite(request, pk):
    """
    Toggle favorite status for a transcription.
    """
    # Only need basic fields for favorite toggle
    transcription = get_object_or_404(
        Transcription.objects.defer('midi_data', 'guitar_notes', 'whisper_analysis', 'musicxml_content'), 
        pk=pk
    )
    
    # Check ownership
    if transcription.user != request.user and not request.user.is_superuser:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    user_profile = request.user.profile
    
    if transcription in user_profile.favorite_transcriptions.all():
        user_profile.favorite_transcriptions.remove(transcription)
        is_favorite = False
    else:
        user_profile.favorite_transcriptions.add(transcription)
        is_favorite = True
    
    # HTMX response
    if request.headers.get('HX-Request'):
        return render(request, 'transcriber/partials/favorite_button.html', {
            'transcription': transcription,
            'is_favorite': is_favorite,
        })
    
    return JsonResponse({'is_favorite': is_favorite})


@require_http_methods(["POST", "DELETE"])
def delete_transcription(request, pk):
    """
    Delete a transcription and all associated files.
    """
    # Need to load full object for deletion (including file fields)
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Check ownership (only enforce if transcription has an owner)
    if transcription.user and transcription.user != request.user and not request.user.is_superuser:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    # Delete associated files
    if transcription.original_audio.name:
        transcription.original_audio.delete()
    # Remove any additional generated files if present (defensive)
    if hasattr(transcription, 'processed_audio') and transcription.processed_audio:
        transcription.processed_audio.delete()
    
    # Delete all exports
    for export in transcription.exports.all():
        if export.file:
            export.file.delete()
    
    # Delete the transcription (cascades to related objects)
    transcription.delete()
    
    # HTMX response
    if request.headers.get('HX-Request') or request.method == 'DELETE':
        # Return empty response for HTMX or DELETE method
        return HttpResponse('', status=204)
    
    # Regular response - redirect to dashboard
    return redirect('transcriber:dashboard')


@htmx_login_required
@require_http_methods(["POST"])
def reprocess(request, pk):
    """
    Reprocess a transcription with the ML pipeline.
    """
    from ..tasks import process_transcription_advanced
    
    # Need full object for reprocessing (will reset data fields)
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Check ownership
    if transcription.user != request.user and not request.user.is_superuser:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    # Reset status and clear old results
    transcription.status = 'processing'
    transcription.error_message = ''
    transcription.guitar_notes = None
    transcription.midi_data = None
    transcription.musicxml_content = ''
    transcription.whisper_analysis = None
    transcription.save()
    
    # Clear old variants
    transcription.variants.all().delete()
    
    # Clear old exports
    for export in transcription.exports.all():
        if export.file:
            export.file.delete()
    transcription.exports.all().delete()
    
    # Start new processing task
    task = process_transcription_advanced.delay(str(transcription.id), accuracy_mode='maximum')
    
    # Store task ID in session for status tracking
    request.session[f'task_{transcription.id}'] = task.id
    
    # HTMX response
    if request.headers.get('HX-Request'):
        # Return the status partial
        return render(request, 'transcriber/partials/status.html', {
            'transcription': transcription,
            'current_step': 1,
            'task_progress': 'Starting reprocessing...',
            'progress_percent': 5,
            'time_remaining': '2-3 minutes'
        })
    
    return JsonResponse({
        'status': 'success', 
        'task_id': task.id,
        'message': 'Reprocessing started'
    })