"""
URL patterns for class-based views.
To use this, replace the include in your main urls.py with:
    path('transcriber/', include('transcriber.urls_cbv')),
"""
from django.urls import path
from . import views_cbv as views

app_name = 'transcriber'

urlpatterns = [
    # Base views
    path('', views.IndexView.as_view(), name='index'),
    path('library/', views.LibraryView.as_view(), name='library'),
    
    # Upload
    path('upload/', views.UploadView.as_view(), name='upload'),
    
    # Transcription views
    path('transcription/<uuid:pk>/', views.TranscriptionDetailView.as_view(), name='detail'),
    path('transcription/<uuid:pk>/status/', views.TranscriptionStatusView.as_view(), name='status'),
    path('transcription/<uuid:pk>/delete/', views.TranscriptionDeleteView.as_view(), name='delete'),
    
    # Export views
    path('transcription/<uuid:pk>/export/', views.ExportManagerView.as_view(), name='export'),
    path('transcription/<uuid:pk>/export/musicxml/', views.ExportMusicXMLView.as_view(), name='export_musicxml'),
    path('transcription/<uuid:pk>/export/gp5/', views.ExportGuitarProView.as_view(), name='download_gp5'),
    path('transcription/<uuid:pk>/export/ascii/', views.ExportASCIITabView.as_view(), name='download_ascii_tab'),
    path('transcription/<uuid:pk>/export/midi/', views.ExportMIDIView.as_view(), name='download_midi'),
    
    # Variant views
    path('transcription/<uuid:pk>/variants/', views.VariantListView.as_view(), name='variants_list'),
    path('transcription/<uuid:pk>/variants/select/<uuid:variant_id>/', views.SelectVariantView.as_view(), name='select_variant'),
    path('transcription/<uuid:pk>/variants/preview/<uuid:variant_id>/', views.VariantPreviewView.as_view(), name='variant_preview'),
    path('transcription/<uuid:pk>/variants/regenerate/', views.RegenerateVariantsView.as_view(), name='regenerate_variants'),
    
    # User views
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('transcription/<uuid:pk>/favorite/', views.ToggleFavoriteView.as_view(), name='toggle_favorite'),
    
    # Task status
    path('task/<str:task_id>/status/', views.TaskStatusView.as_view(), name='task_status'),
]