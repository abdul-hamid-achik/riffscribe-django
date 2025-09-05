"""
Shared mixins and utilities for RiffScribe views
"""
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.mixins import UserPassesTestMixin


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


def check_transcription_access(transcription, user):
    """
    Utility function to check if user has access to transcription.
    Can be used in function-based views.
    """
    return (
        transcription.user == user or 
        user.is_superuser or
        transcription.user is None  # Public transcription
    )