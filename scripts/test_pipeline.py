#!/usr/bin/env python
"""
Test the ML pipeline with sample audio files.
"""
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'riffscribe.settings')

import django
django.setup()

from transcriber.services.ml_pipeline import MLPipeline
from transcriber.services.tab_generator import TabGenerator
import json

def test_audio_file(audio_path):
    """Test the complete pipeline with an audio file."""
    print(f"\n🎸 Testing: {audio_path}")
    print("=" * 60)
    
    if not Path(audio_path).exists():
        print(f"❌ File not found: {audio_path}")
        return False
    
    try:
        # Initialize pipeline
        print("📊 Initializing ML pipeline...")
        pipeline = MLPipeline(use_gpu=False)
        
        # Analyze audio
        print("🎵 Analyzing audio...")
        analysis = pipeline.analyze_audio(audio_path)
        
        print(f"  Duration: {analysis['duration']:.2f} seconds")
        print(f"  Tempo: {analysis['tempo']:.1f} BPM")
        print(f"  Key: {analysis['key']}")
        print(f"  Complexity: {analysis['complexity']}")
        print(f"  Instruments: {', '.join(analysis['instruments'])}")
        
        # Transcribe
        print("\n🎼 Transcribing notes...")
        transcription = pipeline.transcribe(audio_path)
        print(f"  Detected {len(transcription['notes'])} notes")
        
        # Generate tabs
        print("\n🎸 Generating guitar tabs...")
        tab_gen = TabGenerator(
            transcription['notes'],
            analysis['tempo'],
            analysis.get('time_signature', '4/4')
        )
        
        tab_data = tab_gen.generate_optimized_tabs()
        print(f"  Generated {len(tab_data['measures'])} measures")
        print(f"  Techniques used: {tab_data['techniques_used']}")
        
        # Generate ASCII tab
        print("\n📝 ASCII Tab Preview:")
        print("-" * 60)
        ascii_tab = tab_gen.to_ascii_tab(measures_per_line=2)
        print(ascii_tab[:500] + "..." if len(ascii_tab) > 500 else ascii_tab)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function."""
    print("🎸 RiffScribe Pipeline Test")
    print("=" * 60)
    
    # Test with sample files
    samples_dir = Path(__file__).parent.parent / "samples"
    
    test_files = [
        samples_dir / "simple-riff.wav",
        samples_dir / "complex-riff.wav"
    ]
    
    results = []
    for audio_file in test_files:
        if audio_file.exists():
            success = test_audio_file(str(audio_file))
            results.append((audio_file.name, success))
        else:
            print(f"⚠️  Sample file not found: {audio_file}")
            results.append((audio_file.name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary:")
    for filename, success in results:
        status = "✅" if success else "❌"
        print(f"  {status} {filename}")
    
    all_passed = all(r[1] for r in results)
    if all_passed:
        print("\n🎉 All tests passed! Pipeline is working correctly.")
    else:
        print("\n⚠️  Some tests failed. Check the errors above.")

if __name__ == "__main__":
    main()