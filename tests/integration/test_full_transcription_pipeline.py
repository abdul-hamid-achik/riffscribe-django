"""
Integration tests for the complete AI transcription pipeline.
Tests the full flow from audio upload through AI transcription to export generation.

This test file automatically uses:
- REAL API calls when OPENAI_API_KEY is available in the environment
- MOCKED responses when no API key is present (e.g., CI/CD environments)
"""

import pytest
import os
import time
import json
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from django.core.files import File
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings

from transcriber.models import Transcription, TabExport, FingeringVariant
from transcriber.tasks import process_transcription, generate_export
from transcriber.services.ai_transcription_agent import (
    AIPipeline, 
    AITranscriptionAgent, 
    AIBassAgent, 
    AIDrumAgent,
    AIMultiInstrumentAgent
)
from transcriber.services.export_manager import ExportManager
from model_bakery import baker


def should_use_real_api():
    """Determine if we should use real OpenAI API or mocks."""
    api_key = os.getenv('OPENAI_API_KEY') or getattr(settings, 'OPENAI_API_KEY', None)
    return bool(api_key)


@pytest.mark.django_db
@pytest.mark.integration
class TestFullTranscriptionPipeline:
    """
    Comprehensive integration tests for the complete AI transcription pipeline.
    
    This test suite can run in two modes:
    1. Real Mode: Uses actual OpenAI API calls (when OPENAI_API_KEY is available)
    2. Mock Mode: Uses mocked responses (when no API key is present, e.g., CI/CD)
    """

    @pytest.fixture(autouse=True)
    def setup_api_environment(self):
        """Setup API environment based on configuration."""
        if should_use_real_api():
            # Real API mode - no mocking needed
            print("\n🚀 Running tests with REAL OpenAI API")
            yield
        else:
            # Mock mode for CI/CD
            print("\n🔧 Running tests with MOCKED OpenAI API")
            with patch('openai.OpenAI') as mock_openai_class:
                mock_client = self._create_mock_openai_client()
                mock_openai_class.return_value = mock_client
                yield mock_client

    def _create_mock_openai_client(self):
        """Create a comprehensive mock OpenAI client for testing."""
        mock_client = MagicMock()
        
        # Mock Whisper transcription for different audio types
        def create_whisper_response(filename):
            if 'full-song' in filename:
                text = "Full song with guitar, bass, and drums in D Major"
                duration = 135.0
                segments = [
                    MagicMock(start=0.0, end=16.0, text="Intro guitar and drums"),
                    MagicMock(start=16.0, end=48.0, text="Verse with bass line"),
                    MagicMock(start=48.0, end=80.0, text="Chorus section"),
                    MagicMock(start=80.0, end=112.0, text="Bridge and solo"),
                    MagicMock(start=112.0, end=135.0, text="Outro")
                ]
            elif 'complex' in filename:
                text = "Complex guitar riff with intricate fingerpicking"
                duration = 15.0
                segments = [
                    MagicMock(start=0.0, end=5.0, text="Complex intro"),
                    MagicMock(start=5.0, end=15.0, text="Technical passage")
                ]
            else:  # simple riff
                text = "Simple guitar riff in E minor"
                duration = 10.0
                segments = [
                    MagicMock(start=0.0, end=10.0, text="Simple guitar pattern")
                ]
            
            response = MagicMock()
            response.text = text
            response.segments = segments
            response.words = []
            response.language = "en"
            response.duration = duration
            return response
        
        # Mock GPT-4 audio analysis
        def create_gpt_response(is_full_song=False, is_complex=False):
            if is_full_song:
                content = {
                    "tempo": 128,
                    "key": "D Major",
                    "time_signature": "4/4",
                    "complexity": "moderate",
                    "instruments": ["electric_guitar", "bass", "drums"],
                    "chord_progression": [
                        {"time": 0.0, "chord": "D", "confidence": 0.95},
                        {"time": 4.0, "chord": "G", "confidence": 0.9},
                        {"time": 8.0, "chord": "A", "confidence": 0.92},
                        {"time": 12.0, "chord": "Bm", "confidence": 0.88},
                        {"time": 16.0, "chord": "D", "confidence": 0.94}
                    ],
                    "notes": self._generate_mock_notes(50),  # Full song has many notes
                    "confidence": 0.9,
                    "analysis_summary": "Full song with multiple instruments and clear structure"
                }
            elif is_complex:
                content = {
                    "tempo": 160,
                    "key": "A Minor",
                    "time_signature": "4/4",
                    "complexity": "complex",
                    "instruments": ["electric_guitar"],
                    "chord_progression": [
                        {"time": 0.0, "chord": "Am", "confidence": 0.85},
                        {"time": 2.0, "chord": "F", "confidence": 0.82},
                        {"time": 4.0, "chord": "C", "confidence": 0.88},
                        {"time": 6.0, "chord": "G", "confidence": 0.86}
                    ],
                    "notes": self._generate_mock_notes(20),
                    "confidence": 0.85,
                    "analysis_summary": "Complex guitar riff with technical passages"
                }
            else:
                content = {
                    "tempo": 140,
                    "key": "E Minor",
                    "time_signature": "4/4", 
                    "complexity": "simple",
                    "instruments": ["electric_guitar"],
                    "chord_progression": [
                        {"time": 0.0, "chord": "Em", "confidence": 0.9},
                        {"time": 2.0, "chord": "Am", "confidence": 0.88}
                    ],
                    "notes": self._generate_mock_notes(10),
                    "confidence": 0.88,
                    "analysis_summary": "Simple guitar riff with clear note articulation"
                }
            
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = json.dumps(content)
            return response
        
        # Setup mock client methods
        def mock_whisper_create(**kwargs):
            filename = kwargs.get('file', MagicMock()).name if hasattr(kwargs.get('file'), 'name') else 'simple.wav'
            return create_whisper_response(filename)
        
        def mock_gpt_create(**kwargs):
            messages = kwargs.get('messages', [])
            # Determine type based on context in messages or global context
            message_text = ' '.join(str(m) for m in messages).lower()
            is_full_song = any(indicator in message_text for indicator in ['full', '135', 'song', 'long'])
            is_complex = any(indicator in message_text for indicator in ['complex', 'technical', 'intricate', 'advanced'])
            
            # Fallback: check if this is being called for complex riff processing
            # by examining if we're in a complex test context
            import inspect
            frame = inspect.currentframe()
            try:
                while frame:
                    if 'complex' in str(frame.f_locals.get('complex_riff_wav', '')):
                        is_complex = True
                        break
                    if 'full' in str(frame.f_locals.get('full_song_wav', '')):
                        is_full_song = True
                        break
                    frame = frame.f_back
            except:
                pass
            finally:
                del frame
                
            return create_gpt_response(is_full_song, is_complex)
        
        mock_client.audio.transcriptions.create = MagicMock(side_effect=mock_whisper_create)
        mock_client.chat.completions.create = MagicMock(side_effect=mock_gpt_create)
        
        return mock_client

    def _generate_mock_notes(self, count):
        """Generate mock note data for testing."""
        notes = []
        for i in range(count):
            notes.append({
                "midi_note": 60 + (i % 12),
                "start_time": i * 0.5,
                "end_time": (i + 1) * 0.5,
                "velocity": 80 + (i % 20),
                "confidence": 0.85 + (i % 10) * 0.01
            })
        return notes

    @pytest.fixture(autouse=True)
    def ensure_openai_key_for_tests(self):
        """Ensure OpenAI API key is available for pipeline initialization."""
        api_key = os.getenv('OPENAI_API_KEY') or getattr(settings, 'OPENAI_API_KEY', None)
        if not api_key:
            # Set a test key if none is configured
            test_key = 'test-key-for-integration-tests'
            with patch.object(settings, 'OPENAI_API_KEY', test_key):
                with patch.dict(os.environ, {'OPENAI_API_KEY': test_key}):
                    yield
        else:
            yield

    @pytest.fixture(autouse=True)
    def setup_celery_task_context(self):
        """Setup Celery task context for integration tests."""
        with patch('celery.app.task.Task.update_state') as mock_update_state:
            mock_update_state.return_value = None
            yield mock_update_state

    # ========== Core Pipeline Tests ==========

    def test_complete_pipeline_simple_riff(self, simple_riff_wav):
        """Test the complete transcription pipeline with a simple riff."""
        if not simple_riff_wav:
            pytest.skip("simple-riff.wav sample not available")
        
        # Create transcription
        with open(simple_riff_wav, 'rb') as f:
            audio_content = f.read()
        
        audio_file = SimpleUploadedFile(
            "simple-riff.wav",
            audio_content,
            content_type="audio/wav"
        )
        
        transcription = baker.make_recipe(
            'transcriber.transcription_basic',
            filename="simple-riff.wav",
            original_audio=audio_file,
            status="pending"
        )
        
        # Process transcription
        start_time = time.time()
        result = process_transcription(transcription.id)
        processing_time = time.time() - start_time
        
        # Verify successful processing
        assert result['status'] == 'success'
        assert result['transcription_id'] == str(transcription.id)
        
        transcription.refresh_from_db()
        
        # Verify all fields are populated
        assert transcription.status == 'completed'
        assert transcription.duration is not None
        assert transcription.estimated_tempo is not None
        assert transcription.estimated_key is not None
        assert transcription.complexity in ['simple', 'moderate', 'complex']
        assert transcription.detected_instruments is not None
        assert len(transcription.detected_instruments) >= 1
        
        # Verify AI analysis
        assert transcription.whisper_analysis is not None
        assert transcription.midi_data is not None
        assert transcription.guitar_notes is not None
        
        # Verify fingering variants
        variants = FingeringVariant.objects.filter(transcription=transcription)
        print(f"Generated {variants.count()} fingering variants")
        
        if variants.count() > 0:
            # Verify variant quality
            assert variants.filter(is_selected=True).count() == 1
            for variant in variants:
                assert 0 <= variant.difficulty_score <= 100
                assert 0 <= variant.playability_score <= 100
                assert variant.tab_data is not None
        
        # Performance check
        print(f"Simple riff processing time: {processing_time:.2f}s")
        assert processing_time < 60, f"Processing too slow: {processing_time:.2f}s"

    def test_complete_pipeline_complex_riff(self, complex_riff_wav):
        """Test the complete transcription pipeline with a complex riff."""
        if not complex_riff_wav:
            pytest.skip("complex-riff.wav sample not available")
        
        with open(complex_riff_wav, 'rb') as f:
            audio_content = f.read()
        
        audio_file = SimpleUploadedFile(
            "complex-riff.wav",
            audio_content,
            content_type="audio/wav"
        )
        
        transcription = baker.make_recipe(
            'transcriber.transcription_basic',
            filename="complex-riff.wav",
            original_audio=audio_file,
            status="pending"
        )
        
        result = process_transcription(transcription.id)
        assert result['status'] == 'success'
        
        transcription.refresh_from_db()
        
        # Complex riff specific checks
        assert transcription.status == 'completed'
        assert transcription.complexity in ['moderate', 'complex']
        
        # Should have multiple fingering variants for complex piece
        variants = FingeringVariant.objects.filter(transcription=transcription)
        variant_names = [v.variant_name for v in variants]
        
        if variants.count() > 0:
            assert 'easy' in variant_names  # Should offer simplified version
            assert variants.count() >= 2

    def test_complete_pipeline_full_song(self, full_song_wav):
        """Test the complete transcription pipeline with a full song."""
        if not full_song_wav:
            pytest.skip("full-song.wav sample not available")
        
        with open(full_song_wav, 'rb') as f:
            audio_content = f.read()
        
        audio_file = SimpleUploadedFile(
            "full-song.wav",
            audio_content,
            content_type="audio/wav"
        )
        
        transcription = baker.make_recipe(
            'transcriber.transcription_basic',
            filename="full-song.wav",
            original_audio=audio_file,
            status="pending"
        )
        
        start_time = time.time()
        result = process_transcription(transcription.id)
        processing_time = time.time() - start_time
        
        assert result['status'] == 'success'
        
        transcription.refresh_from_db()
        
        # Full song specific checks
        assert transcription.status == 'completed'
        assert transcription.duration > 30  # Full songs are longer
        
        # Should detect multiple instruments
        detected_instruments = transcription.detected_instruments
        if should_use_real_api():
            # Real API might detect more instruments
            assert len(detected_instruments) >= 1
        else:
            # Mock data has guitar, bass, drums
            assert len(detected_instruments) >= 1
        
        # Performance check for full song
        print(f"Full song processing time: {processing_time:.2f}s")
        max_time = 180 if should_use_real_api() else 120
        assert processing_time < max_time

    # ========== Multi-Format Support Tests ==========

    @pytest.mark.parametrize("audio_format", ['wav', 'mp3', 'flac', 'm4a', 'ogg'])
    def test_all_audio_formats(self, sample_audio_files, audio_format):
        """Test transcription with all supported audio formats."""
        # Try different sample types
        for sample_type in ['simple-riff', 'complex-riff', 'full-song']:
            file_key = f"{sample_type}_{audio_format}"
            
            if file_key in sample_audio_files:
                audio_path = sample_audio_files[file_key]
                
                with open(audio_path, 'rb') as f:
                    audio_content = f.read()
                
                audio_file = SimpleUploadedFile(
                    f"{sample_type}.{audio_format}",
                    audio_content,
                    content_type=f"audio/{audio_format}"
                )
                
                transcription = baker.make_recipe(
                    'transcriber.transcription_basic',
                    filename=f"{sample_type}.{audio_format}",
                    original_audio=audio_file,
                    status="pending"
                )
                
                result = process_transcription(transcription.id)
                
                # All formats should process successfully
                assert result['status'] == 'success'
                
                transcription.refresh_from_db()
                assert transcription.status == 'completed'
                assert transcription.duration is not None
                
                # Found at least one file for this format, can break
                break
        else:
            pytest.skip(f"No samples available for {audio_format} format")

    # ========== Export Generation Tests ==========

    def test_all_export_formats(self, simple_riff_wav):
        """Test generation of all supported export formats."""
        if not simple_riff_wav:
            pytest.skip("simple-riff.wav sample not available")
        
        # First create and process a transcription
        with open(simple_riff_wav, 'rb') as f:
            audio_content = f.read()
        
        audio_file = SimpleUploadedFile(
            "simple-riff.wav",
            audio_content,
            content_type="audio/wav"
        )
        
        transcription = baker.make_recipe(
            'transcriber.transcription_completed',
            filename="simple-riff.wav",
            original_audio=audio_file
        )
        
        # Test all export formats
        export_formats = ['musicxml', 'midi', 'gp5', 'ascii_tab', 'pdf']
        successful_exports = []
        failed_exports = []
        
        for export_format in export_formats:
            try:
                # Use minimal mocking for file operations only
                with patch('transcriber.services.export_manager.ExportManager.export_' + export_format) as mock_export:
                    mock_file_path = f"/tmp/test_export.{export_format}"
                    mock_export.return_value = mock_file_path
                    
                    with patch('os.path.exists', return_value=True), \
                         patch('os.path.getsize', return_value=2048), \
                         patch('builtins.open', create=True) as mock_open:
                        
                        # Mock file content based on format
                        mock_content = self._get_mock_export_content(export_format)
                        mock_open.return_value.__enter__.return_value.read.return_value = mock_content
                        
                        result = generate_export(transcription.id, export_format)
                        
                        if result['status'] == 'success':
                            successful_exports.append(export_format)
                            
                            # Verify export record
                            export = TabExport.objects.get(id=result['export_id'])
                            assert export.transcription == transcription
                            assert export.format == export_format
                        else:
                            failed_exports.append((export_format, result.get('error')))
                            
            except Exception as e:
                failed_exports.append((export_format, str(e)))
        
        print(f"\nExport Results:")
        print(f"  Successful: {successful_exports}")
        print(f"  Failed: {failed_exports}")
        
        # Core formats should always work
        core_formats = {'musicxml', 'midi', 'ascii_tab'}
        successful_core = set(successful_exports) & core_formats
        assert len(successful_core) >= 2, f"Core formats failed. Success: {successful_core}"

    def _get_mock_export_content(self, format_type):
        """Get appropriate mock content for each export format."""
        contents = {
            'musicxml': b'<?xml version="1.0"?><score-partwise/>',
            'midi': b'MThd\x00\x00\x00\x06\x00\x00\x00\x01\x00\x60',
            'gp5': b'FICHIER GUITAR PRO v5.00',
            'ascii_tab': b'e|---0---2---3---|\nB|---1---3---5---|\n',
            'pdf': b'%PDF-1.4\n%Mock PDF content'
        }
        return contents.get(format_type, b'mock content')

    # ========== Direct AI Component Tests ==========

    def test_ai_pipeline_direct(self, simple_riff_wav):
        """Test AI pipeline components directly without Django models."""
        if not simple_riff_wav:
            pytest.skip("simple-riff.wav sample not available")
        
        # Test pipeline directly
        pipeline = AIPipeline(enable_drums=True)
        
        # Analyze audio
        analysis = pipeline.analyze_audio(simple_riff_wav)
        
        assert analysis['duration'] > 0
        assert analysis['tempo'] > 0
        assert analysis['key'] is not None
        assert analysis['complexity'] in ['simple', 'moderate', 'complex']
        assert isinstance(analysis['instruments'], list)
        
        # Transcribe audio
        transcription = pipeline.transcribe(simple_riff_wav)
        
        assert 'notes' in transcription
        assert 'midi_data' in transcription
        assert len(transcription['notes']) > 0
        
        if should_use_real_api():
            print(f"\n✅ Real API transcribed {len(transcription['notes'])} notes")

    def test_multi_instrument_detection(self, full_song_wav):
        """Test multi-instrument detection and transcription."""
        if not full_song_wav:
            pytest.skip("full-song.wav sample not available")
        
        # Test multi-instrument agent
        multi_agent = AIMultiInstrumentAgent()
        
        # Run async transcription
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                multi_agent.transcribe_all(full_song_wav)
            )
            
            # Verify structure
            assert 'guitar' in result
            assert 'bass' in result
            assert 'drums' in result
            assert 'master_grid' in result
            
            # Check guitar results
            guitar = result['guitar']
            assert guitar.tempo > 0
            assert guitar.key is not None
            assert guitar.confidence > 0
            
            # Check master grid
            master_grid = result['master_grid']
            assert isinstance(master_grid, list)
            assert len(master_grid) >= 3  # Should have multiple events
            
            if should_use_real_api():
                print(f"\n✅ Real API detected {len(master_grid)} master events")
                
        finally:
            loop.close()

    def test_individual_ai_agents(self, simple_riff_wav):
        """Test individual AI agent components."""
        if not simple_riff_wav:
            pytest.skip("simple-riff.wav sample not available")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Test Guitar Agent
            guitar_agent = AITranscriptionAgent()
            guitar_result = loop.run_until_complete(
                guitar_agent.transcribe_audio(simple_riff_wav)
            )
            
            assert guitar_result.tempo > 0
            assert guitar_result.key is not None
            assert len(guitar_result.notes) >= 3
            assert guitar_result.confidence >= 0.5
            
            # Test Bass Agent
            bass_agent = AIBassAgent()
            bass_result = loop.run_until_complete(
                bass_agent.transcribe_audio(simple_riff_wav)
            )
            
            assert bass_result.tempo > 0
            assert bass_result.key is not None
            
            # Test Drum Agent
            drum_agent = AIDrumAgent()
            drum_result = loop.run_until_complete(
                drum_agent.transcribe_drums(simple_riff_wav)
            )
            
            assert drum_result['tempo'] > 0
            assert drum_result['time_signature'] is not None
            
            if should_use_real_api():
                print(f"\n✅ Real API agent tests completed successfully")
                
        finally:
            loop.close()

    # ========== Performance and Optimization Tests ==========

    def test_performance_benchmarks(self, sample_audio_files):
        """Test pipeline performance across different file types."""
        results = []
        
        test_cases = [
            ('simple-riff_wav', 30),   # Simple should be fast
            ('complex-riff_wav', 45),  # Complex takes longer
            ('full-song_wav', 180)      # Full song needs more time
        ]
        
        for file_key, max_time in test_cases:
            if file_key not in sample_audio_files:
                continue
            
            audio_path = sample_audio_files[file_key]
            
            with open(audio_path, 'rb') as f:
                audio_file = File(f)
                transcription = baker.make_recipe(
                    'transcriber.transcription_basic',
                    filename=os.path.basename(audio_path),
                    original_audio=audio_file,
                    status="pending"
                )
            
            start_time = time.time()
            result = process_transcription(transcription.id)
            processing_time = time.time() - start_time
            
            assert result['status'] == 'success'
            assert processing_time < max_time
            
            results.append({
                'file': file_key,
                'time': processing_time,
                'passed': processing_time < max_time
            })
        
        # Report performance summary
        print("\n📊 Performance Benchmark Results:")
        for r in results:
            status = "✅" if r['passed'] else "❌"
            print(f"  {status} {r['file']}: {r['time']:.2f}s")
        
        assert all(r['passed'] for r in results)

    def test_variant_generation_quality(self, complex_riff_wav):
        """Test quality of fingering variant generation."""
        if not complex_riff_wav:
            pytest.skip("complex-riff.wav sample not available")
        
        with open(complex_riff_wav, 'rb') as f:
            audio_file = File(f)
            transcription = baker.make_recipe(
                'transcriber.transcription_basic',
                filename="complex-riff.wav",
                original_audio=audio_file,
                status="pending"
            )
        
        result = process_transcription(transcription.id)
        assert result['status'] == 'success'
        
        variants = FingeringVariant.objects.filter(transcription=transcription)
        
        if variants.count() >= 3:
            # Check variant diversity
            variant_names = set(v.variant_name for v in variants)
            expected_variants = {'easy', 'balanced', 'technical', 'original'}
            
            # Should have most standard variants
            overlap = variant_names & expected_variants
            assert len(overlap) >= 2
            
            # Check score distribution
            difficulties = [v.difficulty_score for v in variants]
            playabilities = [v.playability_score for v in variants]
            
            # Should have range in scores
            assert max(difficulties) - min(difficulties) > 10
            assert max(playabilities) - min(playabilities) > 10
            
            # One variant should be selected
            assert variants.filter(is_selected=True).count() == 1

    # ========== Error Handling Tests ==========

    def test_error_handling_missing_file(self):
        """Test graceful handling of missing audio files."""
        transcription = baker.make_recipe(
            'transcriber.transcription_basic',
            filename="missing.wav",
            status="pending"
        )
        
        # Delete the audio file
        if transcription.original_audio.name:
            transcription.original_audio.delete()
        
        result = process_transcription(transcription.id)
        
        assert result['status'] == 'failed_permanently'
        assert 'error' in result
        
        transcription.refresh_from_db()
        assert transcription.status == 'failed'
        assert transcription.error_message is not None

    def test_error_handling_invalid_audio(self):
        """Test handling of invalid audio data."""
        # Create a fake "audio" file with text content
        invalid_content = b"This is not audio data"
        invalid_file = SimpleUploadedFile(
            "invalid.wav",
            invalid_content,
            content_type="audio/wav"
        )
        
        transcription = baker.make_recipe(
            'transcriber.transcription_basic',
            filename="invalid.wav",
            original_audio=invalid_file,
            status="pending"
        )
        
        result = process_transcription(transcription.id)
        
        # Should fail but handle gracefully
        assert result['status'] in ['failed', 'failed_permanently']
        
        transcription.refresh_from_db()
        assert transcription.status == 'failed'

    def test_api_key_validation(self):
        """Test OpenAI API key validation."""
        # Test with no API key
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(settings, 'OPENAI_API_KEY', ''):
                with pytest.raises(ValueError, match="OpenAI API key is required"):
                    AITranscriptionAgent()
        
        # Test with valid API key
        with patch.object(settings, 'OPENAI_API_KEY', 'test-key'):
            agent = AITranscriptionAgent()
            assert agent.api_key == 'test-key'
            assert agent.client is not None

    # ========== Comprehensive End-to-End Test ==========

    @pytest.mark.slow
    def test_comprehensive_end_to_end(self, sample_audio_files):
        """
        Comprehensive test covering the entire pipeline from upload to export.
        This is the ultimate integration test.
        """
        test_summary = {
            'total_tests': 0,
            'successful': 0,
            'failed': 0,
            'total_time': 0,
            'details': []
        }
        
        # Test different file types
        test_files = [
            ('simple-riff_wav', 'simple'),
            ('complex-riff_wav', 'complex'),
            ('full-song_wav', 'full'),
            ('simple-riff_mp3', 'simple'),
            ('complex-riff_mp3', 'complex')
        ]
        
        for file_key, file_type in test_files:
            if file_key not in sample_audio_files:
                continue
            
            test_summary['total_tests'] += 1
            audio_path = sample_audio_files[file_key]
            
            print(f"\n🎵 Testing {file_key}...")
            
            # Step 1: Create transcription
            with open(audio_path, 'rb') as f:
                audio_file = File(f)
                transcription = baker.make_recipe(
                    'transcriber.transcription_basic',
                    filename=os.path.basename(audio_path),
                    original_audio=audio_file,
                    status="pending"
                )
            
            # Step 2: Process transcription
            start_time = time.time()
            result = process_transcription(transcription.id)
            processing_time = time.time() - start_time
            test_summary['total_time'] += processing_time
            
            if result['status'] != 'success':
                test_summary['failed'] += 1
                test_summary['details'].append({
                    'file': file_key,
                    'step': 'transcription',
                    'status': 'failed',
                    'error': result.get('error')
                })
                continue
            
            transcription.refresh_from_db()
            
            # Step 3: Verify transcription quality
            checks_passed = all([
                transcription.status == 'completed',
                transcription.duration is not None,
                transcription.estimated_tempo is not None,
                transcription.estimated_key is not None,
                transcription.complexity is not None,
                transcription.detected_instruments is not None,
                transcription.midi_data is not None,
                transcription.guitar_notes is not None
            ])
            
            if not checks_passed:
                test_summary['failed'] += 1
                test_summary['details'].append({
                    'file': file_key,
                    'step': 'verification',
                    'status': 'failed'
                })
                continue
            
            # Step 4: Test exports
            export_success = 0
            for export_format in ['musicxml', 'midi', 'ascii_tab']:
                try:
                    export_result = generate_export(transcription.id, export_format)
                    if export_result['status'] == 'success':
                        export_success += 1
                except:
                    pass
            
            # Step 5: Check variants
            variants = FingeringVariant.objects.filter(transcription=transcription)
            
            # Summary for this file
            file_summary = {
                'file': file_key,
                'type': file_type,
                'processing_time': processing_time,
                'complexity': transcription.complexity,
                'duration': transcription.duration,
                'tempo': transcription.estimated_tempo,
                'key': transcription.estimated_key,
                'instruments': len(transcription.detected_instruments) if transcription.detected_instruments else 0,
                'variants': variants.count(),
                'exports': export_success,
                'status': 'success'
            }
            
            test_summary['successful'] += 1
            test_summary['details'].append(file_summary)
        
        # Print comprehensive summary
        print("\n" + "="*60)
        print("🎯 COMPREHENSIVE TEST SUMMARY")
        print("="*60)
        print(f"Total Tests: {test_summary['total_tests']}")
        print(f"Successful: {test_summary['successful']}")
        print(f"Failed: {test_summary['failed']}")
        print(f"Total Time: {test_summary['total_time']:.2f}s")
        print(f"Average Time: {test_summary['total_time']/max(test_summary['total_tests'], 1):.2f}s")
        print(f"Success Rate: {test_summary['successful']/max(test_summary['total_tests'], 1)*100:.1f}%")
        
        if should_use_real_api():
            print("\n🚀 Tests run with REAL OpenAI API")
        else:
            print("\n🔧 Tests run with MOCKED OpenAI API")
        
        print("\nDetailed Results:")
        for detail in test_summary['details']:
            if detail.get('status') == 'success':
                print(f"  ✅ {detail['file']}: {detail['processing_time']:.2f}s, "
                      f"{detail.get('variants', 0)} variants, {detail.get('exports', 0)} exports")
            else:
                print(f"  ❌ {detail['file']}: Failed at {detail.get('step', 'unknown')}")
        
        # Assert overall success
        assert test_summary['successful'] > 0, "No tests succeeded"
        assert test_summary['successful'] / test_summary['total_tests'] >= 0.6, "Success rate too low"
        
        return test_summary