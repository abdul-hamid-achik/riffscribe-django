from django.db import models
from django.urls import reverse
import uuid
import json


class Transcription(models.Model):
    """Model for audio transcriptions"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    COMPLEXITY_CHOICES = [
        ('simple', 'Simple'),
        ('moderate', 'Moderate'),
        ('complex', 'Complex'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    filename = models.CharField(max_length=255)
    original_audio = models.FileField(upload_to='audio/%Y/%m/%d/', null=True, blank=True)
    
    # Status tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True, null=True)
    
    # Audio analysis
    duration = models.FloatField(null=True, blank=True)  # in seconds
    sample_rate = models.IntegerField(null=True, blank=True)
    channels = models.IntegerField(default=1)
    estimated_tempo = models.IntegerField(null=True, blank=True)  # BPM
    estimated_key = models.CharField(max_length=20, blank=True)
    complexity = models.CharField(max_length=20, choices=COMPLEXITY_CHOICES, blank=True)
    
    # Detected instruments (stored as JSON)
    detected_instruments = models.JSONField(default=list, blank=True)
    
    # Transcription results
    midi_data = models.JSONField(null=True, blank=True)
    musicxml_content = models.TextField(blank=True)
    gp5_file = models.FileField(upload_to='gp5/%Y/%m/%d/', null=True, blank=True)
    guitar_notes = models.JSONField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.filename} - {self.get_status_display()}"
    
    def get_absolute_url(self):
        return reverse('transcriber:detail', kwargs={'pk': self.pk})
    
    @property
    def duration_formatted(self):
        """Return duration in MM:SS format"""
        if self.duration:
            minutes = int(self.duration // 60)
            seconds = int(self.duration % 60)
            return f"{minutes}:{seconds:02d}"
        return "--:--"
    
    @property
    def instruments_display(self):
        """Return instruments as comma-separated string"""
        if self.detected_instruments:
            return ", ".join(self.detected_instruments)
        return "Not detected"


class TabExport(models.Model):
    """Track exported tab files"""
    
    FORMAT_CHOICES = [
        ('musicxml', 'MusicXML'),
        ('gp5', 'Guitar Pro 5'),
        ('pdf', 'PDF'),
        ('ascii', 'ASCII Tab'),
    ]
    
    transcription = models.ForeignKey(Transcription, on_delete=models.CASCADE, related_name='exports')
    format = models.CharField(max_length=20, choices=FORMAT_CHOICES)
    file = models.FileField(upload_to='exports/%Y/%m/%d/')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.transcription.filename} - {self.get_format_display()}"
