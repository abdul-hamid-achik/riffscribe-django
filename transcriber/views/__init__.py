"""
RiffScribe Views Package
Organized view modules for better maintainability
"""

from celery.result import AsyncResult  # re-exported for tests patching transcriber.views.AsyncResult

# Lazy import of process_transcription to avoid importing ML dependencies in web container
def __getattr__(name):
    if name == 'process_transcription':
        from ..tasks import process_transcription_advanced
        return process_transcription_advanced
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

# Import all views for backwards compatibility with URLs
from .core import (
    index,
    upload,
    library as library_view,
    dashboard,
    profile,
)

# Enhanced library management views
from .library import (
    library_search,
    library_stats,
    bulk_operations,
    library_suggestions,
    library_analytics,
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
    debug_tab_data,
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

from .progress import (
    transcription_progress,
    system_metrics,
    instrument_stats,
    queue_status,
    retry_failed_transcription,
    cost_estimation,
)

from .business_intelligence import (
    transcription_analytics,
    conversion_funnel_analysis,
    accuracy_dashboard,
    user_transcription_insights,
    revenue_analytics,
    my_transcription_history,
)

# Make all views available at package level
__all__ = [
    # Core views
    'index',
    'upload', 
    'library_view',
    'dashboard',
    'profile',
    
    # Library management views
    'library_search',
    'library_stats',
    'bulk_operations',
    'library_suggestions',
    'library_analytics',
    
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
    'debug_tab_data',
    
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
    
    # Progress and monitoring views
    'transcription_progress',
    'system_metrics',
    'instrument_stats',
    'queue_status',
    'retry_failed_transcription',
    'cost_estimation',
    
    # Business intelligence views
    'transcription_analytics',
    'conversion_funnel_analysis',
    'accuracy_dashboard',
    'user_transcription_insights',
    'revenue_analytics',
    'my_transcription_history',
    
    # Re-exported utilities
    'AsyncResult',
    'process_transcription',
]

# Backward compatibility alias for URLs
library = library_view