#!/usr/bin/env python
"""
Download and setup ML models for RiffScribe.
This script downloads the required models for audio transcription.
"""
import os
import sys
import subprocess
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

def download_basic_pitch():
    """Download basic-pitch model."""
    print("📦 Installing basic-pitch...")
    try:
        subprocess.run(["pip", "install", "basic-pitch"], check=True)
        
        # Test import
        import basic_pitch
        print("✅ Basic-pitch installed successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to install basic-pitch: {e}")
        print("   Try: pip install basic-pitch")
        return False

def download_crepe():
    """Download CREPE model."""
    print("📦 Installing CREPE...")
    try:
        subprocess.run(["pip", "install", "crepe"], check=True)
        
        # Download model weights by importing
        import crepe
        print("✅ CREPE installed successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to install CREPE: {e}")
        print("   Try: pip install crepe")
        return False

def setup_demucs():
    """Setup Demucs for source separation."""
    print("📦 Setting up Demucs...")
    print("   Note: Demucs requires manual installation")
    print("   Run: pip install -U git+https://github.com/facebookresearch/demucs#egg=demucs")
    print("   Or use Spleeter as alternative: pip install spleeter")
    return True

def download_spleeter():
    """Download Spleeter as alternative to Demucs."""
    print("📦 Installing Spleeter (alternative to Demucs)...")
    try:
        subprocess.run(["pip", "install", "spleeter"], check=True)
        print("✅ Spleeter installed successfully")
        return True
    except Exception as e:
        print(f"⚠️  Failed to install Spleeter: {e}")
        return False

def test_models():
    """Test that models can be imported."""
    print("\n🧪 Testing model imports...")
    
    successes = []
    failures = []
    
    # Test librosa (should always work)
    try:
        import librosa
        successes.append("librosa")
    except:
        failures.append("librosa")
    
    # Test torch
    try:
        import torch
        import torchaudio
        successes.append("torch/torchaudio")
    except:
        failures.append("torch/torchaudio")
    
    # Test music21
    try:
        import music21
        successes.append("music21")
    except:
        failures.append("music21")
    
    # Test optional models
    try:
        import basic_pitch
        successes.append("basic-pitch")
    except:
        print("   ⚠️  basic-pitch not installed (optional)")
    
    try:
        import crepe
        successes.append("crepe")
    except:
        print("   ⚠️  crepe not installed (optional)")
    
    try:
        import spleeter
        successes.append("spleeter")
    except:
        print("   ⚠️  spleeter not installed (optional)")
    
    print(f"\n✅ Successfully loaded: {', '.join(successes)}")
    if failures:
        print(f"❌ Failed to load: {', '.join(failures)}")
        return False
    return True

def main():
    """Main function to download all models."""
    print("🎸 RiffScribe Model Setup")
    print("=" * 50)
    
    # Check if ml_models directory exists
    ml_models_dir = Path(__file__).parent.parent / "ml_models"
    ml_models_dir.mkdir(exist_ok=True)
    
    print(f"📁 Model directory: {ml_models_dir}")
    
    # Core dependencies should already be installed
    print("\n📋 Checking core dependencies...")
    test_models()
    
    # Optional: Install advanced models
    print("\n📥 Installing optional advanced models...")
    print("These models provide better accuracy but are not required.\n")
    
    response = input("Install basic-pitch for polyphonic transcription? (y/n): ")
    if response.lower() == 'y':
        download_basic_pitch()
    
    response = input("Install CREPE for monophonic pitch detection? (y/n): ")
    if response.lower() == 'y':
        download_crepe()
    
    response = input("Install Spleeter for source separation? (y/n): ")
    if response.lower() == 'y':
        download_spleeter()
    
    print("\n" + "=" * 50)
    print("Setup information for Demucs (advanced source separation):")
    setup_demucs()
    
    print("\n" + "=" * 50)
    print("🎉 Model setup complete!")
    print("\nYour system will work with basic librosa transcription.")
    print("Advanced models will be used if available for better accuracy.")
    
    # Final test
    print("\n🧪 Final system test...")
    if test_models():
        print("✅ System ready for audio transcription!")
    else:
        print("⚠️  System will work but some features may be limited.")

if __name__ == "__main__":
    main()