"""
Custom decorators for HTMX authentication handling
"""
from functools import wraps
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse


def htmx_login_required(view_func):
    """
    Decorator that requires login and handles HTMX requests properly.
    For HTMX requests, returns an authentication modal instead of redirecting.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            # Check if this is an HTMX request
            if request.headers.get('HX-Request'):
                # Return authentication modal container for HTMX requests
                response = render(request, 'transcriber/partials/auth_modal_container.html')
                # Tell HTMX to show this as a modal by appending to body
                response['HX-Retarget'] = 'body'
                response['HX-Reswap'] = 'beforeend'
                return response
            else:
                # For non-HTMX requests, use the standard login_required behavior
                return login_required(view_func)(request, *args, **kwargs)
        
        # User is authenticated, proceed with the view
        return view_func(request, *args, **kwargs)
    
    return wrapper


def require_auth_or_modal(view_func):
    """
    Alternative decorator that returns a 401 response for HTMX requests
    which can be handled by JavaScript to show the auth modal.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            if request.headers.get('HX-Request'):
                # Return 401 with special header to trigger auth modal
                response = HttpResponse('Authentication required', status=401)
                response['HX-Trigger'] = 'show-auth-modal'
                return response
            else:
                # For non-HTMX requests, use standard login_required
                return login_required(view_func)(request, *args, **kwargs)
        
        return view_func(request, *args, **kwargs)
    
    return wrapper