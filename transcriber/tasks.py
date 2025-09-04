import os
import time
from .models import Transcription
from .audio_processing import AudioAnalyzer, GuitarTabGenerator
from django.utils import timezone
import json


def process_audio_file(transcription_id):
    try:
        transcription = Transcription.objects.get(id=transcription_id)
        transcription.status = 'processing'
        transcription.save()
        
        # Get the file path
        audio_path = transcription.original_audio.path
        
        # Initialize analyzer
        analyzer = AudioAnalyzer(audio_path)
        
        # Extract audio features
        duration = analyzer.get_duration()
        tempo, beats = analyzer.estimate_tempo()
        key = analyzer.estimate_key()
        complexity = analyzer.estimate_complexity()
        instruments = analyzer.detect_instruments()
        
        # Update transcription with analysis
        transcription.duration = duration
        transcription.estimated_tempo = int(tempo)
        transcription.estimated_key = key
        transcription.complexity = complexity
        transcription.detected_instruments = instruments
        transcription.save()
        
        # Extract pitch contour for tab generation
        pitch_contour = analyzer.extract_pitch_contour()
        
        # Generate guitar tabs
        if pitch_contour:
            tab_generator = GuitarTabGenerator(pitch_contour, tempo)
            tab_data = tab_generator.generate_tab_data()
            
            # Store tab data
            transcription.guitar_notes = tab_data
            transcription.midi_data = {
                'notes': [
                    {
                        'time': note['time'],
                        'midi': note['midi_note'],
                        'frequency': note['frequency']
                    }
                    for note in pitch_contour if note['midi_note']
                ]
            }
        
        # Mark as completed
        transcription.status = 'completed'
        transcription.updated_at = timezone.now()
        transcription.save()
        
    except Exception as e:
        # Handle errors
        transcription = Transcription.objects.get(id=transcription_id)
        transcription.status = 'failed'
        transcription.error_message = str(e)
        transcription.save()
        raise


def process_audio_file_sync(transcription_id):
    """
    Synchronous version for development.
    In production, use Celery for async processing.
    """
    import threading
    thread = threading.Thread(target=process_audio_file, args=(transcription_id,))
    thread.daemon = True
    thread.start()