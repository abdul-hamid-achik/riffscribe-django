"""
Enhanced decorators for premium features and access control
"""
import functools
import logging
from django.shortcuts import redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

from .services.rate_limiter import check_openai_rate_limit
from .services.metrics_service import metrics_service

logger = logging.getLogger(__name__)


def premium_required(view_func=None, *, feature_name: str = None):
    """
    Decorator to require premium subscription for specific features
    
    Args:
        feature_name: Name of the premium feature for analytics
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Must be authenticated first
            if not request.user.is_authenticated:
                if request.headers.get('HX-Request'):
                    return JsonResponse({
                        'error': 'Authentication required',
                        'action': 'redirect',
                        'url': '/accounts/signup/?next=' + request.path,
                        'message': 'Sign up to export your transcription!'
                    }, status=401)
                else:
                    return redirect(f'/accounts/signup/?next={request.path}')
            
            # Check premium status
            user_profile = getattr(request.user, 'profile', None)
            if not user_profile:
                logger.error(f"User {request.user.id} has no profile")
                return JsonResponse({'error': 'User profile not found'}, status=500)
            
            # Check if user has premium access
            has_premium = (
                user_profile.subscription_tier in ['premium', 'professional'] or
                user_profile.is_premium or
                request.user.is_superuser
            )
            
            if not has_premium:
                # Track conversion event
                from .models import ConversionEvent
                try:
                    ConversionEvent.objects.create(
                        user=request.user,
                        event_type='attempted_export',
                        transcription_id=kwargs.get('pk'),
                        feature_name=feature_name or 'unknown'
                    )
                except Exception as e:
                    logger.warning(f"Failed to track conversion event: {e}")
                
                # Return upgrade prompt
                if request.headers.get('HX-Request'):
                    return JsonResponse({
                        'error': 'Premium subscription required',
                        'action': 'upgrade_prompt',
                        'upgrade_url': '/upgrade/',
                        'feature': feature_name or 'export',
                        'message': f'Upgrade to download {feature_name or "exports"}! '
                                   'Preview is always free.'
                    }, status=402)  # Payment Required
                else:
                    return redirect('/upgrade/?feature=' + (feature_name or 'export'))
            
            # Check if subscription is still valid
            if (user_profile.subscription_expires and 
                user_profile.subscription_expires < timezone.now()):
                
                return JsonResponse({
                    'error': 'Subscription expired',
                    'action': 'renew_subscription',
                    'renew_url': '/upgrade/renew/',
                    'message': 'Your subscription has expired. Renew to continue exporting.'
                }, status=402)
            
            # Premium user - proceed with request
            return view_func(request, *args, **kwargs)
            
        return wrapper
    
    if view_func is None:
        return decorator
    else:
        return decorator(view_func)


def rate_limited(requests_per_minute: int = 60, cost_estimate: float = 0.0):
    """
    Decorator to apply rate limiting with OpenAI cost consideration
    
    Args:
        requests_per_minute: Rate limit
        cost_estimate: Estimated cost for this operation
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Check OpenAI rate limits if cost is involved
            if cost_estimate > 0:
                can_proceed, retry_after = check_openai_rate_limit(cost_estimate)
                if not can_proceed:
                    return JsonResponse({
                        'error': 'Rate limit exceeded',
                        'retry_after': retry_after,
                        'message': f'Please wait {retry_after} seconds before trying again.'
                    }, status=429)
            
            # TODO: Implement general rate limiting per user/IP
            # For now, just proceed
            
            return view_func(request, *args, **kwargs)
            
        return wrapper
    return decorator


def track_conversion_event(event_type: str):
    """
    Decorator to track user conversion events for analytics
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Execute the view first
            response = view_func(request, *args, **kwargs)
            
            # Track event if user is authenticated and response is successful
            if (request.user.is_authenticated and 
                hasattr(response, 'status_code') and 
                200 <= response.status_code < 300):
                
                try:
                    from .models import ConversionEvent
                    ConversionEvent.objects.create(
                        user=request.user,
                        event_type=event_type,
                        transcription_id=kwargs.get('pk'),
                        metadata={
                            'path': request.path,
                            'method': request.method,
                            'user_agent': request.META.get('HTTP_USER_AGENT', '')[:200]
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to track conversion event '{event_type}': {e}")
            
            return response
            
        return wrapper
    return decorator


def admin_required(view_func):
    """Decorator to require admin access"""
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            return JsonResponse({'error': 'Admin access required'}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


def htmx_login_required(view_func):
    """
    Enhanced login required decorator that handles HTMX requests gracefully
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            if request.headers.get('HX-Request'):
                # Return HTMX-friendly response
                return JsonResponse({
                    'error': 'Authentication required',
                    'action': 'show_auth_modal',
                    'message': 'Please sign in to continue'
                }, status=401)
            else:
                # Regular redirect
                return redirect(f'/accounts/signin/?next={request.path}')
        
        return view_func(request, *args, **kwargs)
        
    return wrapper


def usage_tracking(feature: str):
    """
    Decorator to track feature usage for analytics
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            start_time = time.time()
            
            try:
                response = view_func(request, *args, **kwargs)
                
                # Track successful usage
                if request.user.is_authenticated:
                    duration = time.time() - start_time
                    metrics_service.track_feature_usage(
                        user_id=request.user.id,
                        feature=feature,
                        duration=duration,
                        success=True
                    )
                
                return response
                
            except Exception as e:
                # Track failed usage
                if request.user.is_authenticated:
                    duration = time.time() - start_time
                    metrics_service.track_feature_usage(
                        user_id=request.user.id,
                        feature=feature,
                        duration=duration,
                        success=False,
                        error=str(e)
                    )
                raise
                
        return wrapper
    return decorator


def check_monthly_limits(view_func):
    """
    Decorator to check user's monthly usage limits
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return view_func(request, *args, **kwargs)
        
        user_profile = getattr(request.user, 'profile', None)
        if not user_profile:
            return view_func(request, *args, **kwargs)
        
        # Check if user can upload more files this month
        if not user_profile.can_upload():
            limit = user_profile.monthly_upload_limit
            used = user_profile.uploads_this_month
            
            return JsonResponse({
                'error': 'Monthly limit exceeded',
                'limit': limit,
                'used': used,
                'upgrade_url': '/upgrade/',
                'message': f'You have used {used}/{limit} transcriptions this month. '
                          'Upgrade for unlimited access!'
            }, status=429)
        
        return view_func(request, *args, **kwargs)
        
    return wrapper