"""
Unit tests for Django models.
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from transcriber.models import Transcription, TabExport


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
        transcription = Transcription.objects.create(
            filename="my_song.wav",
            status="completed"
        )
        
        assert str(transcription) == "my_song.wav - completed"
    
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
        transcription = Transcription.objects.create(
            filename="test.wav",
            status="completed",
            duration=30.5,
            estimated_tempo=120,
            estimated_key="C Major",
            complexity="moderate",
            detected_instruments=["guitar", "bass"],
            time_signature="4/4"
        )
        
        assert transcription.duration == 30.5
        assert transcription.estimated_tempo == 120
        assert transcription.estimated_key == "C Major"
        assert transcription.complexity == "moderate"
        assert transcription.detected_instruments == ["guitar", "bass"]
        assert transcription.time_signature == "4/4"
    
    @pytest.mark.unit
    def test_transcription_json_fields(self):
        """Test JSON fields for storing complex data."""
        notes_data = [
            {'start_time': 0, 'end_time': 0.5, 'midi_note': 60}
        ]
        
        guitar_notes = {
            'tempo': 120,
            'measures': [
                {'notes': [{'string': 0, 'fret': 3}]}
            ]
        }
        
        transcription = Transcription.objects.create(
            filename="test.wav",
            status="completed",
            raw_notes=notes_data,
            guitar_notes=guitar_notes
        )
        
        assert transcription.raw_notes == notes_data
        assert transcription.guitar_notes == guitar_notes
        assert isinstance(transcription.raw_notes, list)
        assert isinstance(transcription.guitar_notes, dict)
    
    @pytest.mark.unit
    def test_transcription_task_tracking(self):
        """Test task ID tracking fields."""
        transcription = Transcription.objects.create(
            filename="test.wav",
            status="processing",
            task_id="celery-task-123"
        )
        
        assert transcription.task_id == "celery-task-123"
    
    @pytest.mark.unit
    def test_transcription_cascade_delete(self):
        """Test that related exports are deleted with transcription."""
        transcription = Transcription.objects.create(
            filename="test.wav",
            status="completed"
        )
        
        export = TabExport.objects.create(
            transcription=transcription,
            format="musicxml",
            file_path="/tmp/test.xml"
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
        export = TabExport.objects.create(
            transcription=completed_transcription,
            format="musicxml",
            file_path="/exports/test.xml"
        )
        
        assert export.id is not None
        assert export.transcription == completed_transcription
        assert export.format == "musicxml"
        assert export.file_path == "/exports/test.xml"
        assert export.created_at is not None
    
    @pytest.mark.unit
    def test_tab_export_string_representation(self, completed_transcription):
        """Test string representation of tab export."""
        export = TabExport.objects.create(
            transcription=completed_transcription,
            format="gp5"
        )
        
        expected = f"{completed_transcription.filename} - gp5"
        assert str(export) == expected
    
    @pytest.mark.unit
    def test_tab_export_format_choices(self, completed_transcription):
        """Test export format field choices."""
        valid_formats = ['musicxml', 'gp5', 'midi', 'ascii']
        
        for format_type in valid_formats:
            export = TabExport.objects.create(
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
        
        export = TabExport.objects.create(
            transcription=completed_transcription,
            format="musicxml",
            export_file=export_file
        )
        
        assert export.export_file is not None
        assert "test_export" in export.export_file.name
    
    @pytest.mark.unit
    def test_tab_export_task_tracking(self, completed_transcription):
        """Test export task ID tracking."""
        export = TabExport.objects.create(
            transcription=completed_transcription,
            format="musicxml",
            task_id="export-task-456"
        )
        
        assert export.task_id == "export-task-456"
    
    @pytest.mark.unit
    def test_multiple_exports_per_transcription(self, completed_transcription):
        """Test that a transcription can have multiple exports."""
        export1 = TabExport.objects.create(
            transcription=completed_transcription,
            format="musicxml"
        )
        
        export2 = TabExport.objects.create(
            transcription=completed_transcription,
            format="midi"
        )
        
        export3 = TabExport.objects.create(
            transcription=completed_transcription,
            format="ascii"
        )
        
        exports = TabExport.objects.filter(transcription=completed_transcription)
        assert exports.count() == 3
        
        formats = [e.format for e in exports]
        assert "musicxml" in formats
        assert "midi" in formats
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