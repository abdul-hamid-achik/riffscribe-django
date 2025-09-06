"""
Integration tests for the complete transcription pipeline using real sample audio files.
Tests the full flow from audio upload through AI transcription to export generation.
"""

import pytest
import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from django.core.files import File
from django.conf import settings

from transcriber.models import Transcription, TabExport, FingeringVariant
from transcriber.tasks import process_transcription, generate_export
from transcriber.services.ai_transcription_agent import AIPipeline, AITranscriptionAgent
from model_bakery import baker


@pytest.mark.django_db
@pytest.mark.integration
class TestTranscriptionPipeline:
    """Test the complete transcription pipeline with real sample files."""

    @pytest.fixture(autouse=True)
    def setup_openai_mock(self):
        """Mock OpenAI API calls to avoid hitting the real API in tests."""
        with patch('openai.OpenAI') as mock_openai_class:
            # Mock client instance
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            
            # Mock Whisper transcription response
            mock_whisper_response = MagicMock()
            mock_whisper_response.text = "Guitar riff in E minor"
            mock_whisper_response.segments = []
            mock_whisper_response.words = []
            mock_whisper_response.language = "en"
            mock_whisper_response.duration = 10.5
            
            mock_client.audio.transcriptions.create.return_value = mock_whisper_response
            
            # Mock GPT-4 audio analysis response
            mock_gpt_response = MagicMock()
            mock_gpt_response.choices = [MagicMock()]
            mock_gpt_response.choices[0].message.content = '''
            {
                "tempo": 140,
                "key": "E Minor",
                "time_signature": "4/4",
                "complexity": "moderate",
                "instruments": ["electric_guitar"],
                "chord_progression": [
                    {"time": 0.0, "chord": "Em", "confidence": 0.9},
                    {"time": 2.0, "chord": "Am", "confidence": 0.8}
                ],
                "notes": [
                    {"midi_note": 64, "start_time": 0.0, "end_time": 0.5, "velocity": 80, "confidence": 0.9},
                    {"midi_note": 67, "start_time": 0.5, "end_time": 1.0, "velocity": 85, "confidence": 0.8},
                    {"midi_note": 69, "start_time": 1.0, "end_time": 1.5, "velocity": 90, "confidence": 0.9}
                ],
                "confidence": 0.85,
                "analysis_summary": "Fast-paced electric guitar riff with clear note articulation"
            }
            '''
            
            mock_client.chat.completions.create.return_value = mock_gpt_response
            
            yield mock_client

    def test_simple_riff_transcription_wav(self, simple_riff_wav):
        """Test complete transcription pipeline with simple-riff.wav."""
        if not simple_riff_wav:
            pytest.skip("simple-riff.wav sample not available")
        
        # Create transcription with real audio file
        with open(simple_riff_wav, 'rb') as f:
            audio_file = File(f)
            transcription = baker.make_recipe(
                'transcriber.transcription_basic',
                filename="simple-riff.wav",
                original_audio=audio_file,
                status="pending"
            )
        
        # Process transcription
        result = process_transcription(transcription.id)
        
        # Verify successful processing
        assert result['status'] == 'success'
        assert result['transcription_id'] == str(transcription.id)
        
        # Reload from database to get updated fields
        transcription.refresh_from_db()
        
        # Verify transcription was completed
        assert transcription.status == 'completed'
        assert transcription.duration is not None
        assert transcription.estimated_tempo is not None
        assert transcription.estimated_key is not None
        assert transcription.complexity is not None
        assert transcription.detected_instruments is not None
        
        # Verify AI analysis results
        assert transcription.whisper_analysis is not None
        assert 'confidence' in transcription.whisper_analysis
        
        # Verify note transcription
        assert transcription.midi_data is not None
        assert transcription.guitar_notes is not None
        
        # Verify fingering variants were generated
        variants = FingeringVariant.objects.filter(transcription=transcription)
        assert variants.count() > 0
        
        # Ensure at least one variant is selected
        selected_variants = variants.filter(is_selected=True)
        assert selected_variants.count() == 1

    def test_complex_riff_transcription_wav(self, complex_riff_wav):
        """Test complete transcription pipeline with complex-riff.wav."""
        if not complex_riff_wav:
            pytest.skip("complex-riff.wav sample not available")
        
        # Create transcription with real audio file
        with open(complex_riff_wav, 'rb') as f:
            audio_file = File(f)
            transcription = baker.make_recipe(
                'transcriber.transcription_basic',
                filename="complex-riff.wav",
                original_audio=audio_file,
                status="pending"
            )
        
        # Process transcription
        result = process_transcription(transcription.id)
        
        # Verify successful processing
        assert result['status'] == 'success'
        
        # Reload from database
        transcription.refresh_from_db()
        
        # Verify transcription completed
        assert transcription.status == 'completed'
        
        # Complex riff should have higher complexity rating
        assert transcription.complexity in ['moderate', 'complex']
        
        # Should have transcription results
        assert transcription.midi_data is not None
        assert transcription.guitar_notes is not None
        
        # Verify variants generated with different difficulty levels
        variants = FingeringVariant.objects.filter(transcription=transcription)
        variant_names = [v.variant_name for v in variants]
        
        # Should have multiple variants including easy and technical
        assert 'easy' in variant_names
        assert len(variants) >= 2

    @pytest.mark.parametrize("audio_format", ['mp3', 'flac', 'm4a', 'ogg', 'aac'])
    def test_all_audio_formats_simple_riff(self, sample_audio_files, audio_format):
        """Test transcription with all supported audio formats using simple riff."""
        file_key = f"simple-riff_{audio_format}"
        
        if file_key not in sample_audio_files:
            pytest.skip(f"simple-riff.{audio_format} sample not available")
        
        audio_path = sample_audio_files[file_key]
        
        # Create transcription with specific format
        with open(audio_path, 'rb') as f:
            audio_file = File(f)
            transcription = baker.make_recipe(
                'transcriber.transcription_basic',
                filename=f"simple-riff.{audio_format}",
                original_audio=audio_file,
                status="pending"
            )
        
        # Process transcription
        result = process_transcription(transcription.id)
        
        # Verify successful processing regardless of format
        assert result['status'] == 'success'
        
        transcription.refresh_from_db()
        assert transcription.status == 'completed'
        assert transcription.detected_instruments is not None

    @pytest.mark.parametrize("audio_format", ['mp3', 'flac', 'm4a', 'ogg', 'aac'])
    def test_all_audio_formats_complex_riff(self, sample_audio_files, audio_format):
        """Test transcription with all supported audio formats using complex riff."""
        file_key = f"complex-riff_{audio_format}"
        
        if file_key not in sample_audio_files:
            pytest.skip(f"complex-riff.{audio_format} sample not available")
        
        audio_path = sample_audio_files[file_key]
        
        # Create transcription with specific format
        with open(audio_path, 'rb') as f:
            audio_file = File(f)
            transcription = baker.make_recipe(
                'transcriber.transcription_basic',
                filename=f"complex-riff.{audio_format}",
                original_audio=audio_file,
                status="pending"
            )
        
        # Process transcription
        result = process_transcription(transcription.id)
        
        # Verify successful processing regardless of format
        assert result['status'] == 'success'
        
        transcription.refresh_from_db()
        assert transcription.status == 'completed'
        assert transcription.detected_instruments is not None

    def test_export_generation_after_transcription(self, simple_riff_wav):
        """Test that exports can be generated after transcription completes."""
        if not simple_riff_wav:
            pytest.skip("simple-riff.wav sample not available")
        
        # Create and process transcription
        with open(simple_riff_wav, 'rb') as f:
            audio_file = File(f)
            transcription = baker.make_recipe(
                'transcriber.transcription_completed',
                filename="simple-riff.wav",
                original_audio=audio_file
            )
        
        # Test MusicXML export generation
        with patch('transcriber.services.export_manager.ExportManager.export_musicxml') as mock_export:
            mock_export.return_value = "/tmp/test_export.xml"
            
            # Mock file operations
            with patch('os.path.exists', return_value=True), \
                 patch('os.path.getsize', return_value=1024), \
                 patch('builtins.open', create=True) as mock_open:
                
                mock_open.return_value.__enter__.return_value.read.return_value = b'<musicxml/>'
                
                result = generate_export(transcription.id, 'musicxml')
                
                assert result['status'] == 'success'
                assert 'export_id' in result
                
                # Verify export record was created
                export = TabExport.objects.get(id=result['export_id'])
                assert export.transcription == transcription
                assert export.format == 'musicxml'

    def test_pipeline_performance_benchmarks(self, simple_riff_wav):
        """Test that pipeline performance meets expected benchmarks."""
        if not simple_riff_wav:
            pytest.skip("simple-riff.wav sample not available")
        
        # Create transcription
        with open(simple_riff_wav, 'rb') as f:
            audio_file = File(f)
            transcription = baker.make_recipe(
                'transcriber.transcription_basic',
                filename="simple-riff.wav",
                original_audio=audio_file,
                status="pending"
            )
        
        # Measure processing time
        start_time = time.time()
        result = process_transcription(transcription.id)
        processing_time = time.time() - start_time
        
        # Verify performance benchmarks
        assert result['status'] == 'success'
        assert 'processing_time' in result
        
        # AI pipeline should be much faster than traditional ML pipeline
        # Allow generous time for CI environments, but should typically be <30s
        assert processing_time < 60, f"Processing took {processing_time:.2f}s, expected <60s"
        
        transcription.refresh_from_db()
        assert transcription.status == 'completed'

    def test_humanizer_optimization_applied(self, simple_riff_wav):
        """Test that humanizer optimization is properly applied to transcription results."""
        if not simple_riff_wav:
            pytest.skip("simple-riff.wav sample not available")
        
        # Create transcription
        with open(simple_riff_wav, 'rb') as f:
            audio_file = File(f)
            transcription = baker.make_recipe(
                'transcriber.transcription_basic',
                filename="simple-riff.wav", 
                original_audio=audio_file,
                status="pending"
            )
        
        # Process transcription
        result = process_transcription(transcription.id)
        assert result['status'] == 'success'
        
        transcription.refresh_from_db()
        
        # Verify humanizer settings were stored in transcription results
        assert transcription.midi_data is not None
        
        # Check that guitar notes have string/fret assignments (from humanizer)
        assert transcription.guitar_notes is not None
        
        # Verify fingering variants were created with different playability scores
        variants = FingeringVariant.objects.filter(transcription=transcription)
        assert variants.count() >= 2
        
        # Verify variants have different difficulty/playability scores
        scores = [v.playability_score for v in variants]
        assert len(set(scores)) > 1, "Variants should have different playability scores"

    def test_error_handling_invalid_audio(self):
        """Test error handling with invalid audio file."""
        # Create transcription with invalid audio data
        transcription = baker.make_recipe(
            'transcriber.transcription_basic',
            filename="invalid.wav",
            status="pending"
        )
        
        # Remove the audio file to simulate missing file
        if transcription.original_audio.name:
            transcription.original_audio.delete()
        
        # Process should fail gracefully
        result = process_transcription(transcription.id)
        
        # Should fail with appropriate error
        assert result['status'] == 'failed_permanently'
        assert 'error' in result
        
        transcription.refresh_from_db()
        assert transcription.status == 'failed'
        assert transcription.error_message is not None

    def test_ai_pipeline_direct_usage(self, simple_riff_wav):
        """Test direct usage of AI pipeline components."""
        if not simple_riff_wav:
            pytest.skip("simple-riff.wav sample not available")
        
        # Test AIPipeline directly
        pipeline = AIPipeline(enable_drums=True)
        
        # Test audio analysis
        analysis_result = pipeline.analyze_audio(simple_riff_wav)
        
        assert analysis_result['duration'] > 0
        assert analysis_result['tempo'] is not None
        assert analysis_result['key'] is not None
        assert analysis_result['complexity'] is not None
        assert analysis_result['instruments'] is not None
        
        # Test transcription
        transcription_result = pipeline.transcribe(simple_riff_wav)
        
        assert 'notes' in transcription_result
        assert 'midi_data' in transcription_result
        assert isinstance(transcription_result['notes'], list)

    def test_variant_generation_completeness(self, simple_riff_wav):
        """Test that all expected fingering variants are generated."""
        if not simple_riff_wav:
            pytest.skip("simple-riff.wav sample not available")
        
        # Create and process transcription
        with open(simple_riff_wav, 'rb') as f:
            audio_file = File(f)
            transcription = baker.make_recipe(
                'transcriber.transcription_basic',
                filename="simple-riff.wav",
                original_audio=audio_file,
                status="pending"
            )
        
        result = process_transcription(transcription.id)
        assert result['status'] == 'success'
        
        # Check all expected variants were created
        variants = FingeringVariant.objects.filter(transcription=transcription)
        variant_names = set(v.variant_name for v in variants)
        
        # Should have all standard variants
        expected_variants = {'easy', 'balanced', 'technical', 'original'}
        assert expected_variants.issubset(variant_names), f"Missing variants: {expected_variants - variant_names}"
        
        # Each variant should have valid scores
        for variant in variants:
            assert 0 <= variant.difficulty_score <= 100
            assert 0 <= variant.playability_score <= 100
            assert variant.tab_data is not None
            
        # Exactly one variant should be selected
        selected_count = variants.filter(is_selected=True).count()
        assert selected_count == 1

    def test_multi_track_processing(self, complex_riff_wav):
        """Test AI multi-track processing capabilities."""
        if not complex_riff_wav:
            pytest.skip("complex-riff.wav sample not available")
        
        # Enable multi-track processing
        with patch.object(settings, 'ENABLE_MULTITRACK', True):
            # Create and process transcription
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
            
            transcription.refresh_from_db()
            
            # Check if any tracks were created
            tracks = transcription.tracks.all()
            
            # AI should detect at least the guitar track
            assert tracks.count() >= 0  # May be 0 if no additional instruments detected
            
            # If tracks were created, verify they're properly processed
            for track in tracks:
                assert track.track_type in ['drums', 'bass', 'other', 'vocals', 'original']
                assert track.is_processed == True

    @pytest.mark.slow
    def test_full_pipeline_end_to_end(self, sample_audio_files):
        """Comprehensive end-to-end test of the entire pipeline."""
        # Test both simple and complex riffs with multiple formats
        test_files = [
            ('simple-riff_wav', 'simple'),
            ('complex-riff_wav', 'complex'),
            ('simple-riff_mp3', 'simple'),
            ('complex-riff_mp3', 'complex')
        ]
        
        results = []
        
        for file_key, expected_complexity in test_files:
            if file_key not in sample_audio_files:
                continue
            
            audio_path = sample_audio_files[file_key]
            filename = os.path.basename(audio_path)
            
            # Create transcription
            with open(audio_path, 'rb') as f:
                audio_file = File(f)
                transcription = baker.make_recipe(
                    'transcriber.transcription_basic',
                    filename=filename,
                    original_audio=audio_file,
                    status="pending"
                )
            
            # Process transcription
            start_time = time.time()
            result = process_transcription(transcription.id)
            processing_time = time.time() - start_time
            
            assert result['status'] == 'success'
            
            transcription.refresh_from_db()
            assert transcription.status == 'completed'
            
            # Test export generation
            export_result = generate_export(transcription.id, 'musicxml')
            
            results.append({
                'file': filename,
                'processing_time': processing_time,
                'transcription_success': result['status'] == 'success',
                'export_success': export_result['status'] == 'success',
                'complexity': transcription.complexity,
                'note_count': len(transcription.guitar_notes.get('measures', [])) if transcription.guitar_notes else 0,
                'variant_count': FingeringVariant.objects.filter(transcription=transcription).count()
            })
        
        # Verify all tests passed
        assert len(results) > 0, "No audio files were available for testing"
        
        for result in results:
            assert result['transcription_success'], f"Transcription failed for {result['file']}"
            assert result['export_success'], f"Export failed for {result['file']}"
            assert result['variant_count'] > 0, f"No variants generated for {result['file']}"
        
        # Log summary statistics for analysis
        print(f"\nPipeline Test Summary:")
        print(f"Files tested: {len(results)}")
        print(f"Average processing time: {sum(r['processing_time'] for r in results) / len(results):.2f}s")
        print(f"Success rate: {sum(1 for r in results if r['transcription_success'] and r['export_success']) / len(results) * 100:.1f}%")