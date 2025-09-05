"""
Preview views for RiffScribe
Provides interactive preview functionality for transcriptions
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from ..models import Transcription, FingeringVariant
from ..services.export_manager import ExportManager
import json
import base64


def preview_tab(request, pk):
    """
    Main preview page for a transcription.
    Shows interactive tab viewer, MIDI player, and sheet music preview.
    """
    # For preview page, we only need basic info, not the large data fields
    transcription = get_object_or_404(
        Transcription.objects.defer('midi_data', 'whisper_analysis'), 
        pk=pk
    )
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    # Check if transcription is ready for preview
    if transcription.status != 'completed':
        context = {
            'transcription': transcription,
            'preview_available': False,
            'message': 'Preview will be available once transcription is completed.'
        }
        return render(request, 'transcriber/preview.html', context)
    
    # Add variants for selection
    variants = transcription.variants.all().order_by('difficulty_score')
    selected_variant = transcription.variants.filter(is_selected=True).first()
    
    # Add preview modes
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
        'preview_available': True,
        'variants': variants,
        'selected_variant': selected_variant,
        'has_musicxml': bool(transcription.musicxml_content),
        'has_midi': bool(transcription.midi_data),
        'has_guitar_notes': bool(transcription.guitar_notes),
        'preview_modes': preview_modes,
        'download_formats': download_formats,
    }
    
    return render(request, 'transcriber/preview.html', context)


@require_http_methods(["GET"])
def tab_preview_api(request, pk):
    """
    API endpoint for AlphaTab/tab preview data.
    Returns tab data in format suitable for AlphaTab rendering.
    """
    # Only load guitar_notes field needed for tab preview, defer large unrelated data
    transcription = get_object_or_404(
        Transcription.objects.defer('midi_data', 'whisper_analysis', 'musicxml_content'), 
        pk=pk
    )
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    variant_id = request.GET.get('variant_id')
    
    # Get the tab data to preview
    if variant_id:
        variant = get_object_or_404(
            FingeringVariant, 
            id=variant_id, 
            transcription=transcription
        )
        tab_data = variant.tab_data
    else:
        # Use selected variant or main transcription data
        selected_variant = transcription.variants.filter(is_selected=True).first()
        if selected_variant:
            tab_data = selected_variant.tab_data
        else:
            tab_data = transcription.guitar_notes
    
    # Convert to AlphaTab format if needed
    alphatab_data = _convert_to_alphatab_format(transcription, tab_data)
    
    if request.headers.get('HX-Request'):
        return render(request, 'transcriber/partials/tab_preview.html', {
            'transcription': transcription,
            'alphatab_data': json.dumps(alphatab_data),
            'variant_id': variant_id
        })
    
    return JsonResponse(alphatab_data)


def _convert_to_alphatab_format(transcription, tab_data):
    """
    Convert our internal tab format to AlphaTab JSON format.
    AlphaTab can also read MusicXML directly.
    """
    # If we have MusicXML, we can return that for AlphaTab
    if transcription.musicxml_content:
        return {
            'format': 'musicxml',
            'data': transcription.musicxml_content
        }
    
    # Otherwise, convert our guitar_notes to AlphaTab format
    # This is a simplified conversion - you'd expand this based on your actual format
    return {
        'format': 'alphatab',
        'score': {
            'title': transcription.filename,
            'tempo': 120,
            'tracks': [{
                'name': 'Guitar',
                'instrument': 'AcousticGuitarSteel',
                'measures': _convert_measures_to_alphatab(tab_data)
            }]
        }
    }


def _convert_measures_to_alphatab(tab_data):
    """Convert measures to AlphaTab format."""
    if not tab_data or not isinstance(tab_data, dict):
        return []
    
    measures = tab_data.get('measures', [])
    # Simplified conversion - expand based on your actual data structure
    return measures


@require_http_methods(["GET"])
def midi_preview_api(request, pk):
    """
    API endpoint for MIDI preview data.
    Returns MIDI data as base64 for web audio playback.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    if not transcription.midi_data:
        return JsonResponse({'error': 'MIDI data not available'}, status=404)
    
    export_manager = ExportManager(transcription)
    midi_bytes = export_manager.generate_midi_bytes(transcription.midi_data)
    
    # Convert to base64 for web playback
    midi_base64 = base64.b64encode(midi_bytes).decode('utf-8')
    
    return JsonResponse({
        'midi_data': f'data:audio/midi;base64,{midi_base64}',
        'filename': f"{transcription.filename}.mid",
        'duration': _estimate_duration(transcription.midi_data)
    })


def _estimate_duration(midi_data):
    """Estimate MIDI duration in seconds."""
    # This would calculate actual duration from MIDI data
    # For now, return a placeholder
    return 180  # 3 minutes


@require_http_methods(["GET"])
def sheet_music_preview(request, pk):
    """
    Sheet music preview using MusicXML rendering.
    Can use OpenSheetMusicDisplay or similar library.
    """
    # Only load fields needed for sheet music, defer other large data
    transcription = get_object_or_404(
        Transcription.objects.defer('midi_data', 'whisper_analysis'), 
        pk=pk
    )
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    if not transcription.musicxml_content:
        # Generate if not cached
        export_manager = ExportManager(transcription)
        transcription.musicxml_content = export_manager.generate_musicxml(
            transcription.guitar_notes
        )
        transcription.save()
    
    if request.headers.get('HX-Request'):
        return render(request, 'transcriber/partials/sheet_preview.html', {
            'transcription': transcription,
            'musicxml_content': transcription.musicxml_content
        })
    
    return HttpResponse(
        transcription.musicxml_content, 
        content_type='application/xml'
    )


@require_http_methods(["GET"])
def ascii_tab_preview(request, pk):
    """
    ASCII tab preview for simple text-based viewing.
    """
    # Only load guitar_notes field needed for ASCII tab, defer other large data
    transcription = get_object_or_404(
        Transcription.objects.defer('midi_data', 'whisper_analysis', 'musicxml_content'), 
        pk=pk
    )
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    variant_id = request.GET.get('variant_id')
    
    # Get the data to convert
    if variant_id:
        variant = get_object_or_404(
            FingeringVariant,
            id=variant_id,
            transcription=transcription
        )
        tab_data = variant.tab_data
    else:
        tab_data = transcription.guitar_notes
    
    export_manager = ExportManager(transcription)
    ascii_tab = export_manager.generate_ascii_tab(tab_data)
    
    # Format for display (add line numbers, measure markers, etc.)
    formatted_tab = _format_ascii_tab_for_display(ascii_tab)
    
    if request.headers.get('HX-Request'):
        return render(request, 'transcriber/partials/ascii_preview.html', {
            'transcription': transcription,
            'ascii_tab': formatted_tab,
            'variant_id': variant_id
        })
    
    return HttpResponse(formatted_tab, content_type='text/plain')


def _format_ascii_tab_for_display(ascii_tab):
    """Add formatting for better display."""
    lines = ascii_tab.split('\n')
    formatted_lines = []
    measure_count = 0
    
    for line in lines:
        # Add measure markers
        if line.startswith('|'):
            measure_count += line.count('|') - 1
            if measure_count % 4 == 0:
                formatted_lines.append(f"\n[Measure {measure_count}]")
        formatted_lines.append(line)
    
    return '\n'.join(formatted_lines)


@login_required
@require_http_methods(["GET", "POST"])
def preview_settings(request):
    """
    User preview settings and preferences.
    """
    user_profile = request.user.profile
    
    if request.method == "POST":
        # Update preview settings
        settings_fields = [
            'default_preview_mode',
            'show_fingerings', 
            'show_timing',
            'playback_speed',
            'auto_scroll',
            'notation_style'
        ]
        
        for field in settings_fields:
            if field in request.POST:
                value = request.POST[field]
                # Convert boolean strings
                if value in ['true', 'false']:
                    value = value == 'true'
                # Convert numeric strings
                elif field == 'playback_speed':
                    value = float(value)
                setattr(user_profile, field, value)
        
        user_profile.save()
        
        if request.headers.get('HX-Request'):
            return render(request, 'transcriber/partials/settings_saved.html', {
                'message': 'Preview settings updated successfully'
            })
        
        return JsonResponse({'status': 'success'})
    
    # GET request - show settings form
    preview_settings_data = {
        'default_view': getattr(user_profile, 'default_preview_mode', 'tab'),
        'show_fingerings': getattr(user_profile, 'show_fingerings', True),
        'show_timing': getattr(user_profile, 'show_timing', True),
        'playback_speed': getattr(user_profile, 'playback_speed', 1.0),
        'auto_scroll': getattr(user_profile, 'auto_scroll', True),
        'notation_style': getattr(user_profile, 'notation_style', 'standard'),
    }
    
    notation_styles = [
        ('standard', 'Standard Notation'),
        ('tab_only', 'Tab Only'),
        ('both', 'Standard + Tab'),
    ]
    
    return render(request, 'transcriber/preview_settings.html', {
        'preview_settings': preview_settings_data,
        'notation_styles': notation_styles,
    })


@require_http_methods(["GET"])
def comparison_view(request, pk):
    """
    Compare multiple variants side by side.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    variants = transcription.variants.all().order_by('difficulty_score')
    
    # Get comparison data for selected variants
    variant_ids = request.GET.getlist('variants[]')
    if variant_ids:
        selected_variants = transcription.variants.filter(id__in=variant_ids)
    else:
        # Default to comparing easiest and balanced
        selected_variants = transcription.variants.all()[:2]
    
    comparison_data = _generate_comparison_data(selected_variants)
    
    return render(request, 'transcriber/comparison.html', {
        'transcription': transcription,
        'variants': variants,
        'selected_variants': selected_variants,
        'comparison_data': comparison_data,
    })


def _generate_comparison_data(variants):
    """Generate data for side-by-side comparison."""
    from django.db import models
    
    comparison = {
        'metrics': [],
        'techniques': [],
        'difficulty_breakdown': []
    }
    
    for variant in variants:
        # Add metrics
        comparison['metrics'].append({
            'variant': variant,
            'playability': variant.playability_score,
            'difficulty': variant.difficulty_score,
            'avg_fret': variant.measure_stats.aggregate(
                avg_fret=models.Avg('avg_fret')
            )['avg_fret'],
            'max_jump': variant.measure_stats.aggregate(
                max_jump=models.Max('max_jump')
            )['max_jump'],
        })
        
        # Add technique comparison
        comparison['techniques'].append({
            'variant': variant,
            'removed': variant.removed_techniques or [],
            'config': variant.config
        })
    
    return comparison