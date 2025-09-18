from django.urls import path, include
from . import views
from .views import auth_modal

app_name = 'transcriber'

urlpatterns = [
    path('', views.index, name='index'),
    path('upload/', views.upload, name='upload'),
    path('transcription/<uuid:pk>/', views.detail, name='detail'),
    path('transcription/<uuid:pk>/status/', views.status, name='status'),
    path('transcription/<uuid:pk>/export/', views.export, name='export'),
    path('transcription/<uuid:pk>/reprocess/', views.reprocess, name='reprocess'),
    path('transcription/<uuid:pk>/delete/', views.delete_transcription, name='delete'),
    path('transcription/<uuid:pk>/favorite/', views.toggle_favorite, name='toggle_favorite'),
    path('transcription/<uuid:pk>/preview/', views.preview_tab, name='preview'),
    path('transcription/<uuid:pk>/preview/tab/', views.preview_tab, name='preview_tab'),  # Alias for templates
    path('transcription/<uuid:pk>/preview/tab-api/', views.tab_preview_api, name='tab_preview_api'),
    path('transcription/<uuid:pk>/preview/midi-api/', views.midi_preview_api, name='midi_preview_api'),
    path('transcription/<uuid:pk>/preview/sheet/', views.sheet_music_preview, name='sheet_music_preview'),
    path('transcription/<uuid:pk>/preview/ascii/', views.ascii_tab_preview, name='ascii_tab_preview'),
    path('transcription/<uuid:pk>/comparison/', views.comparison_view, name='comparison'),
    
    # Variant-related URLs
    path('transcription/<uuid:pk>/variants/', views.variants_list, name='variants_list'),
    path('transcription/<uuid:pk>/variants/select/<str:variant_id>/', views.select_variant, name='select_variant'),
    path('transcription/<uuid:pk>/variants/preview/<str:variant_id>/', views.variant_preview, name='variant_preview'),
    # Backward-compatible alias for tests/templates expecting 'preview_variant'
    path('transcription/<uuid:pk>/variants/preview/<str:variant_id>/', views.variant_preview, name='preview_variant'),
    path('transcription/<uuid:pk>/variants/regenerate/', views.regenerate_variants, name='regenerate_variants'),
    path('transcription/<uuid:pk>/variants/<str:variant_id>/stats/', views.variant_stats, name='variant_stats'),
    path('transcription/<uuid:pk>/variants/<str:variant_id>/export/', views.export_variant, name='export_variant'),
    path('transcription/<uuid:pk>/variants/status/<str:task_id>/', views.check_generation_status, name='check_generation_status'),
    
    # Export URLs
    path('transcription/<uuid:pk>/download/<int:export_id>/', views.download, name='download'),
    path('transcription/<uuid:pk>/export/musicxml/', views.export_musicxml, name='export_musicxml'),
    path('transcription/<uuid:pk>/export/gp5/', views.download_gp5, name='download_gp5'),
    path('transcription/<uuid:pk>/debug/tab-data/', views.debug_tab_data, name='debug_tab_data'),
    path('transcription/<uuid:pk>/export/ascii/', views.download_ascii_tab, name='download_ascii_tab'),
    path('transcription/<uuid:pk>/export/midi/', views.download_midi, name='download_midi'),
    path('transcription/<uuid:pk>/export/clear/', views.clear_exports, name='clear_exports'),
    
    # User dashboard and profile
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.profile, name='profile'),
    path('preview-settings/', views.preview_settings, name='preview_settings'),
    
    path('task/<str:task_id>/status/', views.get_task_status, name='task_status'),
    path('library/', views.library, name='library'),
    
    # Enhanced Library Management URLs
    path('library/search/', views.library_search, name='library_search'),
    path('library/stats/', views.library_stats, name='library_stats'),
    path('library/bulk/', views.bulk_operations, name='library_bulk'),
    path('library/suggestions/', views.library_suggestions, name='library_suggestions'),
    path('library/analytics/', views.library_analytics, name='library_analytics'),
    
    # Authentication modal endpoints
    path('accounts/modal/signin/', auth_modal.auth_modal_signin, name='auth_modal_signin'),
    path('accounts/modal/signup/', auth_modal.auth_modal_signup, name='auth_modal_signup'),
    path('accounts/modal/forgot/', auth_modal.auth_modal_forgot, name='auth_modal_forgot'),
    
    # Comment endpoints
    path('transcription/<uuid:pk>/comments/', views.comments_list, name='comments_list'),
    path('transcription/<uuid:pk>/comments/add/', views.add_comment, name='add_comment'),
    path('transcription/<uuid:pk>/comments/<int:comment_id>/flag/', views.flag_comment, name='flag_comment'),
    path('transcription/<uuid:pk>/comment-form/', views.get_comment_form, name='get_comment_form'),
    
    # Voting endpoints
    path('transcription/<uuid:pk>/comments/<int:comment_id>/vote/', views.vote_comment, name='vote_comment'),
    path('transcription/<uuid:pk>/comments/<int:comment_id>/vote/<str:vote_type>/', views.toggle_vote, name='toggle_vote'),
    path('transcription/<uuid:pk>/comments/<int:comment_id>/votes/', views.get_comment_with_votes, name='get_comment_with_votes'),
    path('transcription/<uuid:pk>/comments/<int:comment_id>/stats/', views.voting_stats, name='voting_stats'),
    
    # Karma endpoints
    path('karma/<str:username>/', views.user_karma_display, name='user_karma_display'),
    path('karma/', views.user_karma_display, name='my_karma_display'),
    
    # Enhanced progress tracking and monitoring
    path('transcription/<uuid:transcription_id>/progress/', views.transcription_progress, name='transcription_progress'),
    path('transcription/<uuid:transcription_id>/retry/', views.retry_failed_transcription, name='retry_failed_transcription'),
    path('admin/metrics/system/', views.system_metrics, name='system_metrics'),
    path('admin/metrics/instruments/', views.instrument_stats, name='instrument_stats'),
    path('admin/metrics/queues/', views.queue_status, name='queue_status'),
    path('admin/metrics/costs/', views.cost_estimation, name='cost_estimation'),
    
    # Business intelligence and analytics
    path('transcription/<uuid:pk>/analytics/', views.transcription_analytics, name='transcription_analytics'),
    path('admin/analytics/conversion/', views.conversion_funnel_analysis, name='conversion_funnel'),
    path('admin/analytics/accuracy/', views.accuracy_dashboard, name='accuracy_dashboard'),
    path('admin/analytics/revenue/', views.revenue_analytics, name='revenue_analytics'),
    path('my/transcriptions/history/', views.my_transcription_history, name='user_history'),
    
    # Secure media access
    path('media/', include('transcriber.urls_media')),
]