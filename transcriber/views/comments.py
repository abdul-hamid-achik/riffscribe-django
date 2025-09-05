"""
Comment-related views for transcriptions
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Case, When, IntegerField

from ..models import Transcription, Comment
from ..forms import CommentForm, AnonymousCommentForm
from ..decorators import htmx_login_required


def comments_list(request, pk):
    """
    HTMX endpoint to load comments for a transcription with priority sorting.
    Authenticated user comments are shown first, then sorted by creation time.
    """
    # Only need basic info for comments, defer large data fields
    transcription = get_object_or_404(
        Transcription.objects.defer('midi_data', 'guitar_notes', 'whisper_analysis', 'musicxml_content'), 
        pk=pk
    )
    
    # Custom ordering: authenticated users first, then by creation time
    comments = Comment.objects.filter(
        transcription=transcription,
        is_approved=True
    ).select_related('user').annotate(
        # Add priority field: 1 for authenticated users, 0 for anonymous
        priority=Case(
            When(user__isnull=False, then=1),
            default=0,
            output_field=IntegerField()
        )
    ).order_by('-priority', '-created_at')
    
    # Pagination
    paginator = Paginator(comments, 10)  # 10 comments per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'transcription': transcription,
        'comments': page_obj,
        'total_comments': paginator.count
    }
    
    if request.htmx:
        return render(request, 'transcriber/partials/comments_list.html', context)
    else:
        return render(request, 'transcriber/comments.html', context)


@require_POST
def add_comment(request, pk):
    """
    HTMX endpoint to add a comment to a transcription.
    Handles both authenticated and anonymous comments.
    """
    # Only need basic info for comments, defer large data fields
    transcription = get_object_or_404(
        Transcription.objects.defer('midi_data', 'guitar_notes', 'whisper_analysis', 'musicxml_content'), 
        pk=pk
    )
    
    if request.user.is_authenticated:
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.transcription = transcription
            comment.user = request.user
            comment.save()
            
            messages.success(request, 'Your comment has been added successfully!')
            
            if request.htmx:
                # Return the new comment partial and clear form
                return render(request, 'transcriber/partials/comment_added.html', {
                    'comment': comment,
                    'form': CommentForm(),  # Fresh form
                    'transcription': transcription
                })
            return render(request, 'transcriber/comments.html', {
                'transcription': transcription,
                'comments': [comment],
                'total_comments': 1
            })
        else:
            if request.htmx:
                return render(request, 'transcriber/partials/comment_form.html', {
                    'form': form,
                    'transcription': transcription
                })
            return render(request, 'transcriber/comments.html', {
                'transcription': transcription,
                'form': form
            })
    else:
        form = AnonymousCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.transcription = transcription
            # Anonymous user details are already in the form
            comment.save()
            
            messages.success(request, 'Your comment has been added successfully!')
            
            if request.htmx:
                return render(request, 'transcriber/partials/comment_added.html', {
                    'comment': comment,
                    'form': AnonymousCommentForm(),  # Fresh form
                    'transcription': transcription
                })
            return render(request, 'transcriber/comments.html', {
                'transcription': transcription,
                'comments': [comment],
                'total_comments': 1
            })
        else:
            if request.htmx:
                return render(request, 'transcriber/partials/anonymous_comment_form.html', {
                    'form': form,
                    'transcription': transcription
                })
            return render(request, 'transcriber/comments.html', {
                'transcription': transcription,
                'form': form
            })
    
    # Non-HTMX fallback
    return render(request, 'transcriber/comments.html', {
        'transcription': transcription
    })


@htmx_login_required
@require_POST  
def flag_comment(request, pk, comment_id):
    """Flag a comment as inappropriate"""
    transcription = get_object_or_404(Transcription, pk=pk)
    comment = get_object_or_404(Comment, id=comment_id, transcription=transcription)
    
    # Simple flagging - could be enhanced with user tracking
    comment.is_flagged = True
    comment.save()
    
    messages.info(request, 'Comment has been flagged for review.')
    
    if request.htmx:
        return render(request, 'transcriber/partials/comment_flagged.html', {
            'comment': comment
        })
    
    return redirect('transcriber:detail', pk=transcription.pk)


def get_comment_form(request, pk):
    """
    HTMX endpoint to get the appropriate comment form based on user authentication
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    
    if request.user.is_authenticated:
        form = CommentForm()
        template = 'transcriber/partials/comment_form.html'
    else:
        form = AnonymousCommentForm()
        template = 'transcriber/partials/anonymous_comment_form.html'
    
    return render(request, template, {
        'form': form,
        'transcription': transcription
    })