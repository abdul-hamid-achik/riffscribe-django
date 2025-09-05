"""
Voting system views for comments
"""
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.db import transaction

from ..models import Comment, CommentVote
from ..decorators import htmx_login_required


@htmx_login_required
@require_POST
def vote_comment(request, pk, comment_id):
    """
    HTMX endpoint to upvote or downvote a comment
    """
    comment = get_object_or_404(Comment, id=comment_id, transcription_id=pk)
    vote_type = request.POST.get('vote_type')
    
    if vote_type not in ['up', 'down']:
        return JsonResponse({'error': 'Invalid vote type'}, status=400)
    
    # Prevent users from voting on their own comments
    if comment.user == request.user:
        return JsonResponse({'error': 'Cannot vote on your own comment'}, status=400)
    
    # Prevent voting on anonymous comments
    if not comment.user:
        return JsonResponse({'error': 'Cannot vote on anonymous comments'}, status=400)
    
    with transaction.atomic():
        # Get or create vote
        vote, created = CommentVote.objects.get_or_create(
            comment=comment,
            user=request.user,
            defaults={'vote_type': vote_type}
        )
        
        # If vote exists and is the same type, remove it (toggle off)
        if not created and vote.vote_type == vote_type:
            vote.delete()
            action = 'removed'
        # If vote exists but is different type, update it
        elif not created and vote.vote_type != vote_type:
            vote.vote_type = vote_type
            vote.save()
            action = 'changed'
        # New vote
        else:
            action = 'added'
    
    # Refresh comment to get updated counts
    comment.refresh_from_db()
    
    # Get user's current vote status
    user_vote = comment.get_user_vote(request.user)
    
    context = {
        'comment': comment,
        'user_vote': user_vote,
        'action': action,
        'vote_type': vote_type
    }
    
    if request.htmx:
        return render(request, 'transcriber/partials/voting_buttons.html', context)
    else:
        return JsonResponse({
            'score': comment.score,
            'upvotes': comment.upvotes_count,
            'downvotes': comment.downvotes_count,
            'user_vote': user_vote,
            'action': action
        })


@htmx_login_required
@require_POST
def toggle_vote(request, pk, comment_id, vote_type):
    """
    HTMX endpoint to toggle a specific vote type (up/down)
    """
    comment = get_object_or_404(Comment, id=comment_id, transcription_id=pk)
    
    if vote_type not in ['up', 'down']:
        return JsonResponse({'error': 'Invalid vote type'}, status=400)
    
    # Prevent users from voting on their own comments
    if comment.user == request.user:
        return JsonResponse({'error': 'Cannot vote on your own comment'}, status=400)
    
    # Prevent voting on anonymous comments
    if not comment.user:
        return JsonResponse({'error': 'Cannot vote on anonymous comments'}, status=400)
    
    with transaction.atomic():
        try:
            # Get existing vote
            existing_vote = CommentVote.objects.get(comment=comment, user=request.user)
            
            if existing_vote.vote_type == vote_type:
                # Same vote type - remove it (toggle off)
                existing_vote.delete()
                action = 'removed'
                final_vote = None
            else:
                # Different vote type - change it
                existing_vote.vote_type = vote_type
                existing_vote.save()
                action = 'changed'
                final_vote = vote_type
                
        except CommentVote.DoesNotExist:
            # No existing vote - create new one
            CommentVote.objects.create(
                comment=comment,
                user=request.user,
                vote_type=vote_type
            )
            action = 'added'
            final_vote = vote_type
    
    # Refresh comment to get updated counts
    comment.refresh_from_db()
    
    context = {
        'comment': comment,
        'user_vote': final_vote,
        'action': action,
        'vote_type': vote_type
    }
    
    if request.htmx:
        return render(request, 'transcriber/partials/voting_buttons.html', context)
    else:
        return JsonResponse({
            'score': comment.score,
            'upvotes': comment.upvotes_count,
            'downvotes': comment.downvotes_count,
            'user_vote': final_vote,
            'action': action
        })


def get_comment_with_votes(request, pk, comment_id):
    """
    HTMX endpoint to get comment with current voting state
    """
    comment = get_object_or_404(Comment, id=comment_id, transcription_id=pk)
    
    user_vote = None
    if request.user.is_authenticated:
        user_vote = comment.get_user_vote(request.user)
    
    context = {
        'comment': comment,
        'user_vote': user_vote
    }
    
    if request.htmx:
        return render(request, 'transcriber/partials/voting_buttons.html', context)
    else:
        return JsonResponse({
            'score': comment.score,
            'upvotes': comment.upvotes_count,
            'downvotes': comment.downvotes_count,
            'user_vote': user_vote
        })


@htmx_login_required
def user_karma_display(request, username=None):
    """
    HTMX endpoint to display user karma info
    """
    if username:
        from django.contrib.auth.models import User
        user = get_object_or_404(User, username=username)
    else:
        user = request.user
    
    context = {
        'profile_user': user,
        'karma_score': user.profile.karma_score,
        'karma_level': user.profile.karma_level,
        'karma_level_display': user.profile.karma_level_display,
        'karma_badge_color': user.profile.karma_badge_color,
        'comments_received_upvotes': user.profile.comments_received_upvotes,
        'comments_received_downvotes': user.profile.comments_received_downvotes,
    }
    
    if request.htmx:
        return render(request, 'transcriber/partials/karma_display.html', context)
    else:
        return JsonResponse({
            'karma_score': user.profile.karma_score,
            'karma_level': user.profile.karma_level_display,
            'upvotes_received': user.profile.comments_received_upvotes,
            'downvotes_received': user.profile.comments_received_downvotes,
        })


@htmx_login_required
def voting_stats(request, pk, comment_id):
    """
    HTMX endpoint to show detailed voting stats for a comment
    """
    comment = get_object_or_404(Comment, id=comment_id, transcription_id=pk)
    
    # Get recent voters (last 10)
    recent_upvoters = comment.votes.filter(vote_type='up').select_related('user__profile').order_by('-created_at')[:5]
    recent_downvoters = comment.votes.filter(vote_type='down').select_related('user__profile').order_by('-created_at')[:5]
    
    context = {
        'comment': comment,
        'recent_upvoters': recent_upvoters,
        'recent_downvoters': recent_downvoters,
    }
    
    if request.htmx:
        return render(request, 'transcriber/partials/voting_stats.html', context)
    else:
        return JsonResponse({
            'score': comment.score,
            'upvotes': comment.upvotes_count,
            'downvotes': comment.downvotes_count,
            'recent_upvoters': [v.user.username for v in recent_upvoters],
            'recent_downvoters': [v.user.username for v in recent_downvoters],
        })