"""
Modern Transcription Tasks - Clean Implementation
Uses MT3, Omnizart, and CREPE for maximum accuracy and traceability
"""
import asyncio
import logging
import time
import traceback
from datetime import timedelta
from typing import Dict, List, Optional

import os
from celery import shared_task, group, chain
from celery.result import allow_join_result
from django.utils import timezone
from django.conf import settings

from .models import Transcription, Track, TabExport, ConversionEvent, UsageAnalytics
from .services.advanced_transcription_service import get_advanced_service, AdvancedTranscriptionResult
from .services.export_manager import ExportManager
from .services.metrics_service import start_task_metrics, complete_task_metrics, update_progress
from .services.rate_limiter import check_openai_rate_limit, record_openai_request
from .utils.json_utils import ensure_json_serializable

logger = logging.getLogger(__name__)


# =======================================================
# MAIN TRANSCRIPTION TASKS (MODERN)
# =======================================================

@shared_task(bind=True, max_retries=2)
def process_transcription_advanced(self, transcription_id: str, accuracy_mode: str = 'maximum'):
    """
    Modern transcription task using MT3, Omnizart, and CREPE
    Replaces all legacy transcription code with clean, state-of-the-art implementation
    """
    start_time = time.time()
    logger.info(f"[ADVANCED] Starting transcription {transcription_id} (mode: {accuracy_mode})")
    
    # Start metrics tracking
    task_metrics = start_task_metrics(
        task_id=self.request.id,
        task_type="advanced_transcription",
        transcription_id=transcription_id
    )
    
    try:
        transcription = Transcription.objects.get(id=transcription_id)
        transcription.status = 'processing'
        transcription.processing_model_version = 'advanced_v2.0'
        transcription.save()
        
        # Validate audio file
        if not transcription.original_audio.name:
            raise ValueError(f"No audio file associated with transcription {transcription_id}")
        
        audio_path = transcription.original_audio.path
        if not os.path.exists(audio_path):
            raise ValueError(f"Audio file not found: {audio_path}")
        
        logger.info(f"Processing: {audio_path} ({os.path.getsize(audio_path) / 1024 / 1024:.1f}MB)")
        
        # Check OpenAI rate limits (for any AI analysis)
        can_proceed, retry_after = check_openai_rate_limit(estimated_cost=0.02)
        if not can_proceed:
            logger.info(f"Rate limited, retrying in {retry_after}s")
            raise self.retry(countdown=retry_after)
        
        # Update initial progress
        update_progress(transcription_id, 'overall', 10, 'initializing')
        self.update_state(
            state='PROGRESS',
            meta={'status': f'Starting advanced transcription ({accuracy_mode} mode)...', 'progress': 10}
        )
        
        # Run advanced transcription service
        advanced_service = get_advanced_service()
        
        # Use async method in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result: AdvancedTranscriptionResult = loop.run_until_complete(
                advanced_service.transcribe_audio_advanced(
                    audio_path=audio_path,
                    transcription_id=transcription_id,
                    accuracy_mode=accuracy_mode
                )
            )
        finally:
            loop.close()
        
        # Record OpenAI usage
        record_openai_request(cost=0.02)
        
        # Update transcription with results
        transcription.duration = result.duration
        transcription.sample_rate = result.sample_rate
        transcription.estimated_tempo = int(result.tempo)
        transcription.estimated_key = result.key
        transcription.complexity = result.complexity
        transcription.detected_instruments = ensure_json_serializable(result.detected_instruments)
        transcription.accuracy_score = result.accuracy_score
        transcription.models_used = ensure_json_serializable(list(result.models_used.values()))
        
        # Store advanced analysis results
        transcription.whisper_analysis = {
            'overall_confidence': result.overall_confidence,
            'confidence_scores': result.confidence_scores,
            'processing_times': result.processing_times,
            'models_used': result.models_used,
            'service_version': result.service_version,
            'timestamp': result.timestamp
        }
        
        # Store multi-track data
        transcription.multitrack_data = {
            'tracks_count': len(result.tracks),
            'instruments': result.detected_instruments,
            'confidence_scores': result.confidence_scores,
            'chord_progression': result.chord_progression,
            'beat_tracking': result.beat_tracking[:50] if result.beat_tracking else [],  # Limit size
            'accuracy_score': result.accuracy_score
        }
        
        # Store primary guitar notes (for backward compatibility)
        if 'guitar' in result.tracks:
            transcription.guitar_notes = ensure_json_serializable({
                'measures': self._convert_notes_to_measures(result.tracks['guitar'], result.tempo),
                'tempo': result.tempo,
                'time_signature': result.time_signature,
                'confidence': result.confidence_scores.get('guitar', 0.8)
            })
        
        # Update progress
        update_progress(transcription_id, 'overall', 70, 'creating_tracks')
        self.update_state(
            state='PROGRESS',
            meta={'status': 'Creating instrument tracks...', 'progress': 70}
        )
        
        # Create Track objects for each detected instrument
        created_tracks = []
        for instrument, notes in result.tracks.items():
            if notes:  # Only create tracks with actual content
                track = Track.objects.create(
                    transcription=transcription,
                    track_name=f"{instrument.title()} Track",
                    track_type=instrument if instrument in ['drums', 'bass', 'vocals'] else 'other',
                    instrument_type=instrument,
                    confidence_score=result.confidence_scores.get(instrument, 0.8),
                    guitar_notes=ensure_json_serializable(notes),
                    midi_data=ensure_json_serializable({
                        'notes': notes,
                        'model_used': result.models_used.get(instrument, 'MT3'),
                        'confidence': result.confidence_scores.get(instrument, 0.8)
                    }),
                    is_processed=True
                )
                created_tracks.append(track)
                logger.info(f"Created {instrument} track: {len(notes)} notes, confidence: {track.confidence_score:.2f}")
        
        # Update progress
        update_progress(transcription_id, 'overall', 85, 'generating_exports')
        self.update_state(
            state='PROGRESS',
            meta={'status': 'Generating MusicXML preview...', 'progress': 85}
        )
        
        # Generate MusicXML for free preview (always generated)
        try:
            export_manager = ExportManager(transcription)
            musicxml_content = export_manager.generate_multitrack_musicxml(created_tracks)
            transcription.musicxml_content = musicxml_content
            logger.info("Generated MusicXML preview for free users")
        except Exception as e:
            logger.warning(f"MusicXML generation failed: {e}")
            transcription.musicxml_content = ""
        
        # Final update
        transcription.status = 'completed'
        transcription.save()
        
        # Update progress to completion
        update_progress(transcription_id, 'overall', 100, 'completed')
        self.update_state(
            state='SUCCESS',
            meta={'status': 'Transcription completed!', 'progress': 100}
        )
        
        # Complete metrics tracking
        complete_task_metrics(self.request.id, 'success', additional_data={
            'instruments_detected': len(result.tracks),
            'accuracy_score': result.accuracy_score,
            'overall_confidence': result.overall_confidence,
            'models_used': list(result.models_used.values()),
            'total_notes': sum(len(notes) for notes in result.tracks.values())
        })
        
        total_time = time.time() - start_time
        logger.info(f"[ADVANCED] Transcription {transcription_id} completed successfully in {total_time:.2f}s")
        logger.info(f"Results: {len(result.tracks)} instruments, accuracy: {result.accuracy_score:.2f}, "
                   f"confidence: {result.overall_confidence:.2f}")
        
        return {
            'status': 'success',
            'transcription_id': transcription_id,
            'instruments_detected': result.detected_instruments,
            'accuracy_score': result.accuracy_score,
            'confidence': result.overall_confidence,
            'processing_time': total_time,
            'tracks_created': len(created_tracks)
        }
        
    except Exception as e:
        total_time = time.time() - start_time
        logger.error(f"[ADVANCED] Transcription {transcription_id} failed after {total_time:.2f}s: {str(e)}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        
        # Update transcription status
        try:
            transcription = Transcription.objects.get(id=transcription_id)
            transcription.status = 'failed'
            transcription.error_message = str(e)
            transcription.save()
        except Exception as db_error:
            logger.error(f"Failed to update transcription status: {db_error}")
        
        # Update progress and metrics
        update_progress(transcription_id, 'overall', 0, 'failed')
        complete_task_metrics(self.request.id, 'failed', error_type=type(e).__name__)
        
        # Don't retry for permanent errors
        error_msg = str(e).lower()
        permanent_errors = [
            'no audio file associated',
            'audio file not found',
            'invalid audio format',
            'file too large'
        ]
        
        if any(err in error_msg for err in permanent_errors):
            logger.error(f"Permanent error, not retrying: {str(e)}")
            return {
                'status': 'failed_permanently',
                'transcription_id': transcription_id,
                'error': str(e),
                'processing_time': total_time
            }
        
        # Retry with exponential backoff
        retry_countdown = 120 * (2 ** self.request.retries)  # 2, 4, 8 minutes
        logger.info(f"Retrying in {retry_countdown}s (attempt {self.request.retries + 1}/{self.max_retries})")
        raise self.retry(exc=e, countdown=retry_countdown)


# =======================================================
# EXPORT TASKS (PREMIUM GATED)
# =======================================================

@shared_task(bind=True)
def generate_premium_export(self, transcription_id: str, export_format: str, user_id: int):
    """
    Generate export file for premium users only
    Includes usage tracking and business analytics
    """
    start_time = time.time()
    logger.info(f"[PREMIUM_EXPORT] Generating {export_format} for user {user_id}")
    
    # Start metrics tracking
    task_metrics = start_task_metrics(
        task_id=self.request.id,
        task_type="premium_export",
        transcription_id=transcription_id
    )
    
    try:
        # Verify user has premium access
        from django.contrib.auth.models import User
        user = User.objects.get(id=user_id)
        
        if not user.profile.can_export_files():
            raise PermissionError(f"User {user_id} does not have export permissions")
        
        transcription = Transcription.objects.get(id=transcription_id)
        
        # Update progress
        update_progress(transcription_id, f'export_{export_format}', 20, 'starting')
        self.update_state(
            state='PROGRESS',
            meta={'status': f'Generating {export_format.upper()} export...', 'progress': 20}
        )
        
        # Generate export using enhanced export manager
        export_manager = ExportManager(transcription)
        
        if export_format == 'gp5':
            file_path = export_manager.export_gp5()
        elif export_format == 'midi':
            file_path = export_manager.export_midi()
        elif export_format == 'ascii':
            file_path = export_manager.export_ascii_tab()
        elif export_format == 'musicxml':
            file_path = export_manager.export_musicxml()
        elif export_format == 'stems':
            # Multi-track stems export
            tracks = Track.objects.filter(transcription=transcription)
            file_path = export_manager.generate_stem_archive(tracks)
        else:
            raise ValueError(f"Unsupported export format: {export_format}")
        
        if not file_path or not os.path.exists(file_path):
            raise ValueError(f"Export generation failed for {export_format}")
        
        # Create export record
        tab_export = TabExport.objects.create(
            transcription=transcription,
            format=export_format
        )
        
        # Save file through Django storage
        from django.core.files import File
        with open(file_path, 'rb') as f:
            file_name = f"{transcription.filename}_{export_format}.{self._get_file_extension(export_format)}"
            tab_export.file.save(file_name, File(f), save=True)
        
        # Clean up temporary file
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Update export analytics
        transcription.export_count += 1
        transcription.save(update_fields=['export_count'])
        
        # Track business analytics
        ConversionEvent.objects.create(
            user=user,
            event_type='exported_file',
            transcription=transcription,
            feature_name=export_format,
            metadata={
                'export_format': export_format,
                'file_size_kb': os.path.getsize(file_path) / 1024 if os.path.exists(file_path) else 0,
                'processing_time': time.time() - start_time
            }
        )
        
        # Update progress to completion
        update_progress(transcription_id, f'export_{export_format}', 100, 'completed')
        
        # Complete metrics
        complete_task_metrics(self.request.id, 'success', additional_data={
            'export_format': export_format,
            'file_size_kb': tab_export.file.size / 1024 if tab_export.file else 0
        })
        
        total_time = time.time() - start_time
        logger.info(f"[PREMIUM_EXPORT] {export_format} export completed in {total_time:.2f}s")
        
        return {
            'status': 'success',
            'export_id': tab_export.id,
            'file_url': tab_export.file.url if tab_export.file else None,
            'format': export_format,
            'processing_time': total_time
        }
        
    except Exception as e:
        total_time = time.time() - start_time
        logger.error(f"[PREMIUM_EXPORT] Failed after {total_time:.2f}s: {str(e)}")
        
        # Update progress and metrics
        update_progress(transcription_id, f'export_{export_format}', 0, 'failed')
        complete_task_metrics(self.request.id, 'failed', error_type=type(e).__name__)
        
        return {
            'status': 'error',
            'message': str(e),
            'processing_time': total_time
        }
    
    def _get_file_extension(self, export_format: str) -> str:
        """Get appropriate file extension for export format"""
        extensions = {
            'gp5': 'gp5',
            'midi': 'mid',
            'ascii': 'txt',
            'musicxml': 'xml',
            'stems': 'zip'
        }
        return extensions.get(export_format, 'bin')


@shared_task(bind=True)
def generate_variants_advanced(self, transcription_id: str, user_id: Optional[int] = None):
    """
    Generate fingering variants using advanced algorithms
    """
    start_time = time.time()
    logger.info(f"[VARIANTS] Generating advanced variants for {transcription_id}")
    
    try:
        transcription = Transcription.objects.get(id=transcription_id)
        
        # Import variant generator
        from .services.variant_generator import VariantGenerator
        variant_generator = VariantGenerator(transcription)
        
        # Generate all variants with enhanced algorithms
        variants = variant_generator.generate_all_variants()
        
        # Track analytics if user provided
        if user_id:
            try:
                from django.contrib.auth.models import User
                user = User.objects.get(id=user_id)
                ConversionEvent.objects.create(
                    user=user,
                    event_type='generated_variants',
                    transcription=transcription,
                    metadata={'variants_count': len(variants)}
                )
            except Exception as e:
                logger.warning(f"Failed to track variant generation: {e}")
        
        total_time = time.time() - start_time
        logger.info(f"[VARIANTS] Generated {len(variants)} variants in {total_time:.2f}s")
        
        return {
            'status': 'success',
            'transcription_id': transcription_id,
            'variants_count': len(variants),
            'processing_time': total_time
        }
        
    except Exception as e:
        logger.error(f"[VARIANTS] Failed: {str(e)}")
        return {
            'status': 'error',
            'message': str(e),
            'processing_time': time.time() - start_time
        }


# =======================================================
# MAINTENANCE TASKS
# =======================================================

@shared_task
def cleanup_old_transcriptions():
    """Clean up old transcriptions and temporary files"""
    start_time = time.time()
    cutoff_date = timezone.now() - timedelta(days=30)
    
    logger.info(f"[CLEANUP] Cleaning transcriptions older than {cutoff_date}")
    
    old_transcriptions = Transcription.objects.filter(
        created_at__lt=cutoff_date,
        status__in=['completed', 'failed']
    )
    
    count = 0
    total_size_freed = 0
    
    for transcription in old_transcriptions:
        try:
            # Clean up files
            files_to_clean = []
            
            if transcription.original_audio.name:
                files_to_clean.append(transcription.original_audio.path)
            
            if transcription.gp5_file.name:
                files_to_clean.append(transcription.gp5_file.path)
            
            # Clean export files
            for export in transcription.exports.all():
                if export.file.name:
                    files_to_clean.append(export.file.path)
            
            # Clean track audio files
            for track in transcription.tracks.all():
                if track.separated_audio and track.separated_audio.name:
                    files_to_clean.append(track.separated_audio.path)
            
            # Delete files
            for file_path in files_to_clean:
                try:
                    if os.path.exists(file_path):
                        size = os.path.getsize(file_path)
                        os.remove(file_path)
                        total_size_freed += size
                except Exception as e:
                    logger.warning(f"Could not delete {file_path}: {e}")
            
            # Delete transcription
            transcription.delete()
            count += 1
            
        except Exception as e:
            logger.error(f"Error cleaning transcription {transcription.id}: {e}")
    
    total_time = time.time() - start_time
    logger.info(f"[CLEANUP] Cleaned {count} transcriptions, freed {total_size_freed / 1024 / 1024:.1f}MB in {total_time:.2f}s")
    
    return {
        'transcriptions_cleaned': count,
        'size_freed_mb': total_size_freed / 1024 / 1024,
        'processing_time': total_time
    }


@shared_task
def update_usage_analytics():
    """Update daily usage analytics for business intelligence"""
    logger.info("[ANALYTICS] Updating usage analytics")
    
    try:
        from django.contrib.auth.models import User
        from django.db.models import Count, Avg, Sum
        
        # Get today's data
        today = timezone.now().date()
        
        # Update analytics for active users
        active_users = User.objects.filter(
            transcriptions__created_at__date=today
        ).distinct()
        
        for user in active_users:
            analytics, created = UsageAnalytics.objects.get_or_create(
                user=user,
                date=today
            )
            
            # Calculate daily metrics
            daily_transcriptions = user.transcriptions.filter(created_at__date=today)
            
            analytics.transcriptions_created = daily_transcriptions.count()
            analytics.exports_attempted = ConversionEvent.objects.filter(
                user=user,
                event_type='attempted_export',
                created_at__date=today
            ).count()
            analytics.exports_completed = daily_transcriptions.aggregate(
                total=Sum('export_count')
            )['total'] or 0
            
            # Calculate average accuracy
            accuracy_scores = daily_transcriptions.exclude(
                accuracy_score__isnull=True
            ).aggregate(avg=Avg('accuracy_score'))['avg']
            
            if accuracy_scores:
                analytics.avg_accuracy_score = accuracy_scores
            
            analytics.save()
        
        logger.info(f"[ANALYTICS] Updated analytics for {active_users.count()} users")
        return {'users_updated': active_users.count()}
        
    except Exception as e:
        logger.error(f"[ANALYTICS] Failed to update analytics: {e}")
        return {'error': str(e)}


@shared_task
def health_check_advanced():
    """Enhanced health check for advanced transcription system"""
    logger.info("[HEALTH] Running advanced system health check")
    
    try:
        # Check for stuck transcriptions
        timeout_threshold = timezone.now() - timedelta(hours=2)  # 2 hour timeout
        stuck_transcriptions = Transcription.objects.filter(
            status='processing',
            updated_at__lt=timeout_threshold
        )
        
        stuck_count = 0
        for transcription in stuck_transcriptions:
            time_stuck = timezone.now() - transcription.updated_at
            logger.warning(f"Transcription {transcription.id} stuck for {time_stuck}")
            
            transcription.status = 'failed'
            transcription.error_message = f'Processing timeout after {time_stuck}'
            transcription.save()
            stuck_count += 1
        
        # Check system resources
        from .services.metrics_service import metrics_service
        health = metrics_service.get_system_health()
        
        # Check OpenAI usage
        openai_usage = metrics_service.get_openai_usage_stats()
        
        health_report = {
            'stuck_transcriptions': stuck_count,
            'system_health': health,
            'openai_usage': openai_usage,
            'timestamp': timezone.now().isoformat()
        }
        
        logger.info(f"[HEALTH] Health check completed: {stuck_count} issues resolved")
        return health_report
        
    except Exception as e:
        logger.error(f"[HEALTH] Health check failed: {e}")
        return {'error': str(e)}


# =======================================================
# UTILITY FUNCTIONS
# =======================================================

def _convert_notes_to_measures(notes: List[Dict], tempo: float) -> List[Dict]:
    """Convert note list to measure-based format for backward compatibility"""
    if not notes:
        return []
    
    measures = []
    current_measure = 1
    measure_duration = 240.0 / tempo  # 4 beats at given tempo
    current_measure_start = 0.0
    current_measure_notes = []
    
    for note in notes:
        # Check if note belongs to current measure
        if note['start_time'] >= current_measure_start + measure_duration:
            # Finish current measure
            if current_measure_notes:
                measures.append({
                    'number': current_measure,
                    'start_time': current_measure_start,
                    'notes': current_measure_notes
                })
            
            # Start new measure
            current_measure += 1
            current_measure_start += measure_duration
            current_measure_notes = []
        
        # Convert note to tab format (simplified)
        tab_note = {
            'string': 0,  # Will be calculated by tab generator
            'fret': 0,    # Will be calculated by tab generator
            'time': note['start_time'] - current_measure_start,
            'duration': note['duration'],
            'velocity': note.get('velocity', 80),
            'midi_note': note['midi_note'],
            'confidence': note.get('confidence', 0.8)
        }
        current_measure_notes.append(tab_note)
    
    # Add final measure
    if current_measure_notes:
        measures.append({
            'number': current_measure,
            'start_time': current_measure_start,
            'notes': current_measure_notes
        })
    
    return measures


# Lazy imports to avoid heavy dependencies in web containers
def _get_export_manager():
    from .services.export_manager import ExportManager
    return ExportManager

def _get_advanced_service():
    from .services.advanced_transcription_service import get_advanced_service
    return get_advanced_service()
