from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.conf import settings
from .models import Transcription, TabExport, FingeringVariant, PlayabilityMetrics, UserProfile
from .tasks import process_transcription, generate_export, generate_variants
from .export_manager import ExportManager
from celery.result import AsyncResult
import json
import os


def index(request):
    # Show user's transcriptions if authenticated, otherwise show recent public ones
    if request.user.is_authenticated:
        transcriptions = Transcription.objects.filter(user=request.user)[:10]
    else:
        transcriptions = Transcription.objects.filter(user__isnull=True)[:10]
    
    return render(request, 'transcriber/index.html', {
        'transcriptions': transcriptions
    })


@require_http_methods(["GET", "POST"])
def upload(request):
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
        
        # Validate file extension
        allowed_extensions = ['.mp3', '.wav', '.m4a', '.flac', '.ogg']
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
            
            # Queue processing task with Celery
            try:
                task = process_transcription.delay(str(transcription.id))
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
                return JsonResponse({'error': 'Processing service unavailable'}, status=500)
            
            # Return partial HTML for HTMX
            if is_htmx:
                return render(request, 'transcriber/partials/upload_success.html', {
                    'transcription': transcription,
                    'task_id': task.id if 'task' in locals() else None
                })
            
            return redirect('transcriber:detail', pk=transcription.pk)
            
        except Exception as e:
            error_msg = f'Failed to save file: {str(e)}'
            if is_htmx:
                return render(request, 'transcriber/partials/upload_error.html', {
                    'error': error_msg
                }, status=500)
            return JsonResponse({'error': error_msg}, status=500)
    
    return render(request, 'transcriber/upload.html')


def library(request):
    # Filter by user if authenticated
    if request.user.is_authenticated:
        transcriptions = Transcription.objects.filter(user=request.user).order_by('-created_at')
    else:
        transcriptions = Transcription.objects.filter(user__isnull=True).order_by('-created_at')[:20]
    
    return render(request, 'transcriber/library.html', {
        'transcriptions': transcriptions
    })


def detail(request, pk):
    transcription = get_object_or_404(Transcription, pk=pk)
    
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
        task_status = {
            'state': result.state,
            'info': result.info
        }
    
    return render(request, 'transcriber/detail.html', {
        'transcription': transcription,
        'variants': variants,
        'metrics': metrics,
        'task_status': task_status
    })


@require_http_methods(["GET", "POST"])
def export(request, pk):
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    if request.method == "POST":
        export_format = request.POST.get('format', 'musicxml')
        
        # Check if export already exists
        existing_export = TabExport.objects.filter(
            transcription=transcription,
            format=export_format
        ).first()
        
        if existing_export:
            return redirect(existing_export.file.url)
        
        # Queue export task
        task = generate_export.delay(str(transcription.id), export_format)
        
        # Return task ID for tracking
        return JsonResponse({
            'task_id': task.id,
            'format': export_format
        })
    
    return render(request, 'transcriber/export.html', {
        'transcription': transcription
    })


@require_http_methods(["GET"])
def status(request, pk):
    """
    Get transcription processing status.
    Returns appropriate partial HTML for HTMX requests.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Get task ID from session
    task_id = request.session.get(f'task_{transcription.id}')
    
    # Check if this is an HTMX request
    is_htmx = request.headers.get('HX-Request')
    
    if task_id and transcription.status in ['pending', 'processing']:
        result = AsyncResult(task_id)
        
        if is_htmx:
            # Return appropriate status partial
            context = {
                'transcription': transcription,
                'state': result.state,
                'task_id': task_id
            }
            
            if result.state == 'PROGRESS':
                context['step'] = result.info.get('step', 'Processing...')
                context['current'] = result.info.get('current', 0)
                context['total'] = result.info.get('total', 100)
            elif result.state == 'SUCCESS':
                # Refresh transcription from database
                transcription.refresh_from_db()
                context['transcription'] = transcription
            
            return render(request, 'transcriber/partials/status.html', context)
        
        # JSON response for non-HTMX requests
        response_data = {
            'status': transcription.status,
            'task_state': result.state,
            'task_info': str(result.info) if result.state != 'SUCCESS' else 'Complete'
        }
        
        if result.state == 'PROGRESS':
            response_data['step'] = result.info.get('step', 'Processing...')
            response_data['progress'] = {
                'current': result.info.get('current', 0),
                'total': result.info.get('total', 100)
            }
        
        return JsonResponse(response_data)
    
    # No task or completed
    if is_htmx:
        return render(request, 'transcriber/partials/status.html', {
            'transcription': transcription,
            'state': 'COMPLETED' if transcription.status == 'completed' else transcription.status.upper()
        })
    
    return JsonResponse({'status': transcription.status})


@require_http_methods(["POST"])
def select_variant(request, pk, variant_id):
    """
    Select a specific fingering variant as the active one.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    variant = get_object_or_404(FingeringVariant, id=variant_id, transcription=transcription)
    
    # Mark this variant as selected (model's save() handles deselecting others)
    variant.is_selected = True
    variant.save()
    
    # Update the transcription's guitar_notes with the selected variant's data
    transcription.guitar_notes = variant.tab_data
    transcription.save()
    
    # Update or create playability metrics for this variant
    metrics, created = PlayabilityMetrics.objects.get_or_create(transcription=transcription)
    metrics.playability_score = variant.playability_score
    metrics.recommended_skill_level = variant.variant_name  # Map variant type to skill level
    
    # Calculate physical constraints from the variant's measure stats
    measure_stats = variant.measure_stats.all()
    if measure_stats:
        metrics.max_fret_span = max(stat.chord_span for stat in measure_stats)
        metrics.position_changes = sum(1 for stat in measure_stats if stat.max_jump > 4)
        
    metrics.save()
    
    if request.headers.get('HX-Request'):
        return render(request, 'transcriber/partials/variant_selected.html', {
            'variant': variant,
            'transcription': transcription
        })
    
    return JsonResponse({
        'status': 'success',
        'selected_variant': variant.variant_name,
        'playability_score': variant.playability_score
    })


@require_http_methods(["GET"])
def variant_preview(request, pk, variant_id):
    """
    Preview a variant's tab data without selecting it.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    variant = get_object_or_404(FingeringVariant, id=variant_id, transcription=transcription)
    
    # Get first few measures for preview
    tab_data = variant.tab_data
    preview_measures = 8  # Show first 8 measures
    
    if isinstance(tab_data, dict) and 'measures' in tab_data:
        preview_data = {
            **tab_data,
            'measures': tab_data['measures'][:preview_measures]
        }
    else:
        preview_data = tab_data
    
    if request.headers.get('HX-Request'):
        # Convert tab data to displayable format
        from .tab_generator import TabGenerator
        tab_gen = TabGenerator([], 120)  # Dummy init
        ascii_tab = tab_gen._format_as_ascii_tab(preview_data)
        
        return render(request, 'transcriber/partials/variant_preview.html', {
            'variant': variant,
            'ascii_tab': ascii_tab,
            'measure_count': preview_measures
        })
    
    return JsonResponse({
        'variant_id': str(variant.id),
        'variant_name': variant.variant_name,
        'preview_data': preview_data
    })


@require_http_methods(["GET"])
def export_musicxml(request, pk):
    """
    Export transcription as MusicXML.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    # Check if MusicXML content exists
    if transcription.musicxml_content:
        musicxml_content = transcription.musicxml_content
    else:
        # Generate MusicXML if not cached
        export_manager = ExportManager(transcription)
        musicxml_content = export_manager.generate_musicxml(transcription.guitar_notes)
        
        # Cache it
        transcription.musicxml_content = musicxml_content
        transcription.save()
    
    # Return as downloadable file or for display
    if request.GET.get('download'):
        response = HttpResponse(musicxml_content, content_type='application/xml')
        response['Content-Disposition'] = f'attachment; filename="{transcription.filename}.musicxml"'
        return response
    
    # For HTMX requests, return formatted display
    if request.headers.get('HX-Request'):
        return render(request, 'transcriber/partials/musicxml_display.html', {
            'transcription': transcription,
            'musicxml': musicxml_content
        })
    
    return HttpResponse(musicxml_content, content_type='application/xml')


@require_http_methods(["GET"])
def get_task_status(request, task_id):
    """
    Get Celery task status.
    """
    result = AsyncResult(task_id)
    is_htmx = request.headers.get('HX-Request')
    
    # For HTMX requests, return appropriate HTML templates
    if is_htmx:
        if result.state == 'PENDING':
            return render(request, 'transcriber/partials/export_pending.html', {
                'task_id': task_id,
                'format': 'Export'
            })
        elif result.state == 'PROGRESS':
            return render(request, 'transcriber/partials/export_pending.html', {
                'task_id': task_id,
                'format': 'Export',
                'progress': result.info.get('current', 0),
                'total': result.info.get('total', 1),
                'step': result.info.get('step', '')
            })
        elif result.state == 'SUCCESS':
            # Task completed successfully - render the export link
            task_result = result.result
            if task_result and 'export_id' in task_result:
                from .models import TabExport
                try:
                    export = TabExport.objects.get(id=task_result['export_id'])
                    return render(request, 'transcriber/partials/export_link.html', {
                        'export': export
                    })
                except TabExport.DoesNotExist:
                    pass
            return render(request, 'transcriber/partials/export_error.html', {
                'error': 'Export completed but file not found'
            })
        elif result.state == 'FAILURE':
            return render(request, 'transcriber/partials/export_error.html', {
                'error': str(result.info)
            })
    
    # For non-HTMX requests, return JSON (keep original behavior)
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


@require_http_methods(["GET"])
def download(request, pk, export_id):
    """
    Download a specific export file.
    """
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


@require_http_methods(["GET"])
def preview_tab(request, pk):
    """
    Enhanced preview page for a transcription.
    Shows interactive tab viewer, MIDI player, and sheet music preview.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    # Check if transcription is ready for preview
    preview_available = transcription.status == 'completed'
    
    # Get variants for selection
    variants = transcription.variants.all().order_by('difficulty_score')
    selected_variant = transcription.variants.filter(is_selected=True).first()
    
    # Prepare different preview formats
    has_musicxml = bool(transcription.musicxml_content)
    has_midi = bool(transcription.midi_data)
    has_guitar_notes = bool(transcription.guitar_notes)
    
    # Preview modes
    preview_modes = [
        {'id': 'tab', 'name': 'Interactive Tab', 'icon': '🎸'},
        {'id': 'sheet', 'name': 'Sheet Music', 'icon': '🎼'},
        {'id': 'midi', 'name': 'MIDI Player', 'icon': '🎵'},
        {'id': 'ascii', 'name': 'ASCII Tab', 'icon': '📝'},
    ]
    
    # Download formats available
    download_formats = [
        {'format': 'musicxml', 'name': 'MusicXML', 'extension': '.xml'},
        {'format': 'gp5', 'name': 'Guitar Pro 5', 'extension': '.gp5'},
        {'format': 'midi', 'name': 'MIDI', 'extension': '.mid'},
        {'format': 'pdf', 'name': 'PDF', 'extension': '.pdf'},
        {'format': 'ascii', 'name': 'ASCII Tab', 'extension': '.txt'},
    ]
    
    context = {
        'transcription': transcription,
        'preview_available': preview_available,
        'variants': variants,
        'selected_variant': selected_variant,
        'has_musicxml': has_musicxml,
        'has_midi': has_midi,
        'has_guitar_notes': has_guitar_notes,
        'preview_modes': preview_modes,
        'download_formats': download_formats,
    }
    
    if not preview_available:
        context['message'] = 'Preview will be available once transcription is completed.'
    
    # Check if this is a partial request (HTMX)
    if request.headers.get('HX-Request'):
        return render(request, 'transcriber/partials/tab_preview.html', context)
    
    # Full page render - use the comprehensive preview template
    return render(request, 'transcriber/preview.html', context)


@require_http_methods(["GET"])
def variants_list(request, pk):
    """
    List all fingering variants for a transcription.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    variants = transcription.variants.all().order_by('difficulty_score')
    metrics = getattr(transcription, 'metrics', None)
    
    if request.headers.get('HX-Request'):
        return render(request, 'transcriber/partials/variants_list.html', {
            'transcription': transcription,
            'variants': variants,
            'metrics': metrics
        })
    
    return JsonResponse({
        'transcription_id': str(transcription.id),
        'variants': [
            {
                'id': str(v.id),
                'name': v.variant_name,
                'display_name': v.get_variant_name_display(),
                'difficulty_score': v.difficulty_score,
                'playability_score': v.playability_score,
                'is_selected': v.is_selected,
                'removed_techniques': v.removed_techniques
            }
            for v in variants
        ],
        'metrics': {
            'playability_score': metrics.playability_score if metrics else None,
            'recommended_skill_level': metrics.recommended_skill_level if metrics else None,
            'max_fret_span': metrics.max_fret_span if metrics else None,
            'position_changes': metrics.position_changes if metrics else None,
        } if metrics else None
    })


@require_http_methods(["GET"])
def check_generation_status(request, pk, task_id):
    """
    Check the status of variant generation task.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    result = AsyncResult(task_id)
    
    if request.headers.get('HX-Request'):
        if result.state == 'SUCCESS':
            # Refresh variants list
            variants = transcription.variants.all().order_by('difficulty_score')
            metrics = getattr(transcription, 'metrics', None)
            return render(request, 'transcriber/partials/variants_list.html', {
                'transcription': transcription,
                'variants': variants,
                'metrics': metrics
            })
        elif result.state == 'FAILURE':
            return render(request, 'transcriber/partials/variant_error.html', {
                'error': str(result.info)
            })
        else:
            # Still processing
            return render(request, 'transcriber/partials/variants_regenerating.html', {
                'transcription': transcription,
                'task_id': task_id,
                'state': result.state
            })
    
    return JsonResponse({
        'state': result.state,
        'info': str(result.info) if result.state != 'SUCCESS' else 'Complete'
    })


@require_http_methods(["GET"])
def download_gp5(request, pk):
    """
    Download Guitar Pro 5 file.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    if transcription.gp5_file:
        response = HttpResponse(
            transcription.gp5_file.read(),
            content_type='application/x-guitar-pro'
        )
        response['Content-Disposition'] = f'attachment; filename="{transcription.filename}.gp5"'
        return response
    
    # Generate if not exists
    export_manager = ExportManager(transcription)
    gp5_path = export_manager.generate_gp5(transcription.guitar_notes)
    
    if gp5_path and os.path.exists(gp5_path):
        with open(gp5_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/x-guitar-pro')
            response['Content-Disposition'] = f'attachment; filename="{transcription.filename}.gp5"'
            return response
    
    return HttpResponse('Guitar Pro file not available', status=404)


@require_http_methods(["GET"])
def download_ascii_tab(request, pk):
    """
    Download ASCII tab.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    export_manager = ExportManager(transcription)
    ascii_tab = export_manager.generate_ascii_tab(transcription.guitar_notes)
    
    if request.headers.get('HX-Request'):
        return render(request, 'transcriber/partials/ascii_tab_display.html', {
            'transcription': transcription,
            'ascii_tab': ascii_tab
        })
    
    response = HttpResponse(ascii_tab, content_type='text/plain')
    response['Content-Disposition'] = f'attachment; filename="{transcription.filename}_tab.txt"'
    return response


@require_http_methods(["GET"])
def download_midi(request, pk):
    """
    Download MIDI file.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    if not transcription.midi_data:
        return HttpResponse('MIDI data not available', status=404)
    
    export_manager = ExportManager(transcription)
    midi_content = export_manager.generate_midi_bytes(transcription.midi_data)
    
    response = HttpResponse(midi_content, content_type='audio/midi')
    response['Content-Disposition'] = f'attachment; filename="{transcription.filename}.mid"'
    return response


@require_http_methods(["POST"])
def regenerate_variants(request, pk):
    """
    Regenerate all variants for a transcription.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    # Queue variant regeneration task
    preset = request.POST.get('preset')  # Optional: regenerate specific preset
    task = generate_variants.delay(str(transcription.id), preset)
    
    if request.headers.get('HX-Request'):
        return render(request, 'transcriber/partials/variants_regenerating.html', {
            'transcription': transcription,
            'task_id': task.id,
            'preset': preset
        })
    
    return JsonResponse({
        'status': 'started',
        'task_id': task.id,
        'preset': preset
    })


@require_http_methods(["GET"])
def variant_stats(request, pk, variant_id):
    """
    Get detailed statistics for a specific variant.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    variant = get_object_or_404(FingeringVariant, id=variant_id, transcription=transcription)
    
    measure_stats = variant.measure_stats.all().order_by('measure_number')
    
    if request.headers.get('HX-Request'):
        return render(request, 'transcriber/partials/variant_stats.html', {
            'variant': variant,
            'measure_stats': measure_stats
        })
    
    return JsonResponse({
        'variant_id': str(variant.id),
        'variant_name': variant.variant_name,
        'playability_score': variant.playability_score,
        'difficulty_score': variant.difficulty_score,
        'config': variant.config,
        'removed_techniques': variant.removed_techniques,
        'measure_stats': [
            {
                'measure': stat.measure_number,
                'avg_fret': stat.avg_fret,
                'max_jump': stat.max_jump,
                'chord_span': stat.chord_span,
                'string_crossings': stat.string_crossings
            }
            for stat in measure_stats
        ]
    })


@require_http_methods(["GET"])
def export_variant(request, pk, variant_id):
    """
    Export a specific variant (without selecting it).
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    variant = get_object_or_404(FingeringVariant, id=variant_id, transcription=transcription)
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    export_format = request.GET.get('format', 'musicxml')
    
    # Generate export with variant's tab data
    export_manager = ExportManager(transcription)
    
    if export_format == 'musicxml':
        content = export_manager.generate_musicxml(variant.tab_data)
        content_type = 'application/xml'
        extension = 'xml'
    elif export_format == 'gp5':
        # Generate GP5 with variant data
        content = export_manager.generate_gp5_bytes(variant.tab_data)
        content_type = 'application/x-guitar-pro'
        extension = 'gp5'
    elif export_format == 'ascii':
        content = export_manager.generate_ascii_tab(variant.tab_data)
        content_type = 'text/plain'
        extension = 'txt'
    else:
        return JsonResponse({'error': 'Unsupported format'}, status=400)
    
    response = HttpResponse(content, content_type=content_type)
    filename = f"{transcription.filename}_{variant.variant_name}.{extension}"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ====== NEW USER AUTHENTICATION VIEWS ======

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
    
    context = {
        'user_profile': user_profile,
        'genre_choices': [
            'Rock', 'Blues', 'Jazz', 'Metal', 'Classical',
            'Pop', 'Country', 'Folk', 'Indie', 'Alternative'
        ]
    }
    
    return render(request, 'transcriber/profile.html', context)


@login_required
@require_http_methods(["POST"])
def toggle_favorite(request, pk):
    """
    Toggle a transcription as favorite.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Check ownership
    if transcription.user != request.user:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    user_profile = request.user.profile
    
    if transcription in user_profile.favorite_transcriptions.all():
        user_profile.favorite_transcriptions.remove(transcription)
        is_favorited = False
    else:
        user_profile.favorite_transcriptions.add(transcription)
        is_favorited = True
    
    if request.headers.get('HX-Request'):
        return render(request, 'transcriber/partials/favorite_button.html', {
            'transcription': transcription,
            'is_favorited': is_favorited
        })
    
    return JsonResponse({
        'status': 'success',
        'is_favorited': is_favorited
    })


@login_required
@require_http_methods(["DELETE"])
def delete_transcription(request, pk):
    """
    Delete a transcription.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Check ownership
    if transcription.user != request.user:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    # Delete associated files
    if transcription.original_audio:
        if os.path.exists(transcription.original_audio.path):
            os.remove(transcription.original_audio.path)
    
    if transcription.gp5_file:
        if os.path.exists(transcription.gp5_file.path):
            os.remove(transcription.gp5_file.path)
    
    transcription.delete()
    
    if request.headers.get('HX-Request'):
        return HttpResponse(status=204)  # No content, item deleted
    
    return JsonResponse({'status': 'success'})