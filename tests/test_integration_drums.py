"""
Integration tests for complete workflow including drum transcription.
"""

import pytest
import tempfile
import os
import json
from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from unittest.mock import Mock, patch, MagicMock
from transcriber.models import Transcription, Track, FingeringVariant, UserProfile
from transcriber.tasks import process_transcription
import numpy as np


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)  # Run tasks synchronously for tests
class DrumWorkflowIntegrationTest(TestCase):
    """Test complete workflow with drum transcription"""
    
    def setUp(self):
        self.client = Client()
        
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
        
        # Create mock audio file
        self.audio_content = b'mock audio file content'
        self.audio_file = SimpleUploadedFile(
            'test_song.mp3',
            self.audio_content,
            content_type='audio/mpeg'
        )
    
    @patch('transcriber.tasks.MLPipeline')
    def test_complete_workflow_with_drums(self, mock_pipeline_class):
        """Test complete transcription workflow including drum processing"""
        
        # Setup mock pipeline
        mock_pipeline = Mock()
        mock_pipeline_class.return_value = mock_pipeline
        
        # Mock audio analysis results
        mock_pipeline.analyze_audio.return_value = {
            'duration': 30.0,
            'sample_rate': 44100,
            'channels': 2,
            'tempo': 120,
            'key': 'C major',
            'complexity': 'moderate',
            'instruments': ['guitar', 'bass', 'drums'],
            'time_signature': '4/4'
        }
        
        # Mock source separation (returns original for guitar)
        mock_pipeline.separate_sources.return_value = {
            'guitar': '/tmp/guitar.wav',
            'bass': '/tmp/bass.wav',
            'drums': '/tmp/drums.wav'
        }
        
        # Mock transcription results
        mock_pipeline.transcribe.return_value = {
            'notes': [
                {'time': 0.0, 'pitch': 'E3', 'duration': 0.5},
                {'time': 0.5, 'pitch': 'G3', 'duration': 0.5},
            ],
            'midi_data': {'notes': [], 'tempo': 120}
        }
        
        # Mock multi-track processing with drums
        mock_pipeline.multi_track_service = Mock()
        mock_pipeline.multi_track_service.process_transcription.return_value = {
            'tracks': [
                {'type': 'drums', 'processed': True},
                {'type': 'bass', 'processed': True},
                {'type': 'guitar', 'processed': True}
            ],
            'track_count': 3,
            'processed_count': 3,
            'fallback': False
        }
        
        mock_pipeline.process_multitrack_transcription.return_value = {
            'tracks': [
                {'type': 'drums', 'processed': True},
                {'type': 'bass', 'processed': True},
                {'type': 'guitar', 'processed': True}
            ],
            'track_count': 3,
            'processed_count': 3,
            'fallback': False
        }
        
        # Upload file
        response = self.client.post(
            reverse('transcriber:upload'),
            {'audio_file': self.audio_file},
            format='multipart'
        )
        
        # Should redirect to detail page
        self.assertEqual(response.status_code, 302)
        
        # Get the created transcription
        transcription = Transcription.objects.filter(user=self.user).first()
        self.assertIsNotNone(transcription)
        
        # Process the transcription (mocked)
        with patch('transcriber.tab_generator.TabGenerator.generate_optimized_tabs') as mock_tabs:
            mock_tabs.return_value = {'measures': [], 'strings': 6}
            
            with patch('transcriber.services.export_manager.ExportManager.generate_musicxml') as mock_xml:
                mock_xml.return_value = '<musicxml>Mock</musicxml>'
                
                with patch('transcriber.services.export_manager.ExportManager.generate_gp5') as mock_gp5:
                    mock_gp5.return_value = '/tmp/mock.gp5'
                    
                    with patch('transcriber.variant_generator.VariantGenerator.generate_all_variants') as mock_variants:
                        mock_variants.return_value = []
                        
                        # Run the task
                        result = process_transcription(str(transcription.id))
        
        # Verify multi-track was called
        mock_pipeline.process_multitrack_transcription.assert_called_once()
        
        # Check result
        self.assertEqual(result['status'], 'success')
        self.assertIn('drums', str(transcription.detected_instruments))
    
    def test_drum_track_creation(self):
        """Test that drum tracks are properly created"""
        
        # Create transcription
        transcription = Transcription.objects.create(
            user=self.user,
            filename='test.mp3',
            status='completed',
            detected_instruments=['drums', 'bass', 'guitar']
        )
        
        # Create drum track
        drum_track = Track.objects.create(
            transcription=transcription,
            track_type='drums',
            instrument_type='drums',
            is_processed=True,
            guitar_notes={
                'drum_tab': 'HH |x-x-x-x-|\nSD |----o---|',
                'format': 'drum_notation'
            }
        )
        
        # Verify track exists
        tracks = transcription.tracks.all()
        drum_tracks = [t for t in tracks if t.track_type == 'drums']
        
        self.assertEqual(len(drum_tracks), 1)
        self.assertEqual(drum_tracks[0].instrument_type, 'drums')
        self.assertTrue(drum_tracks[0].is_processed)
        self.assertIsNotNone(drum_tracks[0].guitar_notes)
    
    def test_drum_tab_viewing(self):
        """Test viewing drum tabs in the UI"""
        
        # Create completed transcription with drum track
        transcription = Transcription.objects.create(
            user=self.user,
            filename='test.mp3',
            status='completed'
        )
        
        drum_track = Track.objects.create(
            transcription=transcription,
            track_type='drums',
            is_processed=True,
            guitar_notes={
                'drum_tab': 'Tempo: 120 BPM\nHH |x-x-x-x-|',
                'format': 'drum_notation'
            }
        )
        
        # View transcription detail page
        response = self.client.get(
            reverse('transcriber:detail', kwargs={'pk': transcription.pk})
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Check that tracks are in context
        self.assertIn('transcription', response.context)
        
        # Verify drum track data is accessible
        tracks = transcription.tracks.all()
        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0].track_type, 'drums')
    
    @patch('transcriber.services.drum_transcriber.librosa.load')
    @patch('transcriber.services.drum_transcriber.librosa.beat.beat_track')
    @patch('transcriber.services.drum_transcriber.librosa.onset.onset_detect')
    def test_drum_analysis_accuracy(self, mock_onset, mock_beat, mock_load):
        """Test accuracy of drum analysis"""
        from transcriber.services.drum_transcriber import DrumTranscriber
        
        # Setup mocks for a simple drum pattern
        sample_rate = 22050
        duration = 4.0
        samples = int(sample_rate * duration)
        
        # Create synthetic drum audio (simplified)
        audio = np.zeros(samples)
        
        # Add kick drum hits at beats 1 and 3 (0.0 and 1.0 seconds)
        for t in [0.0, 1.0, 2.0, 3.0]:
            idx = int(t * sample_rate)
            if idx < samples:
                audio[idx:idx+100] = np.sin(2 * np.pi * 60 * np.arange(100) / sample_rate)
        
        # Add snare hits at beats 2 and 4 (0.5 and 1.5 seconds)
        for t in [0.5, 1.5, 2.5, 3.5]:
            idx = int(t * sample_rate)
            if idx < samples:
                audio[idx:idx+100] = np.random.randn(100) * 0.5
        
        mock_load.return_value = (audio, sample_rate)
        mock_beat.return_value = (120.0, np.array([0, 11025, 22050, 33075, 44100]))
        
        # Onset frames for kick and snare pattern
        onset_frames = []
        for t in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]:
            frame = int(t * sample_rate / 512)  # 512 is typical hop length
            onset_frames.append(frame)
        mock_onset.return_value = np.array(onset_frames)
        
        # Run drum transcription
        transcriber = DrumTranscriber()
        with tempfile.NamedTemporaryFile(suffix='.wav') as temp_file:
            result = transcriber.transcribe(temp_file.name)
        
        # Verify results
        self.assertEqual(result['tempo'], 120.0)
        self.assertGreater(len(result['drum_hits']), 0)
        self.assertIn('patterns', result)
        self.assertIn('measures', result)
    
    def test_user_profile_with_drum_preferences(self):
        """Test user profile includes drum-related preferences"""
        
        # Get user profile
        profile = self.user.profile
        
        # Update preferences to include drums
        profile.preferred_genres = ['Rock', 'Jazz']  # Genres with prominent drums
        profile.save()
        
        # Create transcription with drums
        transcription = Transcription.objects.create(
            user=self.user,
            filename='drums_heavy.mp3',
            detected_instruments=['drums', 'guitar'],
            status='completed'
        )
        
        # Check that user can view their drum transcriptions
        response = self.client.get(reverse('transcriber:library'))
        self.assertEqual(response.status_code, 200)
        
        # Verify transcription appears in user's library
        self.assertIn('transcriptions', response.context)
        user_transcriptions = response.context['transcriptions']
        self.assertIn(transcription, user_transcriptions)
    
    def test_drum_export_formats(self):
        """Test exporting drum tabs in various formats"""
        
        # Create transcription with drum track
        transcription = Transcription.objects.create(
            user=self.user,
            filename='test.mp3',
            status='completed'
        )
        
        drum_track = Track.objects.create(
            transcription=transcription,
            track_type='drums',
            is_processed=True,
            guitar_notes={
                'drum_tab': 'HH |x-x-x-x-x-x-x-x-|',
                'format': 'drum_notation'
            },
            midi_data={
                'tempo': 120,
                'drum_hits': [
                    {'time': 0.0, 'drum_type': 'kick', 'midi_note': 36},
                    {'time': 0.5, 'drum_type': 'snare', 'midi_note': 38}
                ]
            }
        )
        
        # Test ASCII export
        ascii_content = drum_track.guitar_notes['drum_tab']
        self.assertIn('HH |', ascii_content)
        
        # Test MIDI data export
        midi_data = drum_track.midi_data
        self.assertEqual(midi_data['tempo'], 120)
        self.assertEqual(len(midi_data['drum_hits']), 2)
        
        # Verify MIDI notes are correct
        self.assertEqual(midi_data['drum_hits'][0]['midi_note'], 36)  # Kick
        self.assertEqual(midi_data['drum_hits'][1]['midi_note'], 38)  # Snare


class DrumPatternRecognitionTest(TestCase):
    """Test drum pattern recognition capabilities"""
    
    def test_rock_beat_pattern(self):
        """Test recognition of standard rock beat"""
        from transcriber.services.drum_transcriber import DrumTranscriber, DrumHit
        
        transcriber = DrumTranscriber()
        
        # Create standard rock beat pattern
        # Kick on 1 and 3, snare on 2 and 4, hi-hat eighth notes
        drum_hits = []
        
        # Two measures of rock beat
        for measure in range(2):
            offset = measure * 2.0
            # Kicks
            drum_hits.append(DrumHit(offset + 0.0, 'kick', 0.8, 0.9))
            drum_hits.append(DrumHit(offset + 1.0, 'kick', 0.8, 0.9))
            # Snares
            drum_hits.append(DrumHit(offset + 0.5, 'snare', 0.7, 0.9))
            drum_hits.append(DrumHit(offset + 1.5, 'snare', 0.7, 0.9))
            # Hi-hats (eighth notes)
            for i in range(8):
                drum_hits.append(DrumHit(offset + i * 0.25, 'hihat', 0.5, 0.8))
        
        beat_times = np.array([0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5])
        tempo = 120.0
        
        patterns = transcriber._detect_patterns(drum_hits, beat_times, tempo)
        
        self.assertEqual(patterns['main_pattern'], 'rock_beat')
    
    def test_drum_fill_detection(self):
        """Test detection of drum fills"""
        from transcriber.services.drum_transcriber import DrumTranscriber, DrumHit
        
        transcriber = DrumTranscriber()
        
        # Create pattern with a fill
        drum_hits = []
        
        # Normal pattern for 3 seconds
        for i in range(12):  # 4 hits per second
            drum_hits.append(DrumHit(i * 0.25, 'snare', 0.6, 0.8))
        
        # Drum fill from 3-4 seconds (high density)
        for i in range(16):  # 16 hits in 1 second
            drum_hits.append(DrumHit(3.0 + i * 0.0625, 'snare', 0.9, 0.9))
            
        beat_times = np.array([0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0])
        
        fills = transcriber._detect_fills(drum_hits, beat_times)
        
        # Should detect the high-density section as a fill
        self.assertGreater(len(fills), 0)
        
        # Verify fill timing
        fill = fills[0]
        self.assertGreaterEqual(fill['start'], 2.5)
        self.assertLessEqual(fill['end'], 4.5)
        self.assertGreater(fill['density'], 10)  # High density