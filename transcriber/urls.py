from django.urls import path
from . import views

app_name = 'transcriber'

urlpatterns = [
    path('', views.index, name='index'),
    path('upload/', views.upload, name='upload'),
    path('transcription/<uuid:pk>/', views.detail, name='detail'),
    path('transcription/<uuid:pk>/status/', views.status, name='status'),
    path('transcription/<uuid:pk>/export/', views.export, name='export'),
    path('transcription/<uuid:pk>/export/<int:export_id>/download/', views.download, name='download'),
    path('transcription/<uuid:pk>/delete/', views.delete, name='delete'),
    path('transcription/<uuid:pk>/preview/', views.preview_tab, name='preview_tab'),
    path('task/<str:task_id>/status/', views.get_task_status, name='task_status'),
    path('library/', views.library, name='library'),
]