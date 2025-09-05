from celery import shared_task
from django.utils import timezone
from django.conf import settings
import os
import json
import logging
from datetime import timedelta

from .models import Transcription, TabExport
from .ml_pipeline import MLPipeline
from .tab_generator import TabGenerator
from .export_manager import ExportManager

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_transcription(self, transcription_id):
    """
    Main task for processing audio transcription.
    Uses the full ML pipeline including source separation and advanced transcription.
    """
    try:
        transcription = Transcription.objects.get(id=transcription_id)
        transcription.status = 'processing'
        transcription.save()
        
        # Initialize ML pipeline
        pipeline = MLPipeline(
            use_gpu=settings.USE_GPU,
            demucs_model=settings.DEMUCS_MODEL,
            basic_pitch_model=settings.BASIC_PITCH_MODEL
        )
        
        # Process audio file
        audio_path = transcription.original_audio.path
        
        # Step 1: Audio analysis and preprocessing
        self.update_state(state='PROGRESS', meta={'step': 'Analyzing audio...'})
        analysis_results = pipeline.analyze_audio(audio_path)
        
        # Update transcription with basic info
        transcription.duration = analysis_results['duration']
        transcription.sample_rate = analysis_results['sample_rate']
        transcription.channels = analysis_results['channels']
        transcription.estimated_tempo = analysis_results['tempo']
        transcription.estimated_key = analysis_results['key']
        transcription.complexity = analysis_results['complexity']
        transcription.detected_instruments = analysis_results['instruments']
        transcription.save()
        
        # Step 2: Source separation (optional)
        self.update_state(state='PROGRESS', meta={'step': 'Separating guitar track...'})
        if 'guitar' in analysis_results['instruments'] or 'bass' in analysis_results['instruments']:
            separated_audio = pipeline.separate_sources(audio_path)
            processing_audio = separated_audio.get('guitar', audio_path)
        else:
            processing_audio = audio_path
        
        # Step 3: Pitch detection and transcription
        self.update_state(state='PROGRESS', meta={'step': 'Transcribing notes...'})
        transcription_results = pipeline.transcribe(processing_audio)
        
        # Step 4: Generate guitar tabs with optimized string mapping
        self.update_state(state='PROGRESS', meta={'step': 'Generating guitar tabs...'})
        tab_generator = TabGenerator(
            notes=transcription_results['notes'],
            tempo=analysis_results['tempo'],
            time_signature=analysis_results.get('time_signature', '4/4')
        )
        
        tab_data = tab_generator.generate_optimized_tabs()
        
        # Store results
        transcription.midi_data = transcription_results['midi_data']
        transcription.guitar_notes = tab_data
        
        # Step 5: Generate MusicXML
        self.update_state(state='PROGRESS', meta={'step': 'Creating MusicXML...'})
        export_manager = ExportManager(transcription)
        musicxml_content = export_manager.generate_musicxml(tab_data)
        transcription.musicxml_content = musicxml_content
        
        # Step 6: Generate GP5 file
        self.update_state(state='PROGRESS', meta={'step': 'Creating Guitar Pro file...'})
        gp5_path = export_manager.generate_gp5(tab_data)
        if gp5_path:
            transcription.gp5_file.name = gp5_path
        
        # Mark as completed
        transcription.status = 'completed'
        transcription.save()
        
        return {
            'status': 'success',
            'transcription_id': str(transcription_id),
            'duration': analysis_results['duration'],
            'notes_count': len(transcription_results['notes'])
        }
        
    except Exception as e:
        logger.error(f"Error processing transcription {transcription_id}: {str(e)}")
        transcription = Transcription.objects.get(id=transcription_id)
        transcription.status = 'failed'
        transcription.error_message = str(e)
        transcription.save()
        
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


@shared_task
def generate_export(transcription_id, export_format):
    """
    Generate export file in specified format.
    """
    try:
        transcription = Transcription.objects.get(id=transcription_id)
        export_manager = ExportManager(transcription)
        
        if export_format == 'musicxml':
            file_path = export_manager.export_musicxml()
        elif export_format == 'gp5':
            file_path = export_manager.export_gp5()
        elif export_format == 'midi':
            file_path = export_manager.export_midi()
        elif export_format == 'pdf':
            file_path = export_manager.export_pdf()
        elif export_format == 'ascii':
            file_path = export_manager.export_ascii_tab()
        else:
            raise ValueError(f"Unsupported export format: {export_format}")
        
        # Create export record
        tab_export = TabExport.objects.create(
            transcription=transcription,
            format=export_format,
            file=file_path
        )
        
        return {
            'status': 'success',
            'export_id': tab_export.id,
            'file_url': tab_export.file.url
        }
        
    except Exception as e:
        logger.error(f"Error generating export for {transcription_id}: {str(e)}")
        return {
            'status': 'error',
            'message': str(e)
        }


@shared_task
def cleanup_old_transcriptions():
    """
    Periodic task to clean up old transcriptions and their files.
    """
    cutoff_date = timezone.now() - timedelta(days=30)
    old_transcriptions = Transcription.objects.filter(
        created_at__lt=cutoff_date,
        status__in=['completed', 'failed']
    )
    
    count = 0
    for transcription in old_transcriptions:
        # Delete associated files
        if transcription.original_audio:
            if os.path.exists(transcription.original_audio.path):
                os.remove(transcription.original_audio.path)
        
        if transcription.gp5_file:
            if os.path.exists(transcription.gp5_file.path):
                os.remove(transcription.gp5_file.path)
        
        # Delete export files
        for export in transcription.exports.all():
            if export.file and os.path.exists(export.file.path):
                os.remove(export.file.path)
        
        transcription.delete()
        count += 1
    
    logger.info(f"Cleaned up {count} old transcriptions")
    return count


@shared_task
def check_transcription_health():
    """
    Health check task to monitor transcription processing.
    """
    stuck_transcriptions = Transcription.objects.filter(
        status='processing',
        updated_at__lt=timezone.now() - timedelta(hours=1)
    )
    
    for transcription in stuck_transcriptions:
        transcription.status = 'failed'
        transcription.error_message = 'Processing timeout'
        transcription.save()
        logger.warning(f"Marked transcription {transcription.id} as failed due to timeout")
    
    return stuck_transcriptions.count()