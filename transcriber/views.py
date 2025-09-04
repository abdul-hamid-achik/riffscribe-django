from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from django.conf import settings
from .models import Transcription, TabExport
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
        
        # Create transcription record
        transcription = Transcription.objects.create(
            filename=audio_file.name,
            original_audio=audio_file,
            status='pending'
        )
        
        # Queue processing task
        from .tasks import process_audio_file_sync
        process_audio_file_sync(str(transcription.id))
        
        # Return partial HTML for HTMX
        if request.headers.get('HX-Request'):
            return render(request, 'transcriber/partials/upload_success.html', {
                'transcription': transcription
            })
        
        return redirect('transcriber:detail', pk=transcription.pk)
    
    return render(request, 'transcriber/upload.html')


def detail(request, pk):
    transcription = get_object_or_404(Transcription, pk=pk)
    exports = transcription.exports.all()
    
    return render(request, 'transcriber/detail.html', {
        'transcription': transcription,
        'exports': exports
    })


@require_http_methods(["GET"])
def status(request, pk):
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Return partial HTML for HTMX polling
    if request.headers.get('HX-Request'):
        return render(request, 'transcriber/partials/status.html', {
            'transcription': transcription
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
        return redirect('transcriber:download', pk=transcription.pk, export_id=existing_export.id)
    
    # Generate export (would be async in production)
    # from .export import generate_export
    # export_file = generate_export(transcription, export_format)
    
    # tab_export = TabExport.objects.create(
    #     transcription=transcription,
    #     format=export_format,
    #     file=export_file
    # )
    
    # if request.headers.get('HX-Request'):
    #     return render(request, 'transcriber/partials/export_link.html', {
    #         'export': tab_export
    #     })
    
    return JsonResponse({'message': 'Export generation coming soon'})


def download(request, pk, export_id):
    transcription = get_object_or_404(Transcription, pk=pk)
    tab_export = get_object_or_404(TabExport, id=export_id, transcription=transcription)
    
    response = HttpResponse(tab_export.file.read(), content_type='application/octet-stream')
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
    
    return render(request, 'transcriber/library.html', {
        'transcriptions': transcriptions,
        'selected_instrument': instrument,
        'selected_complexity': complexity,
    })


@require_http_methods(["DELETE"])
def delete(request, pk):
    transcription = get_object_or_404(Transcription, pk=pk)
    transcription.delete()
    
    if request.headers.get('HX-Request'):
        return HttpResponse(status=204)
    
    return redirect('transcriber:index')
