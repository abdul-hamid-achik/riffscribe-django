"""
Tests for drum transcription functionality.
"""

import pytest
import numpy as np
import tempfile
import os
from django.test import TestCase
from unittest.mock import Mock, patch, MagicMock
from transcriber.drum_transcriber import DrumTranscriber, DrumHit


class DrumTranscriberTestCase(TestCase):
    """Test drum transcription functionality"""
    
    def setUp(self):
        self.drum_transcriber = DrumTranscriber()
        
    def test_drum_hit_creation(self):
        """Test DrumHit dataclass creation"""
        hit = DrumHit(
            time=1.5,
            drum_type='kick',
            velocity=0.8,
            confidence=0.9
        )
        
        self.assertEqual(hit.time, 1.5)
        self.assertEqual(hit.drum_type, 'kick')
        self.assertEqual(hit.velocity, 0.8)
        self.assertEqual(hit.confidence, 0.9)
    
    def test_drum_frequency_ranges(self):
        """Test drum frequency range definitions"""
        # Check that frequency ranges are defined for all main drums
        expected_drums = ['kick', 'snare', 'hihat', 'crash', 'ride']
        
        for drum in expected_drums:
            self.assertIn(drum, DrumTranscriber.DRUM_FREQ_RANGES)
            low, high = DrumTranscriber.DRUM_FREQ_RANGES[drum]
            self.assertLess(low, high)
            self.assertGreater(low, 0)
    
    def test_drum_midi_mapping(self):
        """Test MIDI note mappings for drums"""
        # Standard General MIDI drum map
        expected_mappings = {
            'kick': 36,      # C1
            'snare': 38,     # D1
            'hihat': 42,     # F#1
            'crash': 49,     # C#2
            'ride': 51,      # D#2
        }
        
        for drum, midi_note in expected_mappings.items():
            self.assertEqual(
                DrumTranscriber.DRUM_MIDI_MAP.get(drum),
                midi_note
            )
    
    @patch('librosa.load')
    @patch('librosa.beat.beat_track')
    @patch('librosa.onset.onset_detect')
    def test_transcribe_basic(self, mock_onset, mock_beat, mock_load):
        """Test basic transcription workflow"""
        # Mock audio data
        sample_rate = 22050
        duration = 4.0  # 4 seconds
        samples = int(sample_rate * duration)
        audio = np.random.randn(samples)
        
        mock_load.return_value = (audio, sample_rate)
        mock_beat.return_value = (120.0, np.array([0, 22050, 44100, 66150]))
        mock_onset.return_value = np.array([0, 5512, 11025, 16537])
        
        # Create temp audio file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            # Run transcription
            result = self.drum_transcriber.transcribe(temp_path)
            
            # Check structure
            self.assertIn('tempo', result)
            self.assertIn('beats', result)
            self.assertIn('drum_hits', result)
            self.assertIn('patterns', result)
            self.assertIn('notation', result)
            self.assertIn('measures', result)
            
            # Check tempo
            self.assertEqual(result['tempo'], 120.0)
            
            # Check that methods were called
            mock_load.assert_called_once_with(temp_path, sr=sample_rate)
            mock_beat.assert_called_once()
            mock_onset.assert_called_once()
            
        finally:
            os.unlink(temp_path)
    
    def test_identify_drum_type(self):
        """Test drum type identification from spectrum"""
        # Create mock spectrum with energy in kick frequency range
        freqs = np.linspace(0, 11025, 513)  # Nyquist frequency for 22050 Hz
        spectrum = np.zeros(513)
        
        # Add energy in kick drum range (20-100 Hz)
        kick_mask = (freqs >= 20) & (freqs <= 100)
        spectrum[kick_mask] = 1.0
        
        drum_type, confidence = self.drum_transcriber._identify_drum_type(
            spectrum, freqs
        )
        
        self.assertEqual(drum_type, 'kick')
        self.assertGreater(confidence, 0.5)
    
    def test_calculate_velocity(self):
        """Test velocity calculation from audio"""
        # Create audio with known amplitude
        sample_rate = 22050
        audio = np.ones(sample_rate) * 0.5  # Constant amplitude
        
        frame = 100
        velocity = self.drum_transcriber._calculate_velocity(
            audio, frame, sample_rate
        )
        
        self.assertGreaterEqual(velocity, 0)
        self.assertLessEqual(velocity, 1)
    
    def test_detect_patterns(self):
        """Test drum pattern detection"""
        # Create mock drum hits for basic rock pattern
        drum_hits = [
            DrumHit(0.0, 'kick', 0.8, 0.9),      # Beat 1
            DrumHit(0.5, 'snare', 0.7, 0.9),     # Beat 2
            DrumHit(1.0, 'kick', 0.8, 0.9),      # Beat 3
            DrumHit(1.5, 'snare', 0.7, 0.9),     # Beat 4
        ]
        
        # Add hi-hat pattern
        for i in range(8):
            drum_hits.append(
                DrumHit(i * 0.25, 'hihat', 0.5, 0.8)
            )
        
        beat_times = np.array([0, 0.5, 1.0, 1.5])
        tempo = 120.0
        
        patterns = self.drum_transcriber._detect_patterns(
            drum_hits, beat_times, tempo
        )
        
        self.assertIn('main_pattern', patterns)
        self.assertIn('fills', patterns)
        self.assertEqual(patterns['main_pattern'], 'rock_beat')
    
    def test_detect_fills(self):
        """Test drum fill detection"""
        # Create high-density drum hits (simulating a fill)
        drum_hits = []
        
        # Normal pattern (4 hits per second)
        for i in range(8):
            drum_hits.append(
                DrumHit(i * 0.25, 'snare', 0.7, 0.9)
            )
        
        # Fill section (12 hits per second from 2-3 seconds)
        for i in range(12):
            drum_hits.append(
                DrumHit(2.0 + i * 0.083, 'snare', 0.9, 0.9)
            )
        
        beat_times = np.array([0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0])
        
        fills = self.drum_transcriber._detect_fills(drum_hits, beat_times)
        
        # Should detect the high-density section as a fill
        self.assertGreater(len(fills), 0)
        
        # Check that fill is in the right time range
        fill = fills[0]
        self.assertGreaterEqual(fill['start'], 1.5)
        self.assertLessEqual(fill['end'], 3.5)
        self.assertGreater(fill['density'], 8)
    
    def test_generate_drum_notation(self):
        """Test drum notation generation"""
        drum_hits = [
            DrumHit(0.0, 'kick', 0.8, 0.9),
            DrumHit(0.5, 'snare', 0.7, 0.9),
            DrumHit(1.0, 'kick', 0.8, 0.9),
            DrumHit(1.5, 'snare', 0.7, 0.9),
        ]
        
        tempo = 120.0
        beat_times = np.array([0, 0.5, 1.0, 1.5])
        
        notation = self.drum_transcriber._generate_drum_notation(
            drum_hits, tempo, beat_times
        )
        
        self.assertIn('tempo', notation)
        self.assertEqual(notation['tempo'], tempo)
        self.assertIn('tracks', notation)
        self.assertIn('kick', notation['tracks'])
        self.assertIn('snare', notation['tracks'])
        
        # Check that hits are in tracks
        kick_track = notation['tracks']['kick']
        self.assertGreater(len(kick_track), 0)
        self.assertIn('time', kick_track[0])
        self.assertIn('velocity', kick_track[0])
    
    def test_organize_into_measures(self):
        """Test organizing drum hits into measures"""
        drum_hits = [
            DrumHit(0.0, 'kick', 0.8, 0.9),
            DrumHit(0.5, 'snare', 0.7, 0.9),
            DrumHit(2.0, 'kick', 0.8, 0.9),
            DrumHit(2.5, 'snare', 0.7, 0.9),
        ]
        
        beat_times = np.array([0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5])
        tempo = 120.0
        
        measures = self.drum_transcriber._organize_into_measures(
            drum_hits, beat_times, tempo
        )
        
        # Should have 2 measures (4/4 time at 120 BPM = 2 seconds per measure)
        self.assertEqual(len(measures), 2)
        
        # First measure should have 2 hits
        self.assertEqual(measures[0]['hit_count'], 2)
        self.assertEqual(measures[0]['number'], 1)
        
        # Second measure should have 2 hits
        self.assertEqual(measures[1]['hit_count'], 2)
        self.assertEqual(measures[1]['number'], 2)
    
    def test_generate_drum_tab(self):
        """Test ASCII drum tab generation"""
        drum_hits = [
            {'time': 0.0, 'drum_type': 'kick', 'velocity': 0.8},
            {'time': 0.25, 'drum_type': 'hihat', 'velocity': 0.5},
            {'time': 0.5, 'drum_type': 'snare', 'velocity': 0.7},
            {'time': 0.75, 'drum_type': 'hihat', 'velocity': 0.5},
            {'time': 1.0, 'drum_type': 'kick', 'velocity': 0.8},
            {'time': 1.25, 'drum_type': 'hihat', 'velocity': 0.5},
            {'time': 1.5, 'drum_type': 'snare', 'velocity': 0.7},
            {'time': 1.75, 'drum_type': 'hihat', 'velocity': 0.5},
        ]
        
        tempo = 120.0
        
        tab = self.drum_transcriber.generate_drum_tab(drum_hits, tempo)
        
        # Check tab structure
        self.assertIn('Tempo: 120 BPM', tab)
        self.assertIn('Time: 4/4', tab)
        self.assertIn('HH |', tab)  # Hi-hat line
        self.assertIn('SD |', tab)  # Snare line
        self.assertIn('BD |', tab)  # Bass drum line
        
        # Check that it contains the expected symbols
        lines = tab.split('\n')
        for line in lines:
            if line.startswith('HH |'):
                self.assertIn('x', line)  # Hi-hat hits
            elif line.startswith('SD |'):
                self.assertIn('o', line)  # Snare hits
            elif line.startswith('BD |'):
                self.assertIn('o', line)  # Kick hits
    
    def test_drum_hit_to_dict(self):
        """Test converting DrumHit to dictionary"""
        hit = DrumHit(
            time=1.5,
            drum_type='snare',
            velocity=0.75,
            confidence=0.85
        )
        
        hit_dict = self.drum_transcriber._drum_hit_to_dict(hit)
        
        self.assertEqual(hit_dict['time'], 1.5)
        self.assertEqual(hit_dict['drum_type'], 'snare')
        self.assertEqual(hit_dict['velocity'], 0.75)
        self.assertEqual(hit_dict['confidence'], 0.85)
        self.assertEqual(hit_dict['midi_note'], 38)  # Snare MIDI note
    
    def test_error_handling(self):
        """Test error handling in transcription"""
        # Try to transcribe non-existent file
        result = self.drum_transcriber.transcribe('/non/existent/file.wav')
        
        self.assertIn('error', result)
        self.assertEqual(result['tempo'], 120)  # Default tempo
        self.assertEqual(result['drum_hits'], [])
        
    def test_spectrum_classification_edge_cases(self):
        """Test drum classification with edge cases"""
        freqs = np.linspace(0, 11025, 513)
        
        # Test with empty spectrum
        empty_spectrum = np.zeros(513)
        drum_type, confidence = self.drum_transcriber._identify_drum_type(
            empty_spectrum, freqs
        )
        self.assertIsNotNone(drum_type)
        self.assertEqual(confidence, 0)
        
        # Test with full spectrum (white noise)
        noise_spectrum = np.ones(513)
        drum_type, confidence = self.drum_transcriber._identify_drum_type(
            noise_spectrum, freqs
        )
        self.assertIsNotNone(drum_type)
        self.assertGreater(confidence, 0)