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
from .ml_pipeline import MLPipeline
from .tab_generator import TabGenerator
from .export_manager import ExportManager
from .variant_generator import VariantGenerator
from .json_utils import ensure_json_serializable

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
        
        # Initialize ML pipeline
        gpu_enabled = getattr(settings, 'USE_GPU', False)
        demucs_model = getattr(settings, 'DEMUCS_MODEL', 'htdemucs_ft')
        basic_pitch_model = getattr(settings, 'BASIC_PITCH_MODEL', 'default')
        multitrack_enabled = getattr(settings, 'ENABLE_MULTITRACK', True)
        
        logger.info(f"Initializing ML Pipeline - GPU: {gpu_enabled}, Demucs: {demucs_model}, Basic Pitch: {basic_pitch_model}, Multitrack: {multitrack_enabled}")
        
        pipeline = MLPipeline(
            use_gpu=gpu_enabled,
            demucs_model=demucs_model,
            basic_pitch_model=basic_pitch_model,
            enable_multitrack=multitrack_enabled
        )
        logger.info("ML Pipeline initialized successfully")
        
        # Process audio file
        audio_path = transcription.original_audio.path
        logger.info(f"Processing audio file: {audio_path}")
        logger.info(f"File size: {os.path.getsize(audio_path) / 1024 / 1024:.2f} MB")
        
        # Step 1: Audio analysis and preprocessing
        step_start = time.time()
        self.update_state(state='PROGRESS', meta={'step': 1, 'status': 'Analyzing audio file...', 'progress': 12})
        logger.info("[STEP 1] Starting audio analysis...")
        analysis_results = pipeline.analyze_audio(audio_path)
        logger.info(f"[STEP 1] Audio analysis completed in {time.time() - step_start:.2f}s")
        logger.info(f"Analysis results: Duration={analysis_results.get('duration')}s, Tempo={analysis_results.get('tempo')}, Key={analysis_results.get('key')}, Instruments={analysis_results.get('instruments')}")
        
        # Log memory usage after analysis
        if psutil:
            memory_info = psutil.Process().memory_info()
            logger.info(f"Memory usage after analysis: {memory_info.rss / 1024 / 1024:.1f} MB")
        gc.collect()
        
        # Update transcription with basic info (ensure all values are JSON serializable)
        transcription.duration = float(analysis_results['duration']) if analysis_results['duration'] else None
        transcription.sample_rate = int(analysis_results['sample_rate']) if analysis_results['sample_rate'] else None
        transcription.channels = int(analysis_results['channels']) if analysis_results['channels'] else None
        transcription.estimated_tempo = float(analysis_results['tempo']) if analysis_results['tempo'] else None
        transcription.estimated_key = str(analysis_results['key']) if analysis_results['key'] else None
        transcription.complexity = str(analysis_results['complexity']) if analysis_results['complexity'] else None
        transcription.detected_instruments = ensure_json_serializable(analysis_results['instruments'])
        
        # Store Whisper analysis if available
        if 'whisper_analysis' in analysis_results:
            # Clean numpy arrays from whisper analysis before storing
            cleaned_analysis = ensure_json_serializable(analysis_results['whisper_analysis'])
            transcription.whisper_analysis = cleaned_analysis
            self.update_state(state='PROGRESS', meta={'step': 2, 'status': 'Enhanced with Whisper AI detection...', 'progress': 22})
            logger.info(f"Whisper analysis stored: {len(str(cleaned_analysis))} chars")
            
        transcription.save()
        logger.info("Transcription metadata updated and saved")
        
        # Step 2: Source separation (optional)
        step_start = time.time()
        self.update_state(state='PROGRESS', meta={'step': 2, 'status': 'Separating guitar track...', 'progress': 25})
        logger.info("[STEP 2] Starting source separation...")
        if 'guitar' in analysis_results['instruments'] or 'bass' in analysis_results['instruments']:
            logger.info(f"Guitar/Bass detected, performing source separation")
            separated_audio = pipeline.separate_sources(audio_path)
            processing_audio = separated_audio.get('guitar', audio_path)
            logger.info(f"[STEP 2] Source separation completed in {time.time() - step_start:.2f}s")
        else:
            processing_audio = audio_path
            logger.info("[STEP 2] No guitar/bass detected, skipping source separation")
        
        # Step 3: Pitch detection and transcription (with Whisper context)
        step_start = time.time()
        if pipeline.whisper_service:
            self.update_state(state='PROGRESS', meta={'step': 3, 'status': 'Transcribing notes with Whisper AI...', 'progress': 38})
            logger.info("[STEP 3] Starting transcription with Whisper AI...")
        else:
            self.update_state(state='PROGRESS', meta={'step': 3, 'status': 'Transcribing notes...', 'progress': 35})
            logger.info("[STEP 3] Starting standard transcription...")
            
        # Pass analysis context to transcription for Whisper enhancement
        context = {
            'tempo': analysis_results.get('tempo'),
            'key': analysis_results.get('key'),
            'time_signature': analysis_results.get('time_signature'),
            'detected_instruments': analysis_results.get('instruments')
        }
        logger.info(f"Transcription context: {context}")
        transcription_results = pipeline.transcribe(processing_audio, context=context)
        logger.info(f"[STEP 3] Transcription completed in {time.time() - step_start:.2f}s")
        logger.info(f"Transcribed {len(transcription_results.get('notes', []))} notes")
        
        # Step 4: Generate guitar tabs with optimized string mapping
        step_start = time.time()
        self.update_state(state='PROGRESS', meta={'step': 4, 'status': 'Generating guitar tablature...', 'progress': 50})
        logger.info("[STEP 4] Starting guitar tab generation...")
        tab_generator = TabGenerator(
            notes=transcription_results['notes'],
            tempo=analysis_results['tempo'],
            time_signature=analysis_results.get('time_signature', '4/4')
        )
        
        tab_data = tab_generator.generate_optimized_tabs()
        logger.info(f"[STEP 4] Guitar tabs generated in {time.time() - step_start:.2f}s")
        logger.info(f"Generated {len(tab_data) if isinstance(tab_data, (list, dict)) else 'N/A'} tab entries")
        
        # Store results (clean numpy arrays)
        transcription.midi_data = ensure_json_serializable(transcription_results['midi_data'])
        transcription.guitar_notes = ensure_json_serializable(tab_data)
        
        # Step 5: Generate MusicXML
        step_start = time.time()
        self.update_state(state='PROGRESS', meta={'step': 5, 'status': 'Creating MusicXML notation...', 'progress': 62})
        logger.info("[STEP 5] Starting MusicXML generation...")
        export_manager = ExportManager(transcription)
        musicxml_content = export_manager.generate_musicxml(tab_data)
        transcription.musicxml_content = musicxml_content
        logger.info(f"[STEP 5] MusicXML generated in {time.time() - step_start:.2f}s")
        logger.info(f"MusicXML size: {len(musicxml_content) if musicxml_content else 0} chars")
        
        # Step 6: Generate GP5 file
        step_start = time.time()
        self.update_state(state='PROGRESS', meta={'step': 6, 'status': 'Creating Guitar Pro file...', 'progress': 75})
        logger.info("[STEP 6] Starting GP5 generation...")
        gp5_path = export_manager.generate_gp5(tab_data)
        if gp5_path:
            transcription.gp5_file.name = gp5_path
            logger.info(f"[STEP 6] GP5 file generated in {time.time() - step_start:.2f}s at {gp5_path}")
        else:
            logger.warning("[STEP 6] GP5 generation skipped or failed")
        
        # Step 7: Generate fingering variants
        step_start = time.time()
        self.update_state(state='PROGRESS', meta={'step': 7, 'status': 'Generating fingering variants...', 'progress': 85})
        logger.info("[STEP 7] Starting fingering variant generation...")
        variant_generator = VariantGenerator(transcription)
        variants = variant_generator.generate_all_variants()
        logger.info(f"[STEP 7] Generated {len(variants)} fingering variants in {time.time() - step_start:.2f}s")
        if variants:
            logger.info(f"Variant scores: {[v.playability_score for v in variants[:3]]}...")
        
        # Step 8: Multi-track processing (if enabled)
        if getattr(settings, 'ENABLE_MULTITRACK', True) and pipeline.multi_track_service:
            step_start = time.time()
            try:
                self.update_state(state='PROGRESS', meta={'step': 8, 'status': 'Processing multi-track separation...', 'progress': 92})
                logger.info("[STEP 8] Starting multi-track processing...")
                multitrack_result = pipeline.process_multitrack_transcription(transcription)
                
                if not multitrack_result.get('fallback', False):
                    logger.info(f"[STEP 8] Multi-track processing completed in {time.time() - step_start:.2f}s")
                    logger.info(f"Created {multitrack_result['track_count']} tracks, processed {multitrack_result['processed_count']} successfully")
                    self.update_state(state='PROGRESS', meta={
                        'step': f"Processed {multitrack_result['processed_count']} tracks successfully"
                    })
                else:
                    logger.info(f"[STEP 8] Multi-track processing fell back to single track")
                    
            except Exception as e:
                logger.warning(f"[STEP 8] Multi-track processing failed after {time.time() - step_start:.2f}s: {str(e)}")
                logger.debug(f"Multi-track error traceback: {traceback.format_exc()}")
                # Multi-track is optional, so we continue even if it fails
        else:
            logger.info("[STEP 8] Multi-track processing skipped (disabled or not available)")
        
        # Final completion step
        self.update_state(state='PROGRESS', meta={'step': 8, 'status': 'Finalizing transcription...', 'progress': 98})
        
        # Mark as completed
        transcription.status = 'completed'
        transcription.save()
        
        # Final success state
        self.update_state(state='SUCCESS', meta={'step': 8, 'status': 'Complete!', 'progress': 100})
        
        total_time = time.time() - start_time
        logger.info(f"[TASK COMPLETE] Transcription {transcription_id} processed successfully in {total_time:.2f}s")
        logger.info(f"Final stats: Duration={analysis_results['duration']}s, Notes={len(transcription_results['notes'])}, Variants={len(variants)}")
        
        return {
            'status': 'success',
            'transcription_id': str(transcription_id),
            'duration': analysis_results['duration'],
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
        
        # Retry with exponential backoff
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
        variant_generator = VariantGenerator(transcription)
        
        if preset:
            # Generate specific variant
            from .fingering_optimizer import FINGERING_PRESETS
            if preset not in FINGERING_PRESETS:
                raise ValueError(f"Unknown preset: {preset}")
            
            weights = FINGERING_PRESETS[preset]
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
        if transcription.original_audio:
            if os.path.exists(transcription.original_audio.path):
                file_size = os.path.getsize(transcription.original_audio.path)
                os.remove(transcription.original_audio.path)
                files_deleted += 1
                total_size_freed += file_size
                logger.debug(f"  Deleted audio file: {transcription.original_audio.path} ({file_size / 1024:.2f} KB)")
        
        if transcription.gp5_file:
            if os.path.exists(transcription.gp5_file.path):
                file_size = os.path.getsize(transcription.gp5_file.path)
                os.remove(transcription.gp5_file.path)
                files_deleted += 1
                total_size_freed += file_size
                logger.debug(f"  Deleted GP5 file: {transcription.gp5_file.path} ({file_size / 1024:.2f} KB)")
        
        # Delete export files
        for export in transcription.exports.all():
            if export.file and os.path.exists(export.file.path):
                file_size = os.path.getsize(export.file.path)
                os.remove(export.file.path)
                files_deleted += 1
                total_size_freed += file_size
                logger.debug(f"  Deleted export file: {export.file.path} ({file_size / 1024:.2f} KB)")
        
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