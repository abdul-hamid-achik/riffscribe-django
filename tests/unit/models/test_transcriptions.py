"""
Unit tests for Transcription model
"""
import pytest
import json
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile

from transcriber.models import Transcription
from model_bakery import baker
from tests.test_helpers import create_test_audio_file


class TestTranscriptionModel(TestCase):
    """Test Transcription model functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_transcription_creation(self):
        """Test basic transcription creation"""
        transcription = baker.make('transcriber.Transcription',
                                  user=self.user,
                                  filename='test_song.mp3',
                                  status='completed',
                                  original_audio=create_test_audio_file())
        
        self.assertEqual(transcription.user, self.user)
        self.assertEqual(transcription.filename, 'test_song.mp3')
        self.assertEqual(transcription.status, 'completed')
        self.assertIsNotNone(transcription.created_at)
        self.assertIsNotNone(transcription.updated_at)
        self.assertTrue(transcription.original_audio.name)
    
    def test_transcription_string_representation(self):
        """Test __str__ method"""
        transcription = baker.make('transcriber.Transcription',
                                  user=self.user,
                                  filename='my_song.mp3',
                                  status='completed',
                                  original_audio=create_test_audio_file())
        
        expected = f"my_song.mp3 - Completed"
        self.assertEqual(str(transcription), expected)
    
    def test_transcription_with_audio_file(self):
        """Test transcription with actual file content"""
        transcription = baker.make('transcriber.Transcription',
                                  user=self.user,
                                  filename='audio_file.wav',
                                  status='pending',
                                  original_audio=create_test_audio_file('audio_file.wav'))
        
        self.assertTrue(transcription.original_audio)
        # The file is uploaded to a path like audio/2025/09/06/audio_file_xxx.wav
        self.assertTrue('audio_file' in transcription.original_audio.name and '.wav' in transcription.original_audio.name)
    
    def test_transcription_status_choices(self):
        """Test different status choices"""
        statuses = ['pending', 'processing', 'completed', 'failed']
        
        for status in statuses:
            transcription = baker.make('transcriber.Transcription',
                                      user=self.user,
                                      filename=f'test_{status}.mp3',
                                      status=status,
                                      original_audio=create_test_audio_file())
            
            self.assertEqual(transcription.status, status)
    
    def test_transcription_metadata_fields(self):
        """Test metadata fields"""
        transcription = baker.make('transcriber.Transcription',
                                  user=self.user,
                                  filename='test_song.mp3',
                                  duration=180.5,
                                  estimated_tempo=120,
                                  estimated_key='C',
                                  complexity='moderate',
                                  status='completed',
                                  original_audio=create_test_audio_file())
        
        self.assertEqual(transcription.duration, 180.5)
        self.assertEqual(transcription.estimated_tempo, 120)
        self.assertEqual(transcription.estimated_key, 'C')
        self.assertEqual(transcription.complexity, 'moderate')
    
    def test_transcription_json_fields(self):
        """Test JSON fields functionality"""
        guitar_notes = {
            'measures': [
                {'notes': [{'fret': 0, 'string': 1, 'time': 0}]}
            ]
        }
        
        transcription = baker.make('transcriber.Transcription',
                                  user=self.user,
                                  filename='test_song.mp3',
                                  guitar_notes=guitar_notes,
                                  status='completed',
                                  original_audio=create_test_audio_file())
        
        self.assertEqual(transcription.guitar_notes, guitar_notes)
        self.assertIsInstance(transcription.guitar_notes, dict)
        self.assertIn('measures', transcription.guitar_notes)
    
    def test_transcription_status_tracking(self):
        """Test status tracking over time"""
        transcription = baker.make('transcriber.Transcription',
                                  user=self.user,
                                  filename='test_song.mp3',
                                  status='pending',
                                  original_audio=create_test_audio_file())
        
        original_updated = transcription.updated_at
        
        # Update status
        transcription.status = 'processing'
        transcription.save()
        
        self.assertEqual(transcription.status, 'processing')
        self.assertGreater(transcription.updated_at, original_updated)