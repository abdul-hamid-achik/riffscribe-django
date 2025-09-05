"""
Class-based views for the transcriber app.
Refactored for better maintainability and code reuse.
"""
from django.shortcuts import get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse, Http404
from django.views import View
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView,
    TemplateView, FormView
)
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.files.storage import default_storage
from django.conf import settings
from django.urls import reverse_lazy
from django.db.models import Q
from celery.result import AsyncResult
import json
import os

from .models import (
    Transcription, TabExport, FingeringVariant, 
    PlayabilityMetrics, UserProfile
)
from .tasks import process_transcription, generate_export, generate_variants
from .export_manager import ExportManager


# ============= MIXINS =============

class TranscriptionOwnerMixin(UserPassesTestMixin):
    """Mixin to verify user owns the transcription or is superuser."""
    
    def test_func(self):
        transcription = self.get_object()
        return (
            transcription.user == self.request.user or 
            self.request.user.is_superuser or
            transcription.user is None  # Public transcription
        )
    
    def handle_no_permission(self):
        if self.request.headers.get('HX-Request'):
            return HttpResponse('Access denied', status=403)
        return JsonResponse({'error': 'Access denied'}, status=403)


class HTMXResponseMixin:
    """Mixin to handle HTMX vs regular JSON responses."""
    
    def is_htmx_request(self):
        return self.request.headers.get('HX-Request')
    
    def render_htmx_or_json(self, htmx_template, context=None, json_data=None, status=200):
        """Render HTMX template or return JSON based on request type."""
        if self.is_htmx_request():
            return self.render_to_response(
                self.get_context_data(**context) if context else {},
                template_name=htmx_template,
                status=status
            )
        return JsonResponse(json_data or {}, status=status)


class UserProfileMixin:
    """Mixin to add user profile to context."""
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context['user_profile'] = self.request.user.profile
        return context


# ============= BASE VIEWS =============

class IndexView(TemplateView):
    """Home page view showing recent transcriptions."""
    template_name = 'transcriber/index.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        if self.request.user.is_authenticated:
            transcriptions = Transcription.objects.filter(
                user=self.request.user
            )[:10]
        else:
            transcriptions = Transcription.objects.filter(
                user__isnull=True
            )[:10]
        
        context['transcriptions'] = transcriptions
        return context


class LibraryView(ListView):
    """Library view showing user's or public transcriptions."""
    model = Transcription
    template_name = 'transcriber/library.html'
    context_object_name = 'transcriptions'
    paginate_by = 20
    
    def get_queryset(self):
        if self.request.user.is_authenticated:
            return Transcription.objects.filter(
                user=self.request.user
            ).order_by('-created_at')
        return Transcription.objects.filter(
            user__isnull=True
        ).order_by('-created_at')


# ============= UPLOAD VIEWS =============

class UploadView(HTMXResponseMixin, FormView):
    """Handle audio file uploads with validation."""
    template_name = 'transcriber/upload.html'
    
    def get(self, request, *args, **kwargs):
        return self.render_to_response(self.get_context_data())
    
    def post(self, request, *args, **kwargs):
        # Validate file presence
        if 'audio_file' not in request.FILES:
            return self._handle_error('No file provided. Please select an audio file.')
        
        audio_file = request.FILES['audio_file']
        
        # Validate file extension
        allowed_extensions = ['.mp3', '.wav', '.m4a', '.flac', '.ogg']
        file_ext = os.path.splitext(audio_file.name)[1].lower()
        
        if file_ext not in allowed_extensions:
            return self._handle_error(
                f'Invalid file format. Allowed: {", ".join(allowed_extensions)}'
            )
        
        # Validate file size
        max_size = getattr(settings, 'MAX_AUDIO_FILE_SIZE', 100 * 1024 * 1024)
        if audio_file.size > max_size:
            return self._handle_error(
                f'File too large. Maximum size: {max_size / (1024*1024):.0f}MB'
            )
        
        # Check user upload limits if authenticated
        if request.user.is_authenticated and hasattr(request.user, 'profile'):
            profile = request.user.profile
            if not profile.can_upload():
                return self._handle_error(
                    'Monthly upload limit reached. Please upgrade to premium.'
                )
        
        try:
            # Create transcription
            transcription = self._create_transcription(audio_file)
            
            # Update user usage stats
            if request.user.is_authenticated and hasattr(request.user, 'profile'):
                request.user.profile.increment_usage()
            
            # Queue processing task
            task = self._queue_processing(transcription)
            
            # Return success response
            if self.is_htmx_request():
                return self.render_to_response({
                    'transcription': transcription,
                    'task_id': task.id if task else None
                }, template_name='transcriber/partials/upload_success.html')
            
            return redirect('transcriber:detail', pk=transcription.pk)
            
        except Exception as e:
            return self._handle_error(f'Failed to save file: {str(e)}')
    
    def _create_transcription(self, audio_file):
        """Create and return transcription object."""
        return Transcription.objects.create(
            user=self.request.user if self.request.user.is_authenticated else None,
            filename=audio_file.name,
            original_audio=audio_file,
            status='pending'
        )
    
    def _queue_processing(self, transcription):
        """Queue processing task with Celery."""
        try:
            task = process_transcription.delay(str(transcription.id))
            self.request.session[f'task_{transcription.id}'] = task.id
            return task
        except Exception as e:
            transcription.status = 'failed'
            transcription.error_message = f'Failed to queue processing: {str(e)}'
            transcription.save()
            return None
    
    def _handle_error(self, error_msg):
        """Handle error responses for HTMX and JSON."""
        if self.is_htmx_request():
            return self.render_to_response(
                {'error': error_msg},
                template_name='transcriber/partials/upload_error.html',
                status=400
            )
        return JsonResponse({'error': error_msg}, status=400)


# ============= TRANSCRIPTION VIEWS =============

class TranscriptionDetailView(TranscriptionOwnerMixin, DetailView):
    """Detail view for a transcription with variants and metrics."""
    model = Transcription
    template_name = 'transcriber/detail.html'
    context_object_name = 'transcription'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        transcription = self.object
        
        # Add variants and metrics
        context['variants'] = transcription.variants.all().order_by('difficulty_score')
        context['metrics'] = getattr(transcription, 'metrics', None)
        
        # Add task status if processing
        task_id = self.request.session.get(f'task_{transcription.id}')
        if task_id and transcription.status == 'processing':
            result = AsyncResult(task_id)
            context['task_status'] = {
                'state': result.state,
                'info': result.info
            }
        
        return context


class TranscriptionStatusView(TranscriptionOwnerMixin, HTMXResponseMixin, DetailView):
    """Get transcription processing status."""
    model = Transcription
    
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        task_id = request.session.get(f'task_{self.object.id}')
        
        if task_id and self.object.status in ['pending', 'processing']:
            result = AsyncResult(task_id)
            
            if self.is_htmx_request():
                context = {
                    'transcription': self.object,
                    'state': result.state,
                    'task_id': task_id
                }
                
                if result.state == 'PROGRESS':
                    context.update({
                        'step': result.info.get('step', 'Processing...'),
                        'current': result.info.get('current', 0),
                        'total': result.info.get('total', 100)
                    })
                elif result.state == 'SUCCESS':
                    self.object.refresh_from_db()
                    context['transcription'] = self.object
                
                return self.render_to_response(
                    context,
                    template_name='transcriber/partials/status.html'
                )
            
            # JSON response
            response_data = {
                'status': self.object.status,
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
        if self.is_htmx_request():
            return self.render_to_response({
                'transcription': self.object,
                'state': 'COMPLETED' if self.object.status == 'completed' else self.object.status.upper()
            }, template_name='transcriber/partials/status.html')
        
        return JsonResponse({'status': self.object.status})


class TranscriptionDeleteView(LoginRequiredMixin, TranscriptionOwnerMixin, DeleteView):
    """Delete a transcription and its associated files."""
    model = Transcription
    success_url = reverse_lazy('transcriber:library')
    
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        
        # Delete associated files
        if self.object.original_audio:
            if os.path.exists(self.object.original_audio.path):
                os.remove(self.object.original_audio.path)
        
        if self.object.gp5_file:
            if os.path.exists(self.object.gp5_file.path):
                os.remove(self.object.gp5_file.path)
        
        self.object.delete()
        
        if request.headers.get('HX-Request'):
            return HttpResponse(status=204)
        
        return JsonResponse({'status': 'success'})


# ============= EXPORT VIEWS =============

class BaseExportView(TranscriptionOwnerMixin, HTMXResponseMixin, View):
    """Base class for export views."""
    
    def get_transcription(self):
        return get_object_or_404(Transcription, pk=self.kwargs['pk'])
    
    def create_file_response(self, content, content_type, filename):
        """Create a file download response."""
        response = HttpResponse(content, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class ExportMusicXMLView(BaseExportView):
    """Export transcription as MusicXML."""
    
    def get(self, request, *args, **kwargs):
        transcription = self.get_transcription()
        
        # Get or generate MusicXML content
        if transcription.musicxml_content:
            musicxml_content = transcription.musicxml_content
        else:
            export_manager = ExportManager(transcription)
            musicxml_content = export_manager.generate_musicxml(transcription.guitar_notes)
            transcription.musicxml_content = musicxml_content
            transcription.save()
        
        # Handle download parameter
        if request.GET.get('download'):
            return self.create_file_response(
                musicxml_content,
                'application/xml',
                f"{transcription.filename}.musicxml"
            )
        
        # HTMX display
        if self.is_htmx_request():
            return self.render_to_response({
                'transcription': transcription,
                'musicxml': musicxml_content
            }, template_name='transcriber/partials/musicxml_display.html')
        
        return HttpResponse(musicxml_content, content_type='application/xml')


class ExportGuitarProView(BaseExportView):
    """Export transcription as Guitar Pro 5 file."""
    
    def get(self, request, *args, **kwargs):
        transcription = self.get_transcription()
        
        if transcription.gp5_file:
            content = transcription.gp5_file.read()
        else:
            export_manager = ExportManager(transcription)
            gp5_path = export_manager.generate_gp5(transcription.guitar_notes)
            
            if gp5_path and os.path.exists(gp5_path):
                with open(gp5_path, 'rb') as f:
                    content = f.read()
            else:
                return HttpResponse('Guitar Pro file not available', status=404)
        
        return self.create_file_response(
            content,
            'application/x-guitar-pro',
            f"{transcription.filename}.gp5"
        )


class ExportASCIITabView(BaseExportView):
    """Export transcription as ASCII tab."""
    
    def get(self, request, *args, **kwargs):
        transcription = self.get_transcription()
        export_manager = ExportManager(transcription)
        ascii_tab = export_manager.generate_ascii_tab(transcription.guitar_notes)
        
        if self.is_htmx_request():
            return self.render_to_response({
                'transcription': transcription,
                'ascii_tab': ascii_tab
            }, template_name='transcriber/partials/ascii_tab_display.html')
        
        return self.create_file_response(
            ascii_tab,
            'text/plain',
            f"{transcription.filename}_tab.txt"
        )


class ExportMIDIView(BaseExportView):
    """Export transcription as MIDI file."""
    
    def get(self, request, *args, **kwargs):
        transcription = self.get_transcription()
        
        if not transcription.midi_data:
            return HttpResponse('MIDI data not available', status=404)
        
        export_manager = ExportManager(transcription)
        midi_content = export_manager.generate_midi_bytes(transcription.midi_data)
        
        return self.create_file_response(
            midi_content,
            'audio/midi',
            f"{transcription.filename}.mid"
        )


class ExportManagerView(TranscriptionOwnerMixin, HTMXResponseMixin, View):
    """Manage export generation with task queuing."""
    
    def get(self, request, pk):
        transcription = get_object_or_404(Transcription, pk=pk)
        return self.render_to_response({
            'transcription': transcription
        }, template_name='transcriber/export.html')
    
    def post(self, request, pk):
        transcription = get_object_or_404(Transcription, pk=pk)
        export_format = request.POST.get('format', 'musicxml')
        
        # Check existing export
        existing_export = TabExport.objects.filter(
            transcription=transcription,
            format=export_format
        ).first()
        
        if existing_export:
            return redirect(existing_export.file.url)
        
        # Queue export task
        task = generate_export.delay(str(transcription.id), export_format)
        
        return JsonResponse({
            'task_id': task.id,
            'format': export_format
        })


# ============= VARIANT VIEWS =============

class VariantListView(TranscriptionOwnerMixin, HTMXResponseMixin, View):
    """List all fingering variants for a transcription."""
    
    def get(self, request, pk):
        transcription = get_object_or_404(Transcription, pk=pk)
        variants = transcription.variants.all().order_by('difficulty_score')
        metrics = getattr(transcription, 'metrics', None)
        
        if self.is_htmx_request():
            return self.render_to_response({
                'transcription': transcription,
                'variants': variants,
                'metrics': metrics
            }, template_name='transcriber/partials/variants_list.html')
        
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


class SelectVariantView(TranscriptionOwnerMixin, HTMXResponseMixin, View):
    """Select a specific fingering variant."""
    
    def post(self, request, pk, variant_id):
        transcription = get_object_or_404(Transcription, pk=pk)
        variant = get_object_or_404(
            FingeringVariant, 
            id=variant_id, 
            transcription=transcription
        )
        
        # Mark variant as selected
        variant.is_selected = True
        variant.save()
        
        # Update transcription with variant data
        transcription.guitar_notes = variant.tab_data
        transcription.save()
        
        # Update playability metrics
        self._update_metrics(transcription, variant)
        
        if self.is_htmx_request():
            return self.render_to_response({
                'variant': variant,
                'transcription': transcription
            }, template_name='transcriber/partials/variant_selected.html')
        
        return JsonResponse({
            'status': 'success',
            'selected_variant': variant.variant_name,
            'playability_score': variant.playability_score
        })
    
    def _update_metrics(self, transcription, variant):
        """Update playability metrics for selected variant."""
        metrics, created = PlayabilityMetrics.objects.get_or_create(
            transcription=transcription
        )
        metrics.playability_score = variant.playability_score
        metrics.recommended_skill_level = variant.variant_name
        
        measure_stats = variant.measure_stats.all()
        if measure_stats:
            metrics.max_fret_span = max(stat.chord_span for stat in measure_stats)
            metrics.position_changes = sum(
                1 for stat in measure_stats if stat.max_jump > 4
            )
        
        metrics.save()


class VariantPreviewView(TranscriptionOwnerMixin, HTMXResponseMixin, View):
    """Preview a variant's tab data without selecting it."""
    
    def get(self, request, pk, variant_id):
        transcription = get_object_or_404(Transcription, pk=pk)
        variant = get_object_or_404(
            FingeringVariant, 
            id=variant_id, 
            transcription=transcription
        )
        
        # Get preview data (first 8 measures)
        preview_data = self._get_preview_data(variant.tab_data)
        
        if self.is_htmx_request():
            from .tab_generator import TabGenerator
            tab_gen = TabGenerator([], 120)
            ascii_tab = tab_gen._format_as_ascii_tab(preview_data)
            
            return self.render_to_response({
                'variant': variant,
                'ascii_tab': ascii_tab,
                'measure_count': 8
            }, template_name='transcriber/partials/variant_preview.html')
        
        return JsonResponse({
            'variant_id': str(variant.id),
            'variant_name': variant.variant_name,
            'preview_data': preview_data
        })
    
    def _get_preview_data(self, tab_data, preview_measures=8):
        """Extract preview measures from tab data."""
        if isinstance(tab_data, dict) and 'measures' in tab_data:
            return {
                **tab_data,
                'measures': tab_data['measures'][:preview_measures]
            }
        return tab_data


class RegenerateVariantsView(TranscriptionOwnerMixin, HTMXResponseMixin, View):
    """Regenerate all variants for a transcription."""
    
    def post(self, request, pk):
        transcription = get_object_or_404(Transcription, pk=pk)
        preset = request.POST.get('preset')
        
        # Queue regeneration task
        task = generate_variants.delay(str(transcription.id), preset)
        
        if self.is_htmx_request():
            return self.render_to_response({
                'transcription': transcription,
                'task_id': task.id,
                'preset': preset
            }, template_name='transcriber/partials/variants_regenerating.html')
        
        return JsonResponse({
            'status': 'started',
            'task_id': task.id,
            'preset': preset
        })


# ============= USER VIEWS =============

class DashboardView(LoginRequiredMixin, UserProfileMixin, TemplateView):
    """User dashboard showing transcriptions and stats."""
    template_name = 'transcriber/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Get transcriptions
        context['transcriptions'] = Transcription.objects.filter(
            user=user
        ).order_by('-created_at')[:10]
        
        # Calculate stats
        context['total_transcriptions'] = Transcription.objects.filter(
            user=user
        ).count()
        context['completed_transcriptions'] = Transcription.objects.filter(
            user=user, status='completed'
        ).count()
        context['processing_transcriptions'] = Transcription.objects.filter(
            user=user, status__in=['pending', 'processing']
        ).count()
        
        # Get favorites
        user_profile = user.profile
        context['favorites'] = user_profile.favorite_transcriptions.all()[:5]
        context['usage_percentage'] = (
            user_profile.uploads_this_month / user_profile.monthly_upload_limit * 100
            if user_profile.monthly_upload_limit > 0 else 0
        )
        
        return context


class ProfileView(LoginRequiredMixin, UserProfileMixin, TemplateView):
    """User profile view and edit."""
    template_name = 'transcriber/profile.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['genre_choices'] = [
            'Rock', 'Blues', 'Jazz', 'Metal', 'Classical',
            'Pop', 'Country', 'Folk', 'Indie', 'Alternative'
        ]
        return context
    
    def post(self, request, *args, **kwargs):
        user_profile = request.user.profile
        
        # Update profile
        user_profile.bio = request.POST.get('bio', '')
        user_profile.skill_level = request.POST.get('skill_level', 'intermediate')
        user_profile.preferred_difficulty = request.POST.get('preferred_difficulty', 'balanced')
        user_profile.default_tempo_adjustment = float(
            request.POST.get('tempo_adjustment', 1.0)
        )
        user_profile.preferred_genres = request.POST.getlist('genres')
        user_profile.save()
        
        # Update user info
        request.user.first_name = request.POST.get('first_name', '')
        request.user.last_name = request.POST.get('last_name', '')
        request.user.save()
        
        if request.headers.get('HX-Request'):
            return self.render_to_response({
                'user_profile': user_profile
            }, template_name='transcriber/partials/profile_updated.html')
        
        return redirect('transcriber:profile')


class ToggleFavoriteView(LoginRequiredMixin, HTMXResponseMixin, View):
    """Toggle a transcription as favorite."""
    
    def post(self, request, pk):
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
        
        if self.is_htmx_request():
            return self.render_to_response({
                'transcription': transcription,
                'is_favorited': is_favorited
            }, template_name='transcriber/partials/favorite_button.html')
        
        return JsonResponse({
            'status': 'success',
            'is_favorited': is_favorited
        })


# ============= TASK STATUS VIEW =============

class TaskStatusView(HTMXResponseMixin, View):
    """Get Celery task status."""
    
    def get(self, request, task_id):
        result = AsyncResult(task_id)
        
        if self.is_htmx_request():
            return self._render_htmx_status(result, task_id)
        
        return self._json_status(result, task_id)
    
    def _render_htmx_status(self, result, task_id):
        """Render HTMX template based on task state."""
        template_map = {
            'PENDING': 'transcriber/partials/export_pending.html',
            'PROGRESS': 'transcriber/partials/export_pending.html',
            'SUCCESS': 'transcriber/partials/export_link.html',
            'FAILURE': 'transcriber/partials/export_error.html'
        }
        
        template = template_map.get(result.state, 'transcriber/partials/export_pending.html')
        context = {'task_id': task_id, 'format': 'Export'}
        
        if result.state == 'PROGRESS':
            context.update({
                'progress': result.info.get('current', 0),
                'total': result.info.get('total', 1),
                'step': result.info.get('step', '')
            })
        elif result.state == 'SUCCESS':
            task_result = result.result
            if task_result and 'export_id' in task_result:
                try:
                    from .models import TabExport
                    export = TabExport.objects.get(id=task_result['export_id'])
                    context = {'export': export}
                except TabExport.DoesNotExist:
                    context = {'error': 'Export completed but file not found'}
                    template = 'transcriber/partials/export_error.html'
        elif result.state == 'FAILURE':
            context = {'error': str(result.info)}
        
        return self.render_to_response(context, template_name=template)
    
    def _json_status(self, result, task_id):
        """Return JSON status response."""
        response_data = {
            'task_id': task_id,
            'state': result.state,
            'info': str(result.info)
        }
        
        if result.state == 'PENDING':
            response_data['info'] = 'Task pending...'
        elif result.state == 'PROGRESS':
            response_data.update({
                'current': result.info.get('current', 0),
                'total': result.info.get('total', 1),
                'step': result.info.get('step', '')
            })
        elif result.state == 'SUCCESS':
            response_data['result'] = result.result
        elif result.state == 'FAILURE':
            response_data['error'] = str(result.info)
        
        return JsonResponse(response_data)