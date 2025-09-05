"""
Tests for multi-track processing with drum support.
"""

import pytest
import tempfile
import os
import numpy as np
from django.test import TestCase
from django.core.files.base import ContentFile
from unittest.mock import Mock, patch, MagicMock, PropertyMock
from transcriber.models import Transcription, Track, User
from model_bakery import baker
from transcriber.services.multi_track_service import MultiTrackService
from transcriber.services.drum_transcriber import DrumHit


class MultiTrackDrumTestCase(TestCase):
    """Test multi-track processing with drum support"""
    
    def setUp(self):
        # Create test user and transcription
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass'
        )
        
        self.transcription = baker.make_recipe('transcriber.transcription_basic',
                                              user=self.user,
                                              filename='test_song.mp3',
                                              status='processing')
        
        # Create mock audio file
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
            temp_file.write(b'mock audio data')
            self.audio_path = temp_file.name
        
        # Set the original_audio path
        self.transcription.original_audio.name = self.audio_path
        
        # Initialize service with mocked model
        self.service = MultiTrackService(use_gpu=False)
    
    def tearDown(self):
        # Clean up temp file
        if os.path.exists(self.audio_path):
            os.unlink(self.audio_path)
    
    @patch('transcriber.multi_track_service.demucs')
    def test_multi_track_initialization(self, mock_demucs):
        """Test multi-track service initialization with drum transcriber"""
        service = MultiTrackService(use_gpu=False)
        
        # Check that drum transcriber is initialized
        self.assertIsNotNone(service.drum_transcriber)
        from transcriber.services.drum_transcriber import DrumTranscriber
        self.assertIsInstance(service.drum_transcriber, DrumTranscriber)
    
    @patch.object(MultiTrackService, 'separate_audio')
    @patch.object(MultiTrackService, 'analyze_track_prominence')
    @patch.object(MultiTrackService, 'classify_track_instruments')
    @patch.object(MultiTrackService, 'create_track_objects')
    @patch.object(MultiTrackService, 'process_drum_track')
    def test_process_transcription_with_drums(
        self, mock_process_drums, mock_create_tracks,
        mock_classify, mock_prominence, mock_separate
    ):
        """Test that drum track is processed when present"""
        
        # Mock separation results
        separated_files = {
            'drums': '/tmp/drums.wav',
            'bass': '/tmp/bass.wav',
            'other': '/tmp/other.wav',
            'vocals': '/tmp/vocals.wav'
        }
        mock_separate.return_value = separated_files
        
        # Mock prominence scores
        mock_prominence.return_value = {
            'drums': 0.8,
            'bass': 0.6,
            'other': 0.7,
            'vocals': 0.5
        }
        
        # Mock classifications
        mock_classify.return_value = {
            'drums': 'drums',
            'bass': 'bass',
            'other': 'electric_guitar',
            'vocals': 'vocals'
        }
        
        # Create mock tracks
        drum_track = Mock(spec=Track)
        drum_track.track_type = 'drums'
        drum_track.separated_audio = Mock()
        drum_track.separated_audio.path = '/tmp/drums.wav'
        
        other_tracks = [
            Mock(spec=Track, track_type='bass'),
            Mock(spec=Track, track_type='other'),
            Mock(spec=Track, track_type='vocals'),
        ]
        
        all_tracks = [drum_track] + other_tracks
        mock_create_tracks.return_value = all_tracks
        
        # Process transcription
        with patch('os.path.exists', return_value=True):
            result = self.service.process_transcription(
                self.transcription,
                cleanup_temp_files=False
            )
        
        # Verify drum processing was called
        mock_process_drums.assert_called_once_with(drum_track)
        
        # Verify all tracks were created
        self.assertEqual(len(result), 4)
        self.assertEqual(result[0].track_type, 'drums')
    
    def test_process_drum_track(self):
        """Test drum track processing"""
        # Create a drum track
        drum_track = baker.make_recipe('transcriber.track_drums',
                                      transcription=self.transcription,
                                      track_order=0)
        
        # Save a mock audio file
        drum_track.separated_audio.save(
            'drums.wav',
            ContentFile(b'mock drum audio')
        )
        
        # Mock drum transcriber
        mock_drum_data = {
            'tempo': 120,
            'drum_hits': [
                {'time': 0.0, 'drum_type': 'kick', 'velocity': 0.8, 'confidence': 0.9},
                {'time': 0.5, 'drum_type': 'snare', 'velocity': 0.7, 'confidence': 0.9},
            ],
            'measures': [
                {'number': 1, 'hits': 2, 'start_time': 0.0, 'end_time': 2.0}
            ],
            'patterns': {
                'main_pattern': 'rock_beat',
                'fills': []
            },
            'notation': {
                'tempo': 120,
                'tracks': {'kick': [], 'snare': []}
            }
        }
        
        with patch.object(self.service.drum_transcriber, 'transcribe', return_value=mock_drum_data):
            with patch.object(self.service.drum_transcriber, 'generate_drum_tab', return_value='Mock drum tab'):
                self.service.process_drum_track(drum_track)
        
        # Reload track from database
        drum_track.refresh_from_db()
        
        # Check that drum data was stored
        self.assertTrue(drum_track.is_processed)
        self.assertIsNotNone(drum_track.midi_data)
        self.assertEqual(drum_track.midi_data['tempo'], 120)
        self.assertEqual(len(drum_track.midi_data['drum_hits']), 2)
        
        # Check patterns storage
        self.assertIsNotNone(drum_track.chord_progressions)
        self.assertEqual(drum_track.chord_progressions['patterns']['main_pattern'], 'rock_beat')
        
        # Check drum tab storage
        self.assertIsNotNone(drum_track.guitar_notes)
        self.assertEqual(drum_track.guitar_notes['format'], 'drum_notation')
        self.assertIn('drum_tab', drum_track.guitar_notes)
    
    def test_process_drum_track_error_handling(self):
        """Test error handling in drum track processing"""
        # Create a drum track
        drum_track = Track.objects.create(
            transcription=self.transcription,
            track_type='drums',
            instrument_type='drums'
        )
        
        # Save invalid audio file
        drum_track.separated_audio.save(
            'invalid.wav',
            ContentFile(b'invalid')
        )
        
        # Mock transcriber to raise exception
        with patch.object(
            self.service.drum_transcriber,
            'transcribe',
            side_effect=Exception('Transcription failed')
        ):
            self.service.process_drum_track(drum_track)
        
        # Reload track
        drum_track.refresh_from_db()
        
        # Check error was recorded
        self.assertIn('Transcription failed', drum_track.processing_error)
        self.assertFalse(drum_track.is_processed)
    
    def test_drum_track_identification(self):
        """Test that drum tracks are properly identified"""
        # Create tracks with different types
        tracks = [
            Track(transcription=self.transcription, track_type='drums'),
            Track(transcription=self.transcription, track_type='bass'),
            Track(transcription=self.transcription, track_type='other'),
            Track(transcription=self.transcription, track_type='vocals'),
        ]
        
        # Find drum track
        drum_track = next((t for t in tracks if t.track_type == 'drums'), None)
        
        self.assertIsNotNone(drum_track)
        self.assertEqual(drum_track.track_type, 'drums')
    
    @patch.object(MultiTrackService, '_load_model')
    @patch('librosa.load')
    @patch('soundfile.write')
    def test_separation_includes_drums(self, mock_write, mock_load, mock_load_model):
        """Test that audio separation includes drum track"""
        # Mock audio loading
        mock_load.return_value = (np.random.randn(44100), 22050)
        
        # Mock model prediction
        mock_model = Mock()
        mock_sources = {
            'drums': np.random.randn(1, 2, 44100),
            'bass': np.random.randn(1, 2, 44100),
            'other': np.random.randn(1, 2, 44100),
            'vocals': np.random.randn(1, 2, 44100),
        }
        
        with patch('transcriber.multi_track_service.demucs'):
            with patch('transcriber.multi_track_service.apply_model', return_value=mock_sources):
                self.service.model = mock_model
                
                # Run separation
                result = self.service.separate_audio(self.audio_path)
        
        # Check that drums are in the result
        self.assertIn('drums', result)
        self.assertTrue(result['drums'].endswith('drums.wav'))
        
        # Verify write was called for drums
        write_calls = mock_write.call_args_list
        drum_written = any('drums.wav' in str(call) for call in write_calls)
        self.assertTrue(drum_written)
    
    def test_drum_tab_in_export(self):
        """Test that drum tabs are included in exports"""
        # Create drum track with tab data
        drum_track = Track.objects.create(
            transcription=self.transcription,
            track_type='drums',
            instrument_type='drums',
            is_processed=True,
            guitar_notes={
                'drum_tab': 'HH |x-x-x-x-|\nSD |----o---|',
                'format': 'drum_notation'
            }
        )
        
        # Check that drum tab is accessible
        self.assertIsNotNone(drum_track.guitar_notes)
        self.assertEqual(drum_track.guitar_notes['format'], 'drum_notation')
        self.assertIn('HH |', drum_track.guitar_notes['drum_tab'])
        self.assertIn('SD |', drum_track.guitar_notes['drum_tab'])
    
    def test_drum_pattern_detection_integration(self):
        """Test integration of drum pattern detection"""
        drum_track = Track.objects.create(
            transcription=self.transcription,
            track_type='drums'
        )
        
        # Mock complex drum pattern data
        mock_drum_data = {
            'tempo': 140,
            'drum_hits': [
                {'time': t * 0.214, 'drum_type': 'kick', 'velocity': 0.8}
                for t in range(8)
            ] + [
                {'time': t * 0.428, 'drum_type': 'snare', 'velocity': 0.7}
                for t in range(4)
            ],
            'patterns': {
                'main_pattern': 'double_kick',
                'fills': [
                    {'start': 3.0, 'end': 4.0, 'density': 12}
                ]
            },
            'measures': [],
            'notation': {}
        }
        
        drum_track.separated_audio.save('drums.wav', ContentFile(b'mock'))
        
        with patch.object(self.service.drum_transcriber, 'transcribe', return_value=mock_drum_data):
            with patch.object(self.service.drum_transcriber, 'generate_drum_tab', return_value=''):
                self.service.process_drum_track(drum_track)
        
        drum_track.refresh_from_db()
        
        # Verify pattern detection results
        patterns = drum_track.chord_progressions['patterns']
        self.assertEqual(patterns['main_pattern'], 'double_kick')
        self.assertEqual(len(drum_track.chord_progressions['fills']), 1)
        self.assertEqual(drum_track.chord_progressions['fills'][0]['density'], 12)


class DrumExportTestCase(TestCase):
    """Test drum track export functionality"""
    
    def setUp(self):
        self.user = User.objects.create_user('testuser')
        self.transcription = baker.make_recipe('transcriber.transcription_completed_with_user',
                                              user=self.user,
                                              filename='test.mp3')
        
        self.drum_track = baker.make_recipe('transcriber.track_drums',
                                           transcription=self.transcription,
                                           is_processed=True,
                                           guitar_notes={
                                               'drum_tab': self.generate_sample_drum_tab(),
                                               'format': 'drum_notation'
                                           },
                                           midi_data={
                                               'tempo': 120,
                                               'drum_hits': self.generate_sample_hits()
                                           })
    
    def generate_sample_drum_tab(self):
        """Generate sample drum tab"""
        return """Tempo: 120 BPM
Time: 4/4

Measure 1:
HH |x-x-x-x-x-x-x-x-|
SD |----o-------o---|
BD |o-------o-------|"""
    
    def generate_sample_hits(self):
        """Generate sample drum hits"""
        return [
            {'time': 0.0, 'drum_type': 'kick', 'velocity': 0.8, 'midi_note': 36},
            {'time': 0.5, 'drum_type': 'snare', 'velocity': 0.7, 'midi_note': 38},
            {'time': 1.0, 'drum_type': 'kick', 'velocity': 0.8, 'midi_note': 36},
            {'time': 1.5, 'drum_type': 'snare', 'velocity': 0.7, 'midi_note': 38},
        ]
    
    def test_drum_tab_export(self):
        """Test exporting drum tabs"""
        # Get drum tab
        drum_tab = self.drum_track.guitar_notes['drum_tab']
        
        # Verify structure
        self.assertIn('Tempo: 120 BPM', drum_tab)
        self.assertIn('HH |', drum_tab)
        self.assertIn('SD |', drum_tab)
        self.assertIn('BD |', drum_tab)
        
    def test_drum_midi_export(self):
        """Test drum MIDI data export"""
        midi_data = self.drum_track.midi_data
        
        # Check structure
        self.assertEqual(midi_data['tempo'], 120)
        self.assertEqual(len(midi_data['drum_hits']), 4)
        
        # Check MIDI notes
        for hit in midi_data['drum_hits']:
            self.assertIn('midi_note', hit)
            self.assertIn(hit['midi_note'], [36, 38])  # Kick or snare
    
    def test_multi_track_with_drums_export(self):
        """Test exporting multi-track with drums included"""
        # Add other tracks
        baker.make_recipe('transcriber.track_bass',
                         transcription=self.transcription,
                         is_processed=True)
        baker.make_recipe('transcriber.track_guitar',
                         transcription=self.transcription,
                         is_processed=True)
        
        # Get all tracks
        tracks = self.transcription.tracks.all()
        
        # Verify drums are included
        drum_tracks = [t for t in tracks if t.track_type == 'drums']
        self.assertEqual(len(drum_tracks), 1)
        self.assertTrue(drum_tracks[0].is_processed)