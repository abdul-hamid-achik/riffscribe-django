"""
RiffScribe Views Package
Organized view modules for better maintainability
"""

from celery.result import AsyncResult  # re-exported for tests patching transcriber.views.AsyncResult
from ..tasks import process_transcription  # re-export for tests patching transcriber.views.process_transcription
# Import all views for backwards compatibility with URLs
from .core import (
    index,
    upload,
    library,
    dashboard,
    profile,
)

from .transcription import (
    detail,
    status,
    delete_transcription,
    toggle_favorite,
    get_task_status,
    reprocess,
)

from .export import (
    export,
    download,
    export_musicxml,
    download_gp5,
    download_ascii_tab,
    download_midi,
    clear_exports,
)

from .comments import (
    comments_list,
    add_comment,
    flag_comment,
    get_comment_form,
)

from .voting import (
    vote_comment,
    toggle_vote,
    get_comment_with_votes,
    user_karma_display,
    voting_stats,
)

from .variants import (
    variants_list,
    select_variant,
    variant_preview,
    regenerate_variants,
    variant_stats,
    export_variant,
    check_generation_status,
)

from .preview import (
    preview_tab,
    tab_preview_api,
    midi_preview_api,
    sheet_music_preview,
    ascii_tab_preview,
    preview_settings,
    comparison_view,
)

# Make all views available at package level
__all__ = [
    # Core views
    'index',
    'upload', 
    'library',
    'dashboard',
    'profile',
    
    # Transcription views
    'detail',
    'status',
    'delete_transcription',
    'toggle_favorite',
    'get_task_status',
    'reprocess',
    
    # Export views
    'export',
    'download',
    'export_musicxml',
    'download_gp5',
    'download_ascii_tab',
    'download_midi',
    'clear_exports',
    
    # Comment views
    'comments_list',
    'add_comment',
    'flag_comment',
    'get_comment_form',
    
    # Voting views
    'vote_comment',
    'toggle_vote',
    'get_comment_with_votes',
    'user_karma_display',
    'voting_stats',
    
    # Preview views
    'preview_tab',
    'tab_preview_api',
    'midi_preview_api', 
    'sheet_music_preview',
    'ascii_tab_preview',
    'preview_settings',
    'comparison_view',
    
    # Variant views
    'variants_list',
    'select_variant',
    'variant_preview',
    'regenerate_variants',
    'variant_stats',
    'export_variant',
    'check_generation_status',
    # Re-exported utilities
    'AsyncResult',
    'process_transcription',
]