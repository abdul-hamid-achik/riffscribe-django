"""
Custom template filters for the transcriber app.
"""
from django import template

register = template.Library()


@register.filter
def split(value, delimiter=','):
    """
    Split a string by the given delimiter.
    Usage: {{ "a,b,c"|split:"," }}
    """
    if value is None:
        return []
    return value.split(delimiter)


@register.filter
def length(value):
    """
    Return the length of a value.
    Usage: {{ some_list|length }}
    """
    try:
        return len(value)
    except (TypeError, AttributeError):
        return 0


@register.filter
def get_item(dictionary, key):
    """
    Get an item from a dictionary using a variable key.
    Usage: {{ my_dict|get_item:key_variable }}
    """
    try:
        return dictionary.get(key)
    except (AttributeError, TypeError):
        return None


@register.filter
def multiply(value, arg):
    """
    Multiply a value by an argument.
    Usage: {{ value|multiply:2 }}
    """
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def divide(value, arg):
    """
    Divide a value by an argument.
    Usage: {{ value|divide:2 }}
    """
    try:
        return float(value) / float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def percentage(value, total):
    """
    Calculate percentage of value out of total.
    Usage: {{ current|percentage:total }}
    """
    try:
        value = float(value)
        total = float(total)
        if total == 0:
            return 0
        return (value / total) * 100
    except (ValueError, TypeError, ZeroDivisionError):
        return 0


@register.filter
def format_duration(seconds):
    """
    Format seconds into a human readable duration.
    Usage: {{ 125|format_duration }}  -> "2:05"
    """
    try:
        seconds = int(float(seconds))
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"
    except (ValueError, TypeError):
        return "0:00"


@register.filter
def file_size(bytes_value):
    """
    Format bytes into human readable file size.
    Usage: {{ file_size_bytes|file_size }}
    """
    try:
        bytes_value = float(bytes_value)
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_value < 1024.0:
                if unit == 'B':
                    return f"{bytes_value:.0f} {unit}"
                else:
                    return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.1f} TB"
    except (ValueError, TypeError):
        return "0 B"


@register.filter
def status_color(status):
    """
    Return CSS color class for status.
    Usage: {{ transcription.status|status_color }}
    """
    status_colors = {
        'pending': 'gray',
        'processing': 'blue',
        'completed': 'green',
        'failed': 'red',
        'cancelled': 'orange'
    }
    return status_colors.get(status, 'gray')


@register.filter
def complexity_level(complexity):
    """
    Convert complexity string to numeric level.
    Usage: {{ transcription.complexity|complexity_level }}
    """
    levels = {
        'simple': 1,
        'moderate': 2,
        'complex': 3,
        'advanced': 4,
        'virtuoso': 5
    }
    return levels.get(complexity, 3)


@register.filter
def get_user_vote(comment, user):
    """
    Get the user's vote for a comment.
    Usage: {{ comment|get_user_vote:request.user }}
    """
    if not user or not user.is_authenticated:
        return None
    return comment.get_user_vote(user)