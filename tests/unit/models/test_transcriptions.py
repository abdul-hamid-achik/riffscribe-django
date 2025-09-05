"""
Unit tests for Transcription model.
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from transcriber.models import Transcription
from model_bakery import baker


@pytest.mark.django_db
class TestTranscriptionModel:
    """Test the Transcription model."""
    
    @pytest.mark.unit
    def test_transcription_creation(self):
        """Test creating a transcription."""
        transcription = baker.make_recipe('transcriber.transcription_basic',
                                         filename="test.wav",
                                         status="pending")
        
        assert transcription.id is not None
        assert transcription.filename == "test.wav"
        assert transcription.status == "pending"
        assert transcription.created_at is not None
        assert transcription.updated_at is not None
    
    @pytest.mark.unit
    def test_transcription_string_representation(self):
        """Test string representation of transcription."""
        transcription = baker.make_recipe('transcriber.transcription_completed',
                                         filename="my_song.wav")
        
        assert str(transcription) == "my_song.wav - Completed"
    
    @pytest.mark.unit
    def test_transcription_with_audio_file(self):
        """Test transcription with audio file upload."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        
        audio_file = SimpleUploadedFile(
            "test_audio.wav",
            b"fake audio content",
            content_type="audio/wav"
        )
        
        transcription = baker.make_recipe('transcriber.transcription_basic',
                                         filename="test_audio.wav",
                                         original_audio=audio_file,
                                         status="pending")
        
        assert transcription.original_audio is not None
        assert "test_audio" in transcription.original_audio.name
    
    @pytest.mark.unit
    def test_transcription_status_choices(self):
        """Test transcription status field choices."""
        status_recipes = {
            'pending': 'transcriber.transcription_basic',
            'processing': 'transcriber.transcription_basic', 
            'completed': 'transcriber.transcription_completed',
            'failed': 'transcriber.transcription_failed'
        }
        
        for status, recipe_name in status_recipes.items():
            transcription = baker.make_recipe(recipe_name,
                                             filename=f"test_{status}.wav",
                                             status=status)
            assert transcription.status == status
    
    @pytest.mark.unit
    def test_transcription_metadata_fields(self):
        """Test metadata fields on transcription."""
        transcription = baker.make_recipe('transcriber.transcription_completed',
                                         filename="test.wav",
                                         duration=30.5,
                                         estimated_tempo=120,
                                         estimated_key="C Major",
                                         complexity="moderate",
                                         detected_instruments=["guitar", "bass"])
        
        assert transcription.duration == 30.5
        assert transcription.estimated_tempo == 120
        assert transcription.estimated_key == "C Major"
        assert transcription.complexity == "moderate"
        assert transcription.detected_instruments == ["guitar", "bass"]
    
    @pytest.mark.unit
    def test_transcription_json_fields(self):
        """Test JSON fields for storing complex data."""
        midi_data = {
            'notes': [
                {'start_time': 0, 'end_time': 0.5, 'midi_note': 60}
            ]
        }
        
        guitar_notes = {
            'tempo': 120,
            'measures': [
                {'notes': [{'string': 0, 'fret': 3}]}
            ]
        }
        
        transcription = baker.make_recipe('transcriber.transcription_completed',
                                         filename="test.wav",
                                         midi_data=midi_data,
                                         guitar_notes=guitar_notes)
        
        assert transcription.midi_data == midi_data
        assert transcription.guitar_notes == guitar_notes
        assert isinstance(transcription.midi_data, dict)
        assert isinstance(transcription.guitar_notes, dict)
    
    @pytest.mark.unit
    def test_transcription_status_tracking(self):
        """Test status tracking functionality."""
        transcription = baker.make_recipe('transcriber.transcription_basic',
                                         filename="test.wav",
                                         status="processing")
        
        assert transcription.status == "processing"
        transcription.status = "completed"
        transcription.save()
        assert transcription.status == "completed"