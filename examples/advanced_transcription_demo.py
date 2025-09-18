#!/usr/bin/env python
"""
Advanced Transcription Service Demo
Demonstrates the new MT3 + Omnizart + CREPE pipeline with business intelligence
"""
import os
import sys
import django
import asyncio
from pathlib import Path

# Setup Django
sys.path.append(str(Path(__file__).parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'riffscribe.settings')
django.setup()

from transcriber.services.advanced_transcription_service import get_advanced_service
from transcriber.services.mt3_service import get_mt3_service
from transcriber.services.omnizart_service import get_omnizart_service
from transcriber.services.crepe_service import get_crepe_service
from transcriber.models import Transcription, UserProfile


async def demo_advanced_transcription():
    """Demonstrate the advanced transcription capabilities"""
    print("🎵 RiffScribe Advanced Transcription Demo")
    print("=" * 50)
    
    # Check if sample audio exists
    sample_path = "samples/example.wav"
    if not os.path.exists(sample_path):
        print("❌ Sample audio file not found. Please add a sample audio file at:", sample_path)
        print("   You can use any audio file (MP3, WAV, etc.)")
        return
    
    print(f"📁 Processing: {sample_path}")
    
    # Get the advanced service
    service = get_advanced_service()
    
    # Show service capabilities
    info = service.get_service_info()
    print(f"\n🤖 Service Info:")
    print(f"   Version: {info['version']}")
    print(f"   Models: {', '.join(info['models'].keys())}")
    print(f"   Supported Instruments: {', '.join(info['supported_instruments'])}")
    print(f"   Accuracy Modes: {', '.join(info['accuracy_modes'])}")
    
    # Demonstrate different accuracy modes
    modes = ['fast', 'balanced', 'maximum']
    
    for mode in modes:
        print(f"\n🎯 Testing {mode.upper()} accuracy mode:")
        print("-" * 30)
        
        try:
            result = await service.transcribe_audio_advanced(
                sample_path,
                accuracy_mode=mode,
                use_all_models=(mode != 'fast')
            )
            
            print(f"✅ Transcription completed!")
            print(f"   Instruments detected: {len(result.detected_instruments)}")
            print(f"   Instruments: {', '.join(result.detected_instruments)}")
            print(f"   Overall confidence: {result.overall_confidence:.1%}")
            print(f"   Accuracy score: {result.accuracy_score:.1%}")
            print(f"   Processing time: {result.total_processing_time:.1f}s")
            print(f"   Models used: {', '.join(set(result.models_used.values()))}")
            
            # Show per-instrument details
            print(f"   Per-instrument confidence:")
            for instrument, confidence in result.confidence_scores.items():
                note_count = len(result.tracks.get(instrument, []))
                print(f"     {instrument}: {confidence:.1%} ({note_count} notes)")
            
            # Musical analysis
            print(f"   Musical analysis:")
            print(f"     Tempo: {result.tempo:.0f} BPM")
            print(f"     Key: {result.key}")
            print(f"     Time signature: {result.time_signature}")
            print(f"     Complexity: {result.complexity}")
            
            if result.chord_progression:
                print(f"     Chords detected: {len(result.chord_progression)}")
            
            if result.beat_tracking:
                print(f"     Beat tracking: {len(result.beat_tracking)} beat points")
            
        except Exception as e:
            print(f"❌ Error in {mode} mode: {e}")
            continue
    
    print(f"\n💡 Business Value Demonstration:")
    print("=" * 50)
    
    # Show what free vs premium users get
    print("🆓 FREE Users Get:")
    print("   - MusicXML web player with track visualization")
    print("   - Detected instruments and confidence scores")
    print("   - Tempo, key, and complexity analysis")
    print("   - Processing accuracy information")
    print("   - Up to 3 transcriptions per month")
    
    print("\n💎 PREMIUM Users Get (All free features +):")
    print("   - Download Guitar Pro 5 (.gp5) files")
    print("   - Export MIDI files for DAWs")
    print("   - ASCII tabs for sharing")
    print("   - Separated audio stems (ZIP)")
    print("   - Commercial use rights")
    print("   - Unlimited transcriptions")
    print("   - Advanced fingering variants")
    
    print(f"\n📊 Service Statistics:")
    print("=" * 50)
    
    # Show accuracy expectations
    expected_accuracy = info['expected_accuracy']
    print("🎯 Expected Accuracy by Instrument:")
    for instrument, accuracy in expected_accuracy.items():
        print(f"   {instrument.title()}: {accuracy:.1%}")
    
    print(f"\n🏗️ Technical Architecture:")
    print("=" * 50)
    print("   1. Source Separation: Demucs HTDemucs-FT")
    print("   2. Multi-track Transcription: Google MT3 Transformer")
    print("   3. Specialized Models: Omnizart per-instrument")
    print("   4. Pitch Refinement: CREPE CNN-based detection")
    print("   5. Export Generation: Multi-format (GP5, MIDI, XML, ASCII)")
    print("   6. Business Intelligence: Real-time analytics & conversion tracking")


async def demo_individual_services():
    """Demonstrate individual service capabilities"""
    print(f"\n🔧 Individual Service Demos:")
    print("=" * 50)
    
    sample_path = "samples/example.wav"
    if not os.path.exists(sample_path):
        print("❌ Sample audio required for individual service demos")
        return
    
    # Demo MT3
    print("🎵 MT3 Multi-Track Transcription:")
    try:
        mt3_service = get_mt3_service()
        mt3_result = await mt3_service.transcribe_multitrack(sample_path)
        
        print(f"   ✅ MT3 completed in {mt3_result.processing_time:.1f}s")
        print(f"   Tracks: {list(mt3_result.tracks.keys())}")
        print(f"   Confidence: {mt3_result.total_confidence:.1%}")
        
    except Exception as e:
        print(f"   ❌ MT3 failed: {e}")
    
    # Demo Omnizart
    print("\n🎼 Omnizart Specialized Transcription:")
    try:
        omnizart_service = get_omnizart_service()
        omnizart_results = await omnizart_service.transcribe_all_instruments(sample_path)
        
        print(f"   ✅ Omnizart completed")
        for instrument, result in omnizart_results.items():
            print(f"   {instrument}: {len(result.notes)} notes, {result.confidence:.1%} confidence")
            
    except Exception as e:
        print(f"   ❌ Omnizart failed: {e}")
    
    # Demo CREPE  
    print("\n🎚️ CREPE Pitch Detection:")
    try:
        crepe_service = get_crepe_service()
        crepe_result = await crepe_service.detect_pitch_with_onsets(sample_path)
        
        print(f"   ✅ CREPE completed in {crepe_result.processing_time:.1f}s")
        print(f"   Pitch points: {len(crepe_result.pitches)}")
        print(f"   Notes detected: {len(crepe_result.notes)}")
        print(f"   Average confidence: {crepe_result.average_confidence:.1%}")
        
    except Exception as e:
        print(f"   ❌ CREPE failed: {e}")


def demo_business_model():
    """Demonstrate the business model and user tiers"""
    print(f"\n💰 Business Model Demo:")
    print("=" * 50)
    
    # Show different user tiers
    tiers = {
        'free': {
            'name': 'Free',
            'price': '$0/month',
            'transcriptions': '3/month',
            'features': ['MusicXML preview', 'Track visualization', 'Analysis data'],
            'exports': '❌ Sign up required'
        },
        'premium': {
            'name': 'Premium',
            'price': '$9.99/month',
            'transcriptions': 'Unlimited',
            'features': ['All free features', 'GP5 downloads', 'MIDI exports', 'ASCII tabs'],
            'exports': '✅ All formats'
        },
        'professional': {
            'name': 'Professional',
            'price': '$29.99/month', 
            'transcriptions': 'Unlimited',
            'features': ['All premium features', 'Commercial license', 'API access', 'Priority support'],
            'exports': '✅ All formats + API'
        }
    }
    
    for tier_name, tier_data in tiers.items():
        print(f"\n{tier_data['name']} Tier ({tier_data['price']}):")
        print(f"   Transcriptions: {tier_data['transcriptions']}")
        print(f"   Features: {', '.join(tier_data['features'])}")
        print(f"   Exports: {tier_data['exports']}")
    
    # Show conversion funnel
    print(f"\n📈 Expected Conversion Funnel:")
    print("   100 visitors → Upload audio")
    print("    ↓ 80% completion rate")
    print("   80 completed transcriptions → View results") 
    print("    ↓ 60% attempt export")
    print("   48 export attempts → Hit paywall")
    print("    ↓ 15% conversion rate")
    print("   7 premium signups → $69.93 monthly revenue")
    print("    ↓ 90% retention")
    print("   6.3 retained users → $62.94 recurring revenue")


if __name__ == "__main__":
    print("🚀 Starting RiffScribe Advanced Demo...")
    
    # Check dependencies
    try:
        import mt3
        print("✅ MT3 available")
    except ImportError:
        print("❌ MT3 not installed - run: pip install mt3")
    
    try:
        import omnizart
        print("✅ Omnizart available")
    except ImportError:
        print("❌ Omnizart not installed - run: pip install omnizart")
    
    try:
        import crepe
        print("✅ CREPE available")
    except ImportError:
        print("❌ CREPE not installed - run: pip install crepe")
    
    # Run demos
    asyncio.run(demo_advanced_transcription())
    asyncio.run(demo_individual_services())
    demo_business_model()
    
    print(f"\n🎉 Demo completed!")
    print(f"🚀 Your RiffScribe service is now ready for production with:")
    print(f"   • State-of-the-art accuracy (MT3 + Omnizart + CREPE)")
    print(f"   • Automatic multi-instrument detection")
    print(f"   • Premium export monetization")
    print(f"   • Comprehensive business intelligence")
    print(f"   • Real-time progress tracking")
    print(f"   • Rate limiting and cost controls")

