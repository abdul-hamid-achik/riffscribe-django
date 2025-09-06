#!/usr/bin/env python3
"""
Standalone script to test the transcription pipeline with sample audio files.
This script tests the core AI transcription components without requiring Django/database setup.

Usage:
    python test_samples_standalone.py
    python test_samples_standalone.py --format wav
    python test_samples_standalone.py --riff simple
"""

import os
import sys
import time
import asyncio
import argparse
from pathlib import Path
from unittest.mock import patch, MagicMock
import json

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set up minimal Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'riffscribe.settings')
import django
django.setup()

# Import transcription components
from transcriber.services.ai_transcription_agent import AIPipeline, AITranscriptionAgent


class SampleTester:
    """Test the transcription pipeline with sample audio files."""
    
    def __init__(self, samples_dir=None):
        self.samples_dir = Path(samples_dir or project_root / 'samples')
        self.results = []
        
        # Mock OpenAI to avoid API calls
        self.setup_openai_mock()
    
    def setup_openai_mock(self):
        """Set up OpenAI mocks for testing."""
        patcher = patch('openai.OpenAI')
        mock_openai_class = patcher.start()
        
        # Mock client instance
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        # Mock Whisper transcription response
        mock_whisper_response = MagicMock()
        mock_whisper_response.text = "Guitar riff with clear note articulation"
        mock_whisper_response.segments = []
        mock_whisper_response.words = []
        mock_whisper_response.language = "en"
        mock_whisper_response.duration = 10.0
        
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
                {"time": 2.0, "chord": "Am", "confidence": 0.8},
                {"time": 4.0, "chord": "C", "confidence": 0.85},
                {"time": 6.0, "chord": "G", "confidence": 0.9}
            ],
            "notes": [
                {"midi_note": 64, "start_time": 0.0, "end_time": 0.25, "velocity": 80, "confidence": 0.9},
                {"midi_note": 67, "start_time": 0.25, "end_time": 0.5, "velocity": 85, "confidence": 0.8},
                {"midi_note": 69, "start_time": 0.5, "end_time": 0.75, "velocity": 90, "confidence": 0.9},
                {"midi_note": 71, "start_time": 0.75, "end_time": 1.0, "velocity": 88, "confidence": 0.85},
                {"midi_note": 67, "start_time": 1.0, "end_time": 1.25, "velocity": 82, "confidence": 0.8},
                {"midi_note": 64, "start_time": 1.25, "end_time": 1.5, "velocity": 85, "confidence": 0.9}
            ],
            "confidence": 0.85,
            "analysis_summary": "Fast-paced electric guitar riff in E minor with clear chord progression"
        }
        '''
        
        mock_client.chat.completions.create.return_value = mock_gpt_response
        
        self.openai_patcher = patcher
    
    def find_sample_files(self, riff_type=None, audio_format=None):
        """Find available sample files."""
        if not self.samples_dir.exists():
            print(f"Samples directory not found: {self.samples_dir}")
            return []
        
        files = []
        riff_patterns = [riff_type] if riff_type else ['simple-riff', 'complex-riff']
        format_patterns = [audio_format] if audio_format else ['wav', 'mp3', 'flac', 'm4a', 'ogg', 'aac']
        
        for riff in riff_patterns:
            for fmt in format_patterns:
                file_path = self.samples_dir / f"{riff}.{fmt}"
                if file_path.exists():
                    files.append(file_path)
        
        return files
    
    async def test_ai_agent_direct(self, audio_path):
        """Test AI transcription agent directly."""
        print(f"\n=== Testing AI Agent with {audio_path.name} ===")
        
        try:
            # Test AI transcription agent
            agent = AITranscriptionAgent()
            
            start_time = time.time()
            ai_result = await agent.transcribe_audio(str(audio_path))
            processing_time = time.time() - start_time
            
            # Test humanizer optimization
            optimized_result = agent.optimize_with_humanizer(
                ai_result,
                tuning="standard",
                difficulty="balanced"
            )
            
            result = {
                'file': audio_path.name,
                'success': True,
                'processing_time': processing_time,
                'ai_analysis': {
                    'tempo': ai_result.tempo,
                    'key': ai_result.key,
                    'complexity': ai_result.complexity,
                    'instruments': ai_result.instruments,
                    'confidence': ai_result.confidence
                },
                'notes_detected': len(ai_result.notes),
                'notes_optimized': len(optimized_result.get('optimized_notes', [])),
                'humanizer_applied': 'humanizer_settings' in optimized_result
            }
            
            print(f"✓ Success: {processing_time:.2f}s")
            print(f"  Tempo: {ai_result.tempo} BPM")
            print(f"  Key: {ai_result.key}")
            print(f"  Complexity: {ai_result.complexity}")
            print(f"  Notes detected: {len(ai_result.notes)}")
            print(f"  Notes optimized: {len(optimized_result.get('optimized_notes', []))}")
            
            return result
            
        except Exception as e:
            print(f"✗ Error: {str(e)}")
            return {
                'file': audio_path.name,
                'success': False,
                'error': str(e),
                'processing_time': 0
            }
    
    def test_pipeline_analysis(self, audio_path):
        """Test AI pipeline analysis capabilities."""
        print(f"\n=== Testing AI Pipeline Analysis with {audio_path.name} ===")
        
        try:
            pipeline = AIPipeline(enable_drums=True)
            
            start_time = time.time()
            
            # Test audio analysis
            analysis_result = pipeline.analyze_audio(str(audio_path))
            analysis_time = time.time() - start_time
            
            # Test transcription
            transcription_start = time.time()
            transcription_result = pipeline.transcribe(str(audio_path))
            transcription_time = time.time() - transcription_start
            
            result = {
                'file': audio_path.name,
                'success': True,
                'analysis_time': analysis_time,
                'transcription_time': transcription_time,
                'total_time': analysis_time + transcription_time,
                'analysis': {
                    'duration': analysis_result.get('duration'),
                    'tempo': analysis_result.get('tempo'),
                    'key': analysis_result.get('key'),
                    'complexity': analysis_result.get('complexity'),
                    'instruments': analysis_result.get('instruments')
                },
                'transcription': {
                    'notes_count': len(transcription_result.get('notes', [])),
                    'has_midi_data': 'midi_data' in transcription_result,
                    'has_chord_data': len(transcription_result.get('chord_data', [])) > 0
                }
            }
            
            print(f"✓ Analysis: {analysis_time:.2f}s")
            print(f"  Duration: {analysis_result.get('duration', 'N/A')}s")
            print(f"  Tempo: {analysis_result.get('tempo', 'N/A')} BPM")
            print(f"  Key: {analysis_result.get('key', 'N/A')}")
            print(f"  Instruments: {analysis_result.get('instruments', [])}")
            
            print(f"✓ Transcription: {transcription_time:.2f}s")
            print(f"  Notes: {len(transcription_result.get('notes', []))}")
            print(f"  MIDI data: {'Yes' if transcription_result.get('midi_data') else 'No'}")
            
            return result
            
        except Exception as e:
            print(f"✗ Error: {str(e)}")
            return {
                'file': audio_path.name,
                'success': False,
                'error': str(e)
            }
    
    async def run_ai_tests(self, files):
        """Run AI transcription tests on all files."""
        print(f"\n{'='*60}")
        print(f"TESTING AI TRANSCRIPTION AGENT")
        print(f"{'='*60}")
        
        ai_results = []
        for audio_path in files:
            result = await self.test_ai_agent_direct(audio_path)
            ai_results.append(result)
            
        return ai_results
    
    def run_pipeline_tests(self, files):
        """Run pipeline tests on all files."""
        print(f"\n{'='*60}")
        print(f"TESTING AI PIPELINE")
        print(f"{'='*60}")
        
        pipeline_results = []
        for audio_path in files:
            result = self.test_pipeline_analysis(audio_path)
            pipeline_results.append(result)
            
        return pipeline_results
    
    def print_summary(self, ai_results, pipeline_results):
        """Print test summary."""
        print(f"\n{'='*60}")
        print(f"TEST SUMMARY")
        print(f"{'='*60}")
        
        all_results = ai_results + pipeline_results
        successful = [r for r in all_results if r.get('success', False)]
        failed = [r for r in all_results if not r.get('success', False)]
        
        print(f"Total tests: {len(all_results)}")
        print(f"Successful: {len(successful)}")
        print(f"Failed: {len(failed)}")
        print(f"Success rate: {len(successful)/len(all_results)*100:.1f}%" if all_results else "0%")
        
        if successful:
            avg_time = sum(r.get('processing_time', r.get('total_time', 0)) for r in successful) / len(successful)
            print(f"Average processing time: {avg_time:.2f}s")
        
        if failed:
            print(f"\nFailed tests:")
            for result in failed:
                print(f"  ✗ {result['file']}: {result.get('error', 'Unknown error')}")
        
        # Detailed analysis for AI results
        ai_successful = [r for r in ai_results if r.get('success', False)]
        if ai_successful:
            print(f"\nAI Transcription Details:")
            for result in ai_successful:
                print(f"  {result['file']}:")
                print(f"    Time: {result['processing_time']:.2f}s")
                if 'ai_analysis' in result:
                    analysis = result['ai_analysis']
                    print(f"    Tempo: {analysis.get('tempo', 'N/A')} BPM")
                    print(f"    Key: {analysis.get('key', 'N/A')}")
                    print(f"    Notes: {result.get('notes_detected', 0)} → {result.get('notes_optimized', 0)}")
        
        return len(failed) == 0
    
    def cleanup(self):
        """Clean up mocks."""
        if hasattr(self, 'openai_patcher'):
            self.openai_patcher.stop()


async def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description='Test transcription pipeline with sample audio files')
    parser.add_argument('--format', choices=['wav', 'mp3', 'flac', 'm4a', 'ogg', 'aac'], 
                       help='Test only specific audio format')
    parser.add_argument('--riff', choices=['simple-riff', 'complex-riff'], 
                       help='Test only specific riff type')
    parser.add_argument('--samples-dir', type=str, 
                       help='Path to samples directory (default: ./samples)')
    
    args = parser.parse_args()
    
    # Initialize tester
    tester = SampleTester(samples_dir=args.samples_dir)
    
    try:
        # Find sample files
        files = tester.find_sample_files(riff_type=args.riff, audio_format=args.format)
        
        if not files:
            print("No sample files found!")
            print(f"Looking in: {tester.samples_dir}")
            if args.format:
                print(f"Format filter: {args.format}")
            if args.riff:
                print(f"Riff filter: {args.riff}")
            return False
        
        print(f"Found {len(files)} sample files to test:")
        for f in files:
            print(f"  - {f.name}")
        
        # Run tests
        ai_results = await tester.run_ai_tests(files)
        pipeline_results = tester.run_pipeline_tests(files)
        
        # Print summary
        success = tester.print_summary(ai_results, pipeline_results)
        
        return success
        
    finally:
        tester.cleanup()


if __name__ == '__main__':
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Test failed with error: {e}")
        sys.exit(1)