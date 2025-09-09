"""
Variant management views
Handles fingering variants, selection, regeneration, and variant-specific exports
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from celery.result import AsyncResult
from ..models import Transcription, FingeringVariant, PlayabilityMetrics
from ..tasks import generate_variants
from ..services.export_manager import ExportManager
import json


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
    
    # Always return JSON for consistent JavaScript handling
    return JsonResponse({
        'status': 'success',
        'selected_variant': variant.get_variant_name_display(),
        'variant_id': str(variant.id),
        'playability_score': variant.playability_score,
        'difficulty_score': variant.difficulty_score,
        'stretch_score': getattr(variant, 'stretch_score', 0)
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
        from ..services.tab_generator import TabGenerator
        # Generate a minimal ASCII preview using the generator's public API
        notes = []
        if isinstance(preview_data, dict) and 'measures' in preview_data:
            # Flatten notes for a quick preview
            for measure in preview_data['measures']:
                for n in measure.get('notes', []):
                    notes.append({
                        'start_time': measure.get('start_time', 0) + n.get('time', 0),
                        'end_time': measure.get('start_time', 0) + n.get('time', 0) + n.get('duration', 0.25),
                        'midi_note': preview_data.get('tuning', TabGenerator.STANDARD_TUNING)[n.get('string', 0)] + n.get('fret', 0),
                        'velocity': n.get('velocity', 80)
                    })
        tab_gen = TabGenerator(notes, preview_data.get('tempo', 120), preview_data.get('time_signature', '4/4'))
        ascii_tab = tab_gen.to_ascii_tab(measures_per_line=2)
        
        return render(request, 'transcriber/partials/variant_preview.html', {
            'variant': variant,
            'ascii_tab': ascii_tab,
            'measure_count': preview_measures,
            'transcription': transcription
        })
    
    # Non-HTMX: return MusicXML preview for compatibility with tests
    export_manager = ExportManager(transcription)
    xml = export_manager.generate_musicxml(preview_data)
    return HttpResponse(xml, content_type='application/xml')


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