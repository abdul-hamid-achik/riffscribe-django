"""
URLs for secure media access with signed URLs
"""
from django.urls import path
from transcriber.views import media as media_views

app_name = 'media'

urlpatterns = [
    path('audio/signed/<uuid:transcription_id>/', media_views.signed_audio_url, name='signed_audio_url'),
    path('audio/proxy/<uuid:transcription_id>/', media_views.audio_proxy, name='audio_proxy'),
]
