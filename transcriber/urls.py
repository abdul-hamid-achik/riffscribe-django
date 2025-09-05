from django.urls import path
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
    
    # Variant-related URLs
    path('transcription/<uuid:pk>/variants/', views.variants_list, name='variants_list'),
    path('transcription/<uuid:pk>/variants/select/<uuid:variant_id>/', views.select_variant, name='select_variant'),
    path('transcription/<uuid:pk>/variants/preview/<uuid:variant_id>/', views.variant_preview, name='variant_preview'),
    path('transcription/<uuid:pk>/variants/regenerate/', views.regenerate_variants, name='regenerate_variants'),
    path('transcription/<uuid:pk>/variants/<uuid:variant_id>/stats/', views.variant_stats, name='variant_stats'),
    path('transcription/<uuid:pk>/variants/<uuid:variant_id>/export/', views.export_variant, name='export_variant'),
    
    # Export URLs
    path('transcription/<uuid:pk>/download/<int:export_id>/', views.download, name='download'),
    path('transcription/<uuid:pk>/export/musicxml/', views.export_musicxml, name='export_musicxml'),
    path('transcription/<uuid:pk>/export/gp5/', views.download_gp5, name='download_gp5'),
    path('transcription/<uuid:pk>/export/ascii/', views.download_ascii_tab, name='download_ascii_tab'),
    path('transcription/<uuid:pk>/export/midi/', views.download_midi, name='download_midi'),
    path('transcription/<uuid:pk>/export/clear/', views.clear_exports, name='clear_exports'),
    
    # User dashboard and profile
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.profile, name='profile'),
    
    path('task/<str:task_id>/status/', views.get_task_status, name='task_status'),
    path('library/', views.library, name='library'),
    
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
]