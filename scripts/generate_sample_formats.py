#!/usr/bin/env python3
"""
Script to generate sample audio files in various supported formats.
Converts existing WAV samples to MP3, FLAC, M4A, OGG, and AAC formats.
"""

import os
import sys
from pathlib import Path
from pydub import AudioSegment
from pydub.utils import which


def setup_django():
    """Setup Django environment for script."""
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'riffscribe.settings')
    
    import django
    django.setup()


def check_dependencies():
    """Check if required external tools are available."""
    dependencies = {
        'ffmpeg': 'Required for most audio format conversions',
        'ffprobe': 'Required for audio format detection',
    }
    
    missing = []
    for tool, description in dependencies.items():
        if not which(tool):
            missing.append(f"{tool}: {description}")
    
    if missing:
        print("❌ Missing dependencies:")
        for dep in missing:
            print(f"   - {dep}")
        print("\nOn macOS, install with: brew install ffmpeg")
        print("On Ubuntu/Debian, install with: sudo apt-get install ffmpeg")
        return False
    
    print("✅ All dependencies found")
    return True


def convert_audio_file(input_path: Path, output_path: Path, format_name: str):
    """Convert audio file to specified format."""
    try:
        # Load the audio file
        audio = AudioSegment.from_file(str(input_path))
        
        # Format-specific settings
        export_params = {}
        
        if format_name == 'mp3':
            export_params = {
                'format': 'mp3',
                'bitrate': '192k',
                'parameters': ['-q:a', '2']  # Good quality
            }
        elif format_name == 'flac':
            export_params = {
                'format': 'flac',
                'parameters': ['-compression_level', '5']  # Balanced compression
            }
        elif format_name == 'm4a':
            export_params = {
                'format': 'mp4',
                'codec': 'aac',
                'bitrate': '256k'
            }
        elif format_name == 'ogg':
            export_params = {
                'format': 'ogg',
                'codec': 'libvorbis',
                'parameters': ['-q:a', '6']  # Good quality
            }
        elif format_name == 'aac':
            export_params = {
                'format': 'adts',
                'codec': 'aac',
                'bitrate': '256k',
                'parameters': ['-profile:a', 'aac_low']
            }
        else:
            raise ValueError(f"Unsupported format: {format_name}")
        
        # Export the audio
        audio.export(str(output_path), **export_params)
        print(f"✅ Created {output_path.name}")
        return True
        
    except Exception as e:
        print(f"❌ Error converting {input_path.name} to {format_name}: {e}")
        return False


def generate_samples():
    """Generate sample files in all supported formats."""
    # Setup paths
    project_root = Path(__file__).parent.parent
    samples_dir = project_root / 'samples'
    
    # Ensure samples directory exists
    samples_dir.mkdir(exist_ok=True)
    
    # Define source files and target formats
    source_files = ['simple-riff.wav', 'complex-riff.wav']
    target_formats = ['mp3', 'flac', 'm4a', 'ogg', 'aac']
    
    print(f"📁 Working in: {samples_dir}")
    print(f"🎵 Source files: {source_files}")
    print(f"🔄 Target formats: {target_formats}")
    print()
    
    # Check if source files exist
    missing_sources = []
    for source_file in source_files:
        source_path = samples_dir / source_file
        if not source_path.exists():
            missing_sources.append(source_file)
    
    if missing_sources:
        print(f"❌ Missing source files: {missing_sources}")
        print("Please ensure the WAV sample files exist in the samples directory")
        return False
    
    # Convert each source file to each target format
    success_count = 0
    total_conversions = len(source_files) * len(target_formats)
    
    for source_file in source_files:
        print(f"\n🎧 Converting {source_file}...")
        source_path = samples_dir / source_file
        base_name = source_path.stem  # filename without extension
        
        for format_name in target_formats:
            output_filename = f"{base_name}.{format_name}"
            output_path = samples_dir / output_filename
            
            if convert_audio_file(source_path, output_path, format_name):
                success_count += 1
    
    # Report results
    print(f"\n📊 Conversion Results:")
    print(f"   ✅ Successful: {success_count}/{total_conversions}")
    print(f"   ❌ Failed: {total_conversions - success_count}/{total_conversions}")
    
    if success_count > 0:
        print(f"\n📁 Generated files are in: {samples_dir}")
        print("   (These files are gitignored but available for local testing)")
    
    return success_count == total_conversions


def main():
    """Main script execution."""
    print("🎵 RiffScribe Sample Audio Generator")
    print("=" * 40)
    
    # Check dependencies first
    if not check_dependencies():
        return 1
    
    # Setup Django environment
    setup_django()
    
    # Generate sample files
    if generate_samples():
        print("\n🎉 All sample files generated successfully!")
        return 0
    else:
        print("\n⚠️  Some conversions failed. Check the output above for details.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
