"""
Authentication modal views for HTMX requests
"""
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.http import HttpResponse, JsonResponse


@never_cache
@require_http_methods(["GET", "POST"])
@csrf_protect
def auth_modal_signin(request):
    """
    Handle sign-in modal content and form submission for HTMX requests.
    """
    if request.method == "POST":
        email = request.POST.get('login', '').strip()
        password = request.POST.get('password', '')
        
        # Try to authenticate with email/username
        user = authenticate(request, username=email, password=password)
        
        if user is not None:
            login(request, user)
            # Return success response that triggers page refresh
            response = HttpResponse()
            response['HX-Redirect'] = request.GET.get('next', '/dashboard/')
            return response
        else:
            # Return form with error
            context = {
                'error': 'Invalid email/username or password',
                'email': email
            }
            return render(request, 'transcriber/partials/auth_modal_signin.html', context)
    
    return render(request, 'transcriber/partials/auth_modal_signin.html')


@never_cache  
@require_http_methods(["GET", "POST"])
@csrf_protect
def auth_modal_signup(request):
    """
    Handle sign-up modal content and form submission for HTMX requests.
    """
    if request.method == "POST":
        email = request.POST.get('email', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        
        # Validation
        errors = []
        if not email:
            errors.append('Email is required')
        if not password1:
            errors.append('Password is required')
        if password1 != password2:
            errors.append('Passwords do not match')
        if len(password1) < 8:
            errors.append('Password must be at least 8 characters')
        
        # Check if user already exists
        if User.objects.filter(email=email).exists():
            errors.append('An account with this email already exists')
        
        if not errors:
            try:
                # Create user
                user = User.objects.create_user(
                    username=email.split('@')[0],  # Use email prefix as username
                    email=email,
                    password=password1
                )
                # Log the user in
                login(request, user)
                # Return success response
                response = HttpResponse()
                response['HX-Redirect'] = '/dashboard/'
                return response
            except Exception as e:
                errors.append(f'Error creating account: {str(e)}')
        
        # Return form with errors
        context = {
            'errors': errors,
            'email': email
        }
        return render(request, 'transcriber/partials/auth_modal_signup.html', context)
    
    return render(request, 'transcriber/partials/auth_modal_signup.html')


@never_cache
@require_http_methods(["GET"])  
def auth_modal_forgot(request):
    """
    Return forgot password modal content for HTMX requests.
    """
    return render(request, 'transcriber/partials/auth_modal_forgot.html')