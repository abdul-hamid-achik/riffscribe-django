"""
Preview views for transcriptions.
Provides interactive preview functionality separate from downloads.
"""
from django.shortcuts import get_object_or_404, render
from django.views.generic import DetailView, TemplateView
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.conf import settings
import json
import base64

from .models import Transcription, FingeringVariant
from .export_manager import ExportManager
from .views_cbv import TranscriptionOwnerMixin, HTMXResponseMixin


class TranscriptionPreviewView(TranscriptionOwnerMixin, DetailView):
    """
    Main preview page for a transcription.
    Shows interactive tab viewer, MIDI player, and sheet music preview.
    """
    model = Transcription
    template_name = 'transcriber/preview.html'
    context_object_name = 'transcription'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        transcription = self.object
        
        # Check if transcription is ready for preview
        if transcription.status != 'completed':
            context['preview_available'] = False
            context['message'] = 'Preview will be available once transcription is completed.'
            return context
        
        context['preview_available'] = True
        
        # Add variants for selection
        context['variants'] = transcription.variants.all().order_by('difficulty_score')
        context['selected_variant'] = transcription.variants.filter(is_selected=True).first()
        
        # Prepare different preview formats
        context['has_musicxml'] = bool(transcription.musicxml_content)
        context['has_midi'] = bool(transcription.midi_data)
        context['has_guitar_notes'] = bool(transcription.guitar_notes)
        
        # Add preview modes
        context['preview_modes'] = [
            {'id': 'tab', 'name': 'Interactive Tab', 'icon': '🎸'},
            {'id': 'sheet', 'name': 'Sheet Music', 'icon': '🎼'},
            {'id': 'midi', 'name': 'MIDI Player', 'icon': '🎵'},
            {'id': 'ascii', 'name': 'ASCII Tab', 'icon': '📝'},
        ]
        
        # Download formats available
        context['download_formats'] = [
            {'format': 'musicxml', 'name': 'MusicXML', 'extension': '.xml'},
            {'format': 'gp5', 'name': 'Guitar Pro 5', 'extension': '.gp5'},
            {'format': 'midi', 'name': 'MIDI', 'extension': '.mid'},
            {'format': 'pdf', 'name': 'PDF', 'extension': '.pdf'},
            {'format': 'ascii', 'name': 'ASCII Tab', 'extension': '.txt'},
        ]
        
        return context


class TabPreviewAPIView(TranscriptionOwnerMixin, HTMXResponseMixin, DetailView):
    """
    API endpoint for AlphaTab/tab preview data.
    Returns tab data in format suitable for AlphaTab rendering.
    """
    model = Transcription
    
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        variant_id = request.GET.get('variant_id')
        
        # Get the tab data to preview
        if variant_id:
            variant = get_object_or_404(
                FingeringVariant, 
                id=variant_id, 
                transcription=self.object
            )
            tab_data = variant.tab_data
        else:
            # Use selected variant or main transcription data
            selected_variant = self.object.variants.filter(is_selected=True).first()
            if selected_variant:
                tab_data = selected_variant.tab_data
            else:
                tab_data = self.object.guitar_notes
        
        # Convert to AlphaTab format if needed
        alphatab_data = self._convert_to_alphatab_format(tab_data)
        
        if self.is_htmx_request():
            return render(request, 'transcriber/partials/tab_preview.html', {
                'transcription': self.object,
                'alphatab_data': json.dumps(alphatab_data),
                'variant_id': variant_id
            })
        
        return JsonResponse(alphatab_data)
    
    def _convert_to_alphatab_format(self, tab_data):
        """
        Convert our internal tab format to AlphaTab JSON format.
        AlphaTab can also read MusicXML directly.
        """
        # If we have MusicXML, we can return that for AlphaTab
        if self.object.musicxml_content:
            return {
                'format': 'musicxml',
                'data': self.object.musicxml_content
            }
        
        # Otherwise, convert our guitar_notes to AlphaTab format
        # This is a simplified conversion - you'd expand this based on your actual format
        return {
            'format': 'alphatab',
            'score': {
                'title': self.object.filename,
                'tempo': 120,
                'tracks': [{
                    'name': 'Guitar',
                    'instrument': 'AcousticGuitarSteel',
                    'measures': self._convert_measures_to_alphatab(tab_data)
                }]
            }
        }
    
    def _convert_measures_to_alphatab(self, tab_data):
        """Convert measures to AlphaTab format."""
        if not tab_data or not isinstance(tab_data, dict):
            return []
        
        measures = tab_data.get('measures', [])
        # Simplified conversion - expand based on your actual data structure
        return measures


class MIDIPreviewAPIView(TranscriptionOwnerMixin, DetailView):
    """
    API endpoint for MIDI preview data.
    Returns MIDI data as base64 for web audio playback.
    """
    model = Transcription
    
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        
        if not self.object.midi_data:
            return JsonResponse({'error': 'MIDI data not available'}, status=404)
        
        export_manager = ExportManager(self.object)
        midi_bytes = export_manager.generate_midi_bytes(self.object.midi_data)
        
        # Convert to base64 for web playback
        midi_base64 = base64.b64encode(midi_bytes).decode('utf-8')
        
        return JsonResponse({
            'midi_data': f'data:audio/midi;base64,{midi_base64}',
            'filename': f"{self.object.filename}.mid",
            'duration': self._estimate_duration(self.object.midi_data)
        })
    
    def _estimate_duration(self, midi_data):
        """Estimate MIDI duration in seconds."""
        # This would calculate actual duration from MIDI data
        # For now, return a placeholder
        return 180  # 3 minutes


class SheetMusicPreviewView(TranscriptionOwnerMixin, HTMXResponseMixin, DetailView):
    """
    Sheet music preview using MusicXML rendering.
    Can use OpenSheetMusicDisplay or similar library.
    """
    model = Transcription
    
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        
        if not self.object.musicxml_content:
            # Generate if not cached
            export_manager = ExportManager(self.object)
            self.object.musicxml_content = export_manager.generate_musicxml(
                self.object.guitar_notes
            )
            self.object.save()
        
        if self.is_htmx_request():
            return render(request, 'transcriber/partials/sheet_preview.html', {
                'transcription': self.object,
                'musicxml_content': self.object.musicxml_content
            })
        
        return HttpResponse(
            self.object.musicxml_content, 
            content_type='application/xml'
        )


class ASCIITabPreviewView(TranscriptionOwnerMixin, HTMXResponseMixin, DetailView):
    """
    ASCII tab preview for simple text-based viewing.
    """
    model = Transcription
    
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        variant_id = request.GET.get('variant_id')
        
        # Get the data to convert
        if variant_id:
            variant = get_object_or_404(
                FingeringVariant,
                id=variant_id,
                transcription=self.object
            )
            tab_data = variant.tab_data
        else:
            tab_data = self.object.guitar_notes
        
        export_manager = ExportManager(self.object)
        ascii_tab = export_manager.generate_ascii_tab(tab_data)
        
        # Format for display (add line numbers, measure markers, etc.)
        formatted_tab = self._format_ascii_tab_for_display(ascii_tab)
        
        if self.is_htmx_request():
            return render(request, 'transcriber/partials/ascii_preview.html', {
                'transcription': self.object,
                'ascii_tab': formatted_tab,
                'variant_id': variant_id
            })
        
        return HttpResponse(formatted_tab, content_type='text/plain')
    
    def _format_ascii_tab_for_display(self, ascii_tab):
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


class PreviewSettingsView(LoginRequiredMixin, HTMXResponseMixin, TemplateView):
    """
    User preview settings and preferences.
    """
    template_name = 'transcriber/preview_settings.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_profile = self.request.user.profile
        
        # Get user's preview preferences
        context['preview_settings'] = {
            'default_view': getattr(user_profile, 'default_preview_mode', 'tab'),
            'show_fingerings': getattr(user_profile, 'show_fingerings', True),
            'show_timing': getattr(user_profile, 'show_timing', True),
            'playback_speed': getattr(user_profile, 'playback_speed', 1.0),
            'auto_scroll': getattr(user_profile, 'auto_scroll', True),
            'notation_style': getattr(user_profile, 'notation_style', 'standard'),
        }
        
        context['notation_styles'] = [
            ('standard', 'Standard Notation'),
            ('tab_only', 'Tab Only'),
            ('both', 'Standard + Tab'),
        ]
        
        return context
    
    def post(self, request, *args, **kwargs):
        user_profile = request.user.profile
        
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
        
        if self.is_htmx_request():
            return render(request, 'transcriber/partials/settings_saved.html', {
                'message': 'Preview settings updated successfully'
            })
        
        return JsonResponse({'status': 'success'})


class ComparisonView(TranscriptionOwnerMixin, TemplateView):
    """
    Compare multiple variants side by side.
    """
    template_name = 'transcriber/comparison.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        transcription = get_object_or_404(Transcription, pk=self.kwargs['pk'])
        
        context['transcription'] = transcription
        context['variants'] = transcription.variants.all().order_by('difficulty_score')
        
        # Get comparison data for selected variants
        variant_ids = self.request.GET.getlist('variants[]')
        if variant_ids:
            selected_variants = transcription.variants.filter(id__in=variant_ids)
        else:
            # Default to comparing easiest and balanced
            selected_variants = transcription.variants.all()[:2]
        
        context['selected_variants'] = selected_variants
        context['comparison_data'] = self._generate_comparison_data(selected_variants)
        
        return context
    
    def _generate_comparison_data(self, variants):
        """Generate data for side-by-side comparison."""
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