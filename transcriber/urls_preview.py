"""
URL patterns for preview functionality.
Add these to your main transcriber urls.
"""
from django.urls import path
from . import views_preview as views

# Add these patterns to your existing urlpatterns
preview_patterns = [
    # Main preview page
    path('transcription/<uuid:pk>/preview/', 
         views.TranscriptionPreviewView.as_view(), 
         name='preview'),
    
    # Preview API endpoints
    path('transcription/<uuid:pk>/preview/tab-data/', 
         views.TabPreviewAPIView.as_view(), 
         name='preview_tab_data'),
    
    path('transcription/<uuid:pk>/preview/midi-data/', 
         views.MIDIPreviewAPIView.as_view(), 
         name='preview_midi_data'),
    
    path('transcription/<uuid:pk>/preview/sheet-music/', 
         views.SheetMusicPreviewView.as_view(), 
         name='preview_sheet_music'),
    
    path('transcription/<uuid:pk>/preview/ascii-tab/', 
         views.ASCIITabPreviewView.as_view(), 
         name='preview_ascii_tab'),
    
    # Comparison view
    path('transcription/<uuid:pk>/compare/', 
         views.ComparisonView.as_view(), 
         name='comparison'),
    
    # User preview settings
    path('preview/settings/', 
         views.PreviewSettingsView.as_view(), 
         name='preview_settings'),
]