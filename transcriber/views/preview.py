"""
Preview views for RiffScribe
Handles tab preview with AlphaTab, MIDI player, and sheet music display
"""
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from ..models import Transcription


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