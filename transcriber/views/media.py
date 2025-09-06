"""
Views for secure media access and signed URL generation
"""
import logging
from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import cache_control
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django.conf import settings
from transcriber.models import Transcription
from transcriber.storage import SecureMediaStorage
import requests

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def signed_audio_url(request, transcription_id):
    """
    Generate a signed URL for audio file access
    
    Returns a time-limited signed URL that allows secure access to the audio file
    """
    try:
        # Get transcription object
        transcription = get_object_or_404(Transcription, id=transcription_id)
        
        # Check if user has permission to access this file
        if not _has_file_permission(request, transcription):
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        # Check if file exists
        if not transcription.original_audio:
            return JsonResponse({'error': 'Audio file not found'}, status=404)
        
        # Generate cache key
        cache_key = f"signed_url_{transcription_id}_{request.user.id if request.user.is_authenticated else 'anon'}"
        
        # Check cache first
        signed_url = cache.get(cache_key)
        if signed_url:
            return JsonResponse({'url': signed_url, 'cached': True})
        
        # Generate new signed URL
        storage = SecureMediaStorage()
        file_name = transcription.original_audio.name
        
        # Generate signed URL with 2 hour expiration
        signed_url = storage.generate_signed_url(file_name, expiration=7200)
        
        if not signed_url:
            logger.error(f"Failed to generate signed URL for {file_name}")
            return JsonResponse({'error': 'Failed to generate secure URL'}, status=500)
        
        # Cache the URL for 1 hour (less than expiration time)
        cache.set(cache_key, signed_url, 3600)
        
        return JsonResponse({
            'url': signed_url,
            'expires_in': 7200,
            'transcription_id': str(transcription_id)
        })
        
    except Exception as e:
        logger.error(f"Error generating signed URL for transcription {transcription_id}: {e}")
        return JsonResponse({'error': 'Internal server error'}, status=500)


@require_http_methods(["GET"])
@cache_control(max_age=3600)  # Cache for 1 hour
def audio_proxy(request, transcription_id):
    """
    Proxy audio file access through Django for additional security
    
    This allows for additional logging, rate limiting, and access control
    """
    try:
        # Get transcription object
        transcription = get_object_or_404(Transcription, id=transcription_id)
        
        # Check permissions
        if not _has_file_permission(request, transcription):
            raise Http404("File not found")
        
        # Check if file exists
        if not transcription.original_audio:
            raise Http404("Audio file not found")
        
        # For local development, serve directly from storage
        if settings.DEBUG and hasattr(settings, 'AWS_S3_ENDPOINT_URL'):
            endpoint = getattr(settings, 'AWS_S3_ENDPOINT_URL', '')
            if 'localhost:' in endpoint or '127.0.0.1:' in endpoint:
                # Just redirect to the public file URL for development
                file_url = transcription.original_audio.url
                
                from django.http import HttpResponseRedirect
                return HttpResponseRedirect(file_url)
        
        # For production, generate signed URL and redirect
        storage = SecureMediaStorage()
        signed_url = storage.generate_signed_url(transcription.original_audio.name, expiration=3600)
        
        if signed_url:
            return HttpResponse(
                f'<script>window.location.href="{signed_url}";</script>',
                content_type='text/html'
            )
        else:
            raise Http404("File temporarily unavailable")
            
    except Exception as e:
        logger.error(f"Error in audio proxy for transcription {transcription_id}: {e}")
        raise Http404("File not found")


def _has_file_permission(request, transcription):
    """
    Check if the user has permission to access this transcription's files
    
    Args:
        request: HTTP request object
        transcription: Transcription instance
        
    Returns:
        bool: True if user has access, False otherwise
    """
    # Public access for anonymous users (you might want to restrict this)
    if not request.user.is_authenticated:
        return True
    
    # Owner has full access
    if transcription.user == request.user:
        return True
    
    # Admin users have full access
    if request.user.is_staff or request.user.is_superuser:
        return True
    
    # For now, allow access to all authenticated users
    # You can add more sophisticated permission logic here
    return True


def get_secure_audio_url(transcription, request=None):
    """
    Utility function to get secure audio URL for templates and views
    
    Args:
        transcription: Transcription instance
        request: HTTP request object (optional)
        
    Returns:
        str: Secure URL for the audio file
    """
    try:
        if not transcription.original_audio:
            return None
            
        # For development with localhost, return direct URL
        if settings.DEBUG and hasattr(settings, 'AWS_S3_ENDPOINT_URL'):
            endpoint = getattr(settings, 'AWS_S3_ENDPOINT_URL', '')
            if 'localhost:' in endpoint or '127.0.0.1:' in endpoint:
                return transcription.original_audio.url
        
        # For production, return proxy URL or signed URL endpoint
        from django.urls import reverse
        return reverse('transcriber:media:audio_proxy', kwargs={'transcription_id': transcription.id})
        
    except Exception as e:
        logger.error(f"Error getting secure audio URL for transcription {transcription.id}: {e}")
        return None
