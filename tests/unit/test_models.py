"""
Unit tests for Django models.
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from transcriber.models import Transcription, TabExport
from model_bakery import baker


@pytest.mark.django_db
class TestTranscriptionModel:
    """Test the Transcription model."""
    
    @pytest.mark.unit
    def test_transcription_creation(self):
        """Test creating a transcription."""
        transcription = Transcription.objects.create(
            filename="test.wav",
            status="pending"
        )
        
        assert transcription.id is not None
        assert transcription.filename == "test.wav"
        assert transcription.status == "pending"
        assert transcription.created_at is not None
        assert transcription.updated_at is not None
    
    @pytest.mark.unit
    def test_transcription_string_representation(self):
        """Test string representation of transcription."""
        transcription = baker.make(Transcription, filename="my_song.wav", status="completed")
        
        assert str(transcription) == "my_song.wav - Completed"
    
    @pytest.mark.unit
    def test_transcription_with_audio_file(self):
        """Test transcription with audio file upload."""
        audio_file = SimpleUploadedFile(
            "test_audio.wav",
            b"fake audio content",
            content_type="audio/wav"
        )
        
        transcription = Transcription.objects.create(
            filename="test_audio.wav",
            original_audio=audio_file,
            status="pending"
        )
        
        assert transcription.original_audio is not None
        assert "test_audio" in transcription.original_audio.name
    
    @pytest.mark.unit
    def test_transcription_status_choices(self):
        """Test transcription status field choices."""
        valid_statuses = ['pending', 'processing', 'completed', 'failed']
        
        for status in valid_statuses:
            transcription = Transcription.objects.create(
                filename=f"test_{status}.wav",
                status=status
            )
            assert transcription.status == status
    
    @pytest.mark.unit
    def test_transcription_metadata_fields(self):
        """Test metadata fields on transcription."""
        transcription = baker.make(Transcription,
            filename="test.wav",
            status="completed",
            duration=30.5,
            estimated_tempo=120,
            estimated_key="C Major",
            complexity="moderate",
            detected_instruments=["guitar", "bass"]
        )
        
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
        
        transcription = baker.make(Transcription,
            filename="test.wav",
            status="completed",
            midi_data=midi_data,
            guitar_notes=guitar_notes
        )
        
        assert transcription.midi_data == midi_data
        assert transcription.guitar_notes == guitar_notes
        assert isinstance(transcription.midi_data, dict)
        assert isinstance(transcription.guitar_notes, dict)
    
    @pytest.mark.unit
    def test_transcription_status_tracking(self):
        """Test status tracking functionality."""
        transcription = baker.make(Transcription,
            filename="test.wav",
            status="processing"
        )
        
        assert transcription.status == "processing"
        transcription.status = "completed"
        transcription.save()
        assert transcription.status == "completed"
    
    @pytest.mark.unit
    def test_transcription_cascade_delete(self):
        """Test that related exports are deleted with transcription."""
        transcription = baker.make(Transcription,
            filename="test.wav",
            status="completed"
        )
        
        export = baker.make(TabExport,
            transcription=transcription,
            format="musicxml"
        )
        
        transcription_id = transcription.id
        export_id = export.id
        
        transcription.delete()
        
        assert Transcription.objects.filter(id=transcription_id).count() == 0
        assert TabExport.objects.filter(id=export_id).count() == 0


@pytest.mark.django_db
class TestTabExportModel:
    """Test the TabExport model."""
    
    @pytest.mark.unit
    def test_tab_export_creation(self, completed_transcription):
        """Test creating a tab export."""
        export = baker.make(TabExport,
            transcription=completed_transcription,
            format="musicxml"
        )
        
        assert export.id is not None
        assert export.transcription == completed_transcription
        assert export.format == "musicxml"
        assert export.created_at is not None
    
    @pytest.mark.unit
    def test_tab_export_string_representation(self, completed_transcription):
        """Test string representation of tab export."""
        export = baker.make(TabExport,
            transcription=completed_transcription,
            format="gp5"
        )
        
        expected = f"{completed_transcription.filename} - Guitar Pro 5"
        assert str(export) == expected
    
    @pytest.mark.unit
    def test_tab_export_format_choices(self, completed_transcription):
        """Test export format field choices."""
        valid_formats = ['musicxml', 'gp5', 'midi', 'ascii']
        
        for format_type in valid_formats:
            export = baker.make(TabExport,
                transcription=completed_transcription,
                format=format_type
            )
            assert export.format == format_type
    
    @pytest.mark.unit
    def test_tab_export_with_file(self, completed_transcription):
        """Test tab export with actual file."""
        export_file = SimpleUploadedFile(
            "test_export.xml",
            b"<musicxml>content</musicxml>",
            content_type="text/xml"
        )
        
        export = baker.make(TabExport,
            transcription=completed_transcription,
            format="musicxml",
            file=export_file
        )
        
        assert export.file is not None
        assert "test_export" in export.file.name
    
    @pytest.mark.unit
    def test_tab_export_ordering(self, completed_transcription):
        """Test that exports are ordered by creation time."""
        export1 = baker.make(TabExport,
            transcription=completed_transcription,
            format="musicxml"
        )
        
        export2 = baker.make(TabExport,
            transcription=completed_transcription,
            format="gp5"
        )
        
        exports = TabExport.objects.filter(transcription=completed_transcription)
        assert exports.first().id == export2.id  # Most recent first
    
    @pytest.mark.unit
    def test_multiple_exports_per_transcription(self, completed_transcription):
        """Test that a transcription can have multiple exports."""
        export1 = baker.make(TabExport,
            transcription=completed_transcription,
            format="musicxml"
        )
        
        export2 = baker.make(TabExport,
            transcription=completed_transcription,
            format="gp5"  # Use valid format
        )
        
        export3 = baker.make(TabExport,
            transcription=completed_transcription,
            format="ascii"
        )
        
        exports = TabExport.objects.filter(transcription=completed_transcription)
        assert exports.count() == 3
        
        formats = [e.format for e in exports]
        assert "musicxml" in formats
        assert "gp5" in formats
        assert "ascii" in formats
    
    @pytest.mark.unit
    def test_tab_export_ordering(self, completed_transcription):
        """Test that exports are ordered by creation date."""
        import time
        
        export1 = TabExport.objects.create(
            transcription=completed_transcription,
            format="musicxml"
        )
        time.sleep(0.01)  # Small delay to ensure different timestamps
        
        export2 = TabExport.objects.create(
            transcription=completed_transcription,
            format="midi"
        )
        
        exports = TabExport.objects.filter(
            transcription=completed_transcription
        ).order_by('-created_at')
        
        assert exports[0] == export2  # Most recent first
        assert exports[1] == export1