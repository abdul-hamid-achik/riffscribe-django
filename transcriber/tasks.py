from celery import shared_task
from django.utils import timezone
from django.conf import settings
import os
import json
import logging
import time
import traceback
from datetime import timedelta
import gc
try:
    import psutil
except ImportError:
    psutil = None

from .models import Transcription, TabExport
# Lazy import for export manager (has heavy dependencies like music21)
def _get_export_manager():
    from .services.export_manager import ExportManager
    return ExportManager
from .utils.json_utils import ensure_json_serializable

# AI Transcription Service (new modular approach)
def _get_transcription_service():
    from .services.ai_transcription_agent import get_transcription_service
    return get_transcription_service()

def _get_tab_generator():
    from .services.tab_generator import TabGenerator
    return TabGenerator

def _get_variant_generator():
    from .services.variant_generator import VariantGenerator
    return VariantGenerator

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_transcription(self, transcription_id):
    """
    Main task for processing audio transcription.
    Uses the full ML pipeline including source separation and advanced transcription.
    """
    start_time = time.time()
    logger.info(f"[TASK START] Processing transcription {transcription_id}")
    logger.info(f"Task ID: {self.request.id}, Retry: {self.request.retries}")
    
    try:
        transcription = Transcription.objects.get(id=transcription_id)
        logger.info(f"Transcription found: {transcription.filename}, User: {transcription.user.id if transcription.user else 'Anonymous'}")
        transcription.status = 'processing'
        transcription.save()
        logger.info(f"Status updated to 'processing' for transcription {transcription_id}")
        
        # Initialize new modular AI transcription service
        logger.info("Initializing AI Transcription Service...")
        transcription_service = _get_transcription_service()
        logger.info("AI Transcription Service initialized successfully")
        
        # Process audio file - check if file exists first
        # Use .name instead of accessing the field directly to avoid ValueError
        if not transcription.original_audio.name:
            raise ValueError(f"Transcription {transcription_id} has no audio file associated with it")
        
        try:
            audio_path = transcription.original_audio.path
        except ValueError as e:
            raise ValueError(f"Transcription {transcription_id} audio file is not accessible: {str(e)}")
        
        if not os.path.exists(audio_path):
            raise ValueError(f"Audio file not found on disk: {audio_path}")
        
        logger.info(f"Processing audio file: {audio_path}")
        logger.info(f"File size: {os.path.getsize(audio_path) / 1024 / 1024:.2f} MB")
        
        # Step 1: AI-powered audio analysis with new service
        step_start = time.time()
        self.update_state(state='PROGRESS', meta={'step': 1, 'status': 'AI analyzing audio...', 'progress': 12})
        logger.info("[STEP 1] Starting AI audio analysis...")
        
        # Use async method in sync context
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            ai_result = loop.run_until_complete(transcription_service.transcribe_audio(audio_path))
        finally:
            loop.close()
        
        logger.info(f"[STEP 1] AI audio analysis completed in {time.time() - step_start:.2f}s")
        logger.info(f"AI Analysis results: Duration=563.9s, Tempo={ai_result.tempo}, Key={ai_result.key}, Instruments={ai_result.instruments}")
        
        # Log memory usage after analysis
        if psutil:
            memory_info = psutil.Process().memory_info()
            logger.info(f"Memory usage after analysis: {memory_info.rss / 1024 / 1024:.1f} MB")
        gc.collect()
        
        # Update transcription with AI results
        transcription.duration = ai_result.duration  # Use actual audio duration
        transcription.sample_rate = 44100  # Default
        transcription.channels = 2  # Default stereo
        transcription.estimated_tempo = float(ai_result.tempo)
        transcription.estimated_key = str(ai_result.key)
        transcription.complexity = str(ai_result.complexity)
        transcription.detected_instruments = ensure_json_serializable(ai_result.instruments)
        
        # Store AI analysis results
        transcription.whisper_analysis = {
            'confidence': ai_result.confidence,
            'summary': ai_result.analysis_summary,
            'chord_progression': ai_result.chord_progression
        }
        self.update_state(state='PROGRESS', meta={'step': 2, 'status': 'AI analysis complete...', 'progress': 22})
        logger.info(f"AI analysis stored: confidence={ai_result.confidence}")
        
        transcription.save()
        logger.info("Transcription metadata updated and saved")
        
        # Step 2: AI source analysis (no heavy separation needed!)
        step_start = time.time()
        self.update_state(state='PROGRESS', meta={'step': 2, 'status': 'AI source analysis complete...', 'progress': 25})
        logger.info("[STEP 2] Starting AI source analysis...")
        # AI processes mixed audio directly - no 4GB Demucs model needed!
        processing_audio = audio_path  # AI works with original audio
        logger.info(f"[STEP 2] AI source analysis completed in {time.time() - step_start:.2f}s")
        logger.info("[STEP 2] AI processes mixed audio directly - no heavy separation needed")
        
        # Step 3: Use AI transcription results from step 1 (already done!)
        step_start = time.time()
        self.update_state(state='PROGRESS', meta={'step': 3, 'status': 'Processing AI transcription results...', 'progress': 38})
        logger.info("[STEP 3] Processing AI transcription results...")
        
        # Create transcription results from AI result
        transcription_results = {
            'notes': ai_result.notes,
            'midi_data': {
                'ai_analysis': {
                    'tempo': ai_result.tempo,
                    'key': ai_result.key,
                    'time_signature': ai_result.time_signature,
                    'complexity': ai_result.complexity,
                    'instruments': ai_result.instruments,
                    'confidence': ai_result.confidence,
                    'summary': ai_result.analysis_summary
                }
            },
            'chord_data': ai_result.chord_progression
        }
        
        logger.info(f"[STEP 3] AI transcription results processed in {time.time() - step_start:.2f}s")
        logger.info(f"AI transcribed {len(transcription_results.get('notes', []))} notes")
        
        # Step 4: Generate guitar tabs with optimized string mapping
        step_start = time.time()
        self.update_state(state='PROGRESS', meta={'step': 4, 'status': 'Generating guitar tablature...', 'progress': 50})
        logger.info("[STEP 4] Starting guitar tab generation...")
        TabGenerator = _get_tab_generator()
        tab_generator = TabGenerator(
            notes=transcription_results['notes'],
            tempo=ai_result.tempo,
            time_signature=ai_result.time_signature
        )
        
        tab_data = tab_generator.generate_optimized_tabs()
        logger.info(f"[STEP 4] Guitar tabs generated in {time.time() - step_start:.2f}s")
        logger.info(f"Generated {len(tab_data) if isinstance(tab_data, (list, dict)) else 'N/A'} tab entries")
        
        # Store results (clean numpy arrays)
        transcription.midi_data = ensure_json_serializable(transcription_results['midi_data'])
        transcription.guitar_notes = ensure_json_serializable(tab_data)
        
        # Step 5: Generate MusicXML in background
        step_start = time.time()
        self.update_state(state='PROGRESS', meta={'step': 5, 'status': 'Queuing MusicXML generation...', 'progress': 62})
        logger.info("[STEP 5] Queuing MusicXML generation in background...")
        generate_export.delay(transcription.id, 'musicxml')
        logger.info(f"[STEP 5] MusicXML generation queued in {time.time() - step_start:.2f}s")
        
        # Step 6: Generate GP5 file in background  
        step_start = time.time()
        self.update_state(state='PROGRESS', meta={'step': 6, 'status': 'Queuing Guitar Pro file generation...', 'progress': 75})
        logger.info("[STEP 6] Queuing GP5 generation in background...")
        generate_export.delay(transcription.id, 'gp5')
        logger.info(f"[STEP 6] GP5 generation queued in {time.time() - step_start:.2f}s")
        
        # Step 7: Generate fingering variants
        step_start = time.time()
        self.update_state(state='PROGRESS', meta={'step': 7, 'status': 'Generating fingering variants...', 'progress': 85})
        logger.info("[STEP 7] Starting fingering variant generation...")
        VariantGenerator = _get_variant_generator()
        variant_generator = VariantGenerator(transcription)
        variants = variant_generator.generate_all_variants()
        logger.info(f"[STEP 7] Generated {len(variants)} fingering variants in {time.time() - step_start:.2f}s")
        if variants:
            logger.info(f"Variant scores: {[v.playability_score for v in variants[:3]]}...")
        
        # Step 8: Multi-track processing (skipped in new modular system)
        logger.info("[STEP 8] Multi-track processing (handled by new AI service - instruments already detected)")
        
        # Final completion step
        self.update_state(state='PROGRESS', meta={'step': 8, 'status': 'Finalizing transcription...', 'progress': 98})
        
        # Mark as completed
        transcription.status = 'completed'
        transcription.save()
        
        # Final success state
        self.update_state(state='SUCCESS', meta={'step': 8, 'status': 'Complete!', 'progress': 100})
        
        total_time = time.time() - start_time
        logger.info(f"[TASK COMPLETE] Transcription {transcription_id} processed successfully in {total_time:.2f}s")
        logger.info(f"Final stats: Duration={ai_result.duration}s, Notes={len(transcription_results['notes'])}, Variants={len(variants)}")
        
        return {
            'status': 'success',
            'transcription_id': str(transcription_id),
            'duration': ai_result.duration,
            'notes_count': len(transcription_results['notes']),
            'processing_time': total_time
        }
        
    except Exception as e:
        total_time = time.time() - start_time
        logger.error(f"[TASK FAILED] Error processing transcription {transcription_id} after {total_time:.2f}s: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        
        try:
            transcription = Transcription.objects.get(id=transcription_id)
            transcription.status = 'failed'
            transcription.error_message = str(e)
            transcription.save()
            logger.info(f"Transcription {transcription_id} marked as failed in database")
        except Exception as db_error:
            logger.error(f"Failed to update transcription status in database: {str(db_error)}")
        
        # Don't retry for permanent errors (missing files, invalid data)
        error_msg = str(e).lower()
        permanent_error_keywords = [
            'no audio file associated',
            'audio file is not accessible',
            'audio file not found on disk'
        ]
        
        is_permanent_error = any(keyword in error_msg for keyword in permanent_error_keywords)
        
        if is_permanent_error:
            logger.error(f"[TASK FAILED PERMANENTLY] Not retrying transcription {transcription_id} - permanent error: {str(e)}")
            return {
                'status': 'failed_permanently', 
                'transcription_id': str(transcription_id), 
                'error': str(e),
                'processing_time': total_time
            }
        
        # Retry with exponential backoff for temporary errors
        retry_countdown = 60 * (2 ** self.request.retries)
        logger.info(f"Retrying task in {retry_countdown} seconds (attempt {self.request.retries + 1}/{self.max_retries})")
        raise self.retry(exc=e, countdown=retry_countdown)


@shared_task
def generate_export(transcription_id, export_format):
    """
    Generate export file in specified format.
    """
    start_time = time.time()
    logger.info(f"[EXPORT START] Generating {export_format} export for transcription {transcription_id}")
    
    try:
        transcription = Transcription.objects.get(id=transcription_id)
        logger.info(f"Found transcription: {transcription.filename}")
        ExportManager = _get_export_manager()
        export_manager = ExportManager(transcription)
        
        logger.info(f"Starting {export_format} export generation...")
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
        
        logger.info(f"Export file generated at: {file_path}")
        
        # Check if export was successful
        if not file_path:
            raise ValueError(f"Export failed - no file generated (format may not be supported)")
        
        if not os.path.exists(file_path):
            raise ValueError(f"Export failed - file not found at {file_path}")
            
        file_size = os.path.getsize(file_path) / 1024
        logger.info(f"Export file size: {file_size:.2f} KB")
        
        # Create export record
        tab_export = TabExport.objects.create(
            transcription=transcription,
            format=export_format
        )
        
        # Save the file properly through Django's file storage
        from django.core.files import File
        
        with open(file_path, 'rb') as f:
            file_name = os.path.basename(file_path)
            tab_export.file.save(file_name, File(f), save=True)
        
        # Clean up temporary file
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info("Temporary file cleaned up")
        
        total_time = time.time() - start_time
        logger.info(f"[EXPORT COMPLETE] {export_format} export generated in {total_time:.2f}s")
        logger.info(f"Export ID: {tab_export.id}, URL: {tab_export.file.url if tab_export.file else 'N/A'}")
        
        return {
            'status': 'success',
            'export_id': tab_export.id,
            'file_url': tab_export.file.url if tab_export.file else None,
            'processing_time': total_time
        }
        
    except Exception as e:
        total_time = time.time() - start_time
        logger.error(f"[EXPORT FAILED] Error generating {export_format} export for {transcription_id} after {total_time:.2f}s: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return {
            'status': 'error',
            'message': str(e),
            'processing_time': total_time
        }


@shared_task
def generate_variants(transcription_id, preset=None):
    """
    Generate or regenerate fingering variants for a transcription.
    Can generate all presets or a specific one.
    """
    start_time = time.time()
    logger.info(f"[VARIANT START] Generating variants for transcription {transcription_id}, preset: {preset or 'ALL'}")
    
    try:
        transcription = Transcription.objects.get(id=transcription_id)
        logger.info(f"Found transcription: {transcription.filename}")
        VariantGenerator = _get_variant_generator()
        variant_generator = VariantGenerator(transcription)
        
        if preset:
            # Generate specific variant
            from .services.humanizer_service import HUMANIZER_PRESETS
            if preset not in HUMANIZER_PRESETS:
                raise ValueError(f"Unknown preset: {preset}")
            
            weights = HUMANIZER_PRESETS[preset]
            logger.info(f"Generating variant with preset '{preset}', weights: {weights}")
            variant = variant_generator.generate_variant(preset, weights)
            
            total_time = time.time() - start_time
            logger.info(f"[VARIANT COMPLETE] Generated '{preset}' variant in {total_time:.2f}s")
            logger.info(f"Playability score: {variant.playability_score if variant else 'N/A'}")
            
            return {
                'status': 'success',
                'transcription_id': str(transcription_id),
                'variant_name': preset,
                'playability_score': variant.playability_score if variant else None,
                'processing_time': total_time
            }
        else:
            # Generate all variants
            logger.info("Generating all fingering variants...")
            variants = variant_generator.generate_all_variants()
            
            total_time = time.time() - start_time
            logger.info(f"[VARIANT COMPLETE] Generated {len(variants)} variants in {total_time:.2f}s")
            for v in variants:
                logger.info(f"  - {v.variant_name}: score={v.playability_score:.2f}, selected={v.is_selected}")
            
            return {
                'status': 'success',
                'transcription_id': str(transcription_id),
                'variants_count': len(variants),
                'variants': [
                    {
                        'name': v.variant_name,
                        'playability_score': v.playability_score,
                        'is_selected': v.is_selected
                    }
                    for v in variants
                ],
                'processing_time': total_time
            }
            
    except Exception as e:
        total_time = time.time() - start_time
        logger.error(f"[VARIANT FAILED] Error generating variants for {transcription_id} after {total_time:.2f}s: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return {
            'status': 'error',
            'message': str(e),
            'processing_time': total_time
        }


@shared_task
def cleanup_old_transcriptions():
    """
    Periodic task to clean up old transcriptions and their files.
    """
    start_time = time.time()
    cutoff_date = timezone.now() - timedelta(days=30)
    logger.info(f"[CLEANUP START] Cleaning up transcriptions older than {cutoff_date}")
    
    old_transcriptions = Transcription.objects.filter(
        created_at__lt=cutoff_date,
        status__in=['completed', 'failed']
    )
    logger.info(f"Found {old_transcriptions.count()} transcriptions to clean up")
    
    count = 0
    files_deleted = 0
    total_size_freed = 0
    
    for transcription in old_transcriptions:
        trans_id = transcription.id
        logger.debug(f"Cleaning up transcription {trans_id}: {transcription.filename}")
        
        # Delete associated files
        if transcription.original_audio.name:
            try:
                audio_path = transcription.original_audio.path
                if os.path.exists(audio_path):
                    file_size = os.path.getsize(audio_path)
                    os.remove(audio_path)
                    files_deleted += 1
                    total_size_freed += file_size
                    logger.debug(f"  Deleted audio file: {audio_path} ({file_size / 1024:.2f} KB)")
            except ValueError:
                # File field has no file associated with it
                logger.debug(f"  Audio file field empty for transcription {trans_id}")
        else:
            logger.debug(f"  Audio file field empty for transcription {trans_id}")
        
        if transcription.gp5_file.name:
            try:
                gp5_path = transcription.gp5_file.path
                if os.path.exists(gp5_path):
                    file_size = os.path.getsize(gp5_path)
                    os.remove(gp5_path)
                    files_deleted += 1
                    total_size_freed += file_size
                    logger.debug(f"  Deleted GP5 file: {gp5_path} ({file_size / 1024:.2f} KB)")
            except ValueError:
                # File field has no file associated with it
                logger.debug(f"  GP5 file field empty for transcription {trans_id}")
        else:
            logger.debug(f"  GP5 file field empty for transcription {trans_id}")
        
        # Delete export files
        for export in transcription.exports.all():
            if export.file.name:
                try:
                    export_path = export.file.path
                    if os.path.exists(export_path):
                        file_size = os.path.getsize(export_path)
                        os.remove(export_path)
                        files_deleted += 1
                        total_size_freed += file_size
                        logger.debug(f"  Deleted export file: {export_path} ({file_size / 1024:.2f} KB)")
                except ValueError:
                    # File field has no file associated with it
                    logger.debug(f"  Export file field empty for export {export.id}")
            else:
                logger.debug(f"  Export file field empty for export {export.id}")
        
        transcription.delete()
        count += 1
        logger.debug(f"Transcription {trans_id} deleted from database")
    
    total_time = time.time() - start_time
    logger.info(f"[CLEANUP COMPLETE] Cleaned up {count} transcriptions in {total_time:.2f}s")
    logger.info(f"Files deleted: {files_deleted}, Space freed: {total_size_freed / 1024 / 1024:.2f} MB")
    return count


@shared_task
def check_transcription_health():
    """
    Health check task to monitor transcription processing.
    """
    start_time = time.time()
    logger.info("[HEALTH CHECK START] Checking for stuck transcriptions...")
    
    timeout_threshold = timezone.now() - timedelta(hours=1)
    stuck_transcriptions = Transcription.objects.filter(
        status='processing',
        updated_at__lt=timeout_threshold
    )
    
    stuck_count = stuck_transcriptions.count()
    logger.info(f"Found {stuck_count} stuck transcriptions")
    
    for transcription in stuck_transcriptions:
        time_stuck = timezone.now() - transcription.updated_at
        logger.warning(f"Transcription {transcription.id} has been processing for {time_stuck}")
        logger.warning(f"  Filename: {transcription.filename}, User: {transcription.user.id if transcription.user else 'Anonymous'}")
        
        transcription.status = 'failed'
        transcription.error_message = f'Processing timeout after {time_stuck}'
        transcription.save()
        logger.warning(f"  Marked as failed due to timeout")
    
    total_time = time.time() - start_time
    logger.info(f"[HEALTH CHECK COMPLETE] Processed {stuck_count} stuck transcriptions in {total_time:.2f}s")
    return stuck_count