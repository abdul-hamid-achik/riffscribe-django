from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from django.conf import settings
from .models import Transcription, TabExport
from .tasks import process_transcription, generate_export
from celery.result import AsyncResult
import json
import os


def index(request):
    transcriptions = Transcription.objects.all()[:10]
    return render(request, 'transcriber/index.html', {
        'transcriptions': transcriptions
    })


@require_http_methods(["GET", "POST"])
def upload(request):
    if request.method == "POST":
        if 'audio_file' not in request.FILES:
            return JsonResponse({'error': 'No file provided'}, status=400)
        
        audio_file = request.FILES['audio_file']
        
        # Validate file extension
        allowed_extensions = ['.mp3', '.wav', '.m4a', '.flac', '.ogg']
        file_ext = os.path.splitext(audio_file.name)[1].lower()
        
        if file_ext not in allowed_extensions:
            return JsonResponse({
                'error': f'Invalid file format. Allowed: {", ".join(allowed_extensions)}'
            }, status=400)
        
        # Validate file size
        if audio_file.size > settings.FILE_UPLOAD_MAX_MEMORY_SIZE:
            return JsonResponse({
                'error': f'File too large. Maximum size: {settings.FILE_UPLOAD_MAX_MEMORY_SIZE / (1024*1024):.0f}MB'
            }, status=400)
        
        # Create transcription record
        transcription = Transcription.objects.create(
            filename=audio_file.name,
            original_audio=audio_file,
            status='pending'
        )
        
        # Queue processing task with Celery
        task = process_transcription.delay(str(transcription.id))
        
        # Store task ID in session for tracking
        request.session[f'task_{transcription.id}'] = task.id
        
        # Return partial HTML for HTMX
        if request.headers.get('HX-Request'):
            return render(request, 'transcriber/partials/upload_success.html', {
                'transcription': transcription,
                'task_id': task.id
            })
        
        return redirect('transcriber:detail', pk=transcription.pk)
    
    return render(request, 'transcriber/upload.html')


def detail(request, pk):
    transcription = get_object_or_404(Transcription, pk=pk)
    exports = transcription.exports.all()
    
    # Get task status if available
    task_id = request.session.get(f'task_{transcription.id}')
    task_status = None
    if task_id:
        result = AsyncResult(task_id)
        if result.state == 'PROGRESS':
            task_status = result.info.get('step', 'Processing...')
    
    return render(request, 'transcriber/detail.html', {
        'transcription': transcription,
        'exports': exports,
        'task_status': task_status
    })


@require_http_methods(["GET"])
def status(request, pk):
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Get detailed task status
    task_id = request.session.get(f'task_{transcription.id}')
    task_progress = None
    if task_id and transcription.status == 'processing':
        result = AsyncResult(task_id)
        if result.state == 'PROGRESS':
            task_progress = result.info.get('step', 'Processing...')
    
    # Return partial HTML for HTMX polling
    if request.headers.get('HX-Request'):
        return render(request, 'transcriber/partials/status.html', {
            'transcription': transcription,
            'task_progress': task_progress
        })
    
    # Return JSON for API calls
    return JsonResponse({
        'id': str(transcription.id),
        'status': transcription.status,
        'error_message': transcription.error_message,
        'duration': transcription.duration,
        'estimated_tempo': transcription.estimated_tempo,
        'estimated_key': transcription.estimated_key,
        'complexity': transcription.complexity,
        'detected_instruments': transcription.detected_instruments,
        'task_progress': task_progress
    })


@require_http_methods(["POST"])
def export(request, pk):
    transcription = get_object_or_404(Transcription, pk=pk)
    
    if transcription.status != 'completed':
        return JsonResponse({'error': 'Transcription not completed'}, status=400)
    
    export_format = request.POST.get('format', 'musicxml')
    
    # Check if export already exists
    existing_export = transcription.exports.filter(format=export_format).first()
    if existing_export:
        if request.headers.get('HX-Request'):
            return render(request, 'transcriber/partials/export_link.html', {
                'export': existing_export
            })
        return redirect('transcriber:download', pk=transcription.pk, export_id=existing_export.id)
    
    # Queue export generation task
    task = generate_export.delay(str(transcription.id), export_format)
    
    if request.headers.get('HX-Request'):
        return render(request, 'transcriber/partials/export_pending.html', {
            'format': export_format,
            'task_id': task.id
        })
    
    return JsonResponse({
        'message': 'Export generation started',
        'task_id': task.id
    })


def download(request, pk, export_id):
    transcription = get_object_or_404(Transcription, pk=pk)
    tab_export = get_object_or_404(TabExport, id=export_id, transcription=transcription)
    
    if not tab_export.file:
        return JsonResponse({'error': 'Export file not found'}, status=404)
    
    # Determine content type based on format
    content_types = {
        'musicxml': 'application/xml',
        'gp5': 'application/x-guitar-pro',
        'midi': 'audio/midi',
        'pdf': 'application/pdf',
        'ascii': 'text/plain'
    }
    content_type = content_types.get(tab_export.format, 'application/octet-stream')
    
    response = HttpResponse(tab_export.file.read(), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{transcription.filename}.{tab_export.format}"'
    return response


def library(request):
    transcriptions = Transcription.objects.filter(status='completed')
    
    # Filter by instrument if requested
    instrument = request.GET.get('instrument')
    if instrument:
        transcriptions = transcriptions.filter(detected_instruments__contains=[instrument])
    
    # Filter by complexity
    complexity = request.GET.get('complexity')
    if complexity:
        transcriptions = transcriptions.filter(complexity=complexity)
    
    # Filter by tempo range
    min_tempo = request.GET.get('min_tempo')
    max_tempo = request.GET.get('max_tempo')
    if min_tempo:
        transcriptions = transcriptions.filter(estimated_tempo__gte=int(min_tempo))
    if max_tempo:
        transcriptions = transcriptions.filter(estimated_tempo__lte=int(max_tempo))
    
    return render(request, 'transcriber/library.html', {
        'transcriptions': transcriptions,
        'selected_instrument': instrument,
        'selected_complexity': complexity,
        'min_tempo': min_tempo,
        'max_tempo': max_tempo
    })


@require_http_methods(["DELETE"])
def delete(request, pk):
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Delete associated files
    if transcription.original_audio:
        try:
            os.remove(transcription.original_audio.path)
        except:
            pass
    
    if transcription.gp5_file:
        try:
            os.remove(transcription.gp5_file.path)
        except:
            pass
    
    transcription.delete()
    
    if request.headers.get('HX-Request'):
        return HttpResponse(status=204)
    
    return redirect('transcriber:index')


@require_http_methods(["GET"])
def preview_tab(request, pk):
    """
    Render tab preview using AlphaTab.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    
    if transcription.status != 'completed':
        return JsonResponse({'error': 'Transcription not completed'}, status=400)
    
    return render(request, 'transcriber/partials/tab_preview.html', {
        'transcription': transcription,
        'musicxml': transcription.musicxml_content
    })


@require_http_methods(["GET"])
def get_task_status(request, task_id):
    """
    Get Celery task status.
    """
    result = AsyncResult(task_id)
    
    response_data = {
        'task_id': task_id,
        'state': result.state,
        'info': str(result.info)
    }
    
    if result.state == 'PENDING':
        response_data['info'] = 'Task pending...'
    elif result.state == 'PROGRESS':
        response_data['current'] = result.info.get('current', 0)
        response_data['total'] = result.info.get('total', 1)
        response_data['step'] = result.info.get('step', '')
    elif result.state == 'SUCCESS':
        response_data['result'] = result.result
    elif result.state == 'FAILURE':
        response_data['error'] = str(result.info)
    
    return JsonResponse(response_data)