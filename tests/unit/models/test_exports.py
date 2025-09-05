"""
Unit tests for TabExport model.
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from transcriber.models import TabExport
from model_bakery import baker


@pytest.mark.django_db
class TestTabExportModel:
    """Test the TabExport model."""
    
    @pytest.mark.unit
    def test_tab_export_creation(self, completed_transcription):
        """Test creating a tab export."""
        export = baker.make_recipe('transcriber.tab_export_musicxml',
                                  transcription=completed_transcription)
        
        assert export.id is not None
        assert export.transcription == completed_transcription
        assert export.format == "musicxml"
        assert export.created_at is not None
    
    @pytest.mark.unit
    def test_tab_export_string_representation(self, completed_transcription):
        """Test string representation of tab export."""
        export = baker.make_recipe('transcriber.tab_export_gp5',
                                  transcription=completed_transcription)
        
        expected = f"{completed_transcription.filename} - Guitar Pro 5"
        assert str(export) == expected
    
    @pytest.mark.unit
    def test_tab_export_format_choices(self, completed_transcription):
        """Test export format field choices."""
        format_recipes = {
            'musicxml': 'transcriber.tab_export_musicxml',
            'gp5': 'transcriber.tab_export_gp5',
            'ascii': 'transcriber.tab_export_ascii',
            'pdf': 'transcriber.tab_export_pdf'
        }
        
        for format_type, recipe_name in format_recipes.items():
            export = baker.make_recipe(recipe_name,
                                      transcription=completed_transcription)
            assert export.format == format_type
    
    @pytest.mark.unit
    def test_tab_export_with_file(self, completed_transcription):
        """Test tab export with actual file."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        
        export_file = SimpleUploadedFile(
            "test_export.xml",
            b"<musicxml>content</musicxml>",
            content_type="text/xml"
        )
        
        export = baker.make_recipe('transcriber.tab_export_musicxml',
                                  transcription=completed_transcription,
                                  file=export_file)
        
        assert export.file is not None
        assert "test_export" in export.file.name
    
    @pytest.mark.unit
    def test_tab_export_ordering(self, completed_transcription):
        """Test that exports are ordered by creation time."""
        export1 = baker.make_recipe('transcriber.tab_export_musicxml',
                                   transcription=completed_transcription)
        
        export2 = baker.make_recipe('transcriber.tab_export_gp5',
                                   transcription=completed_transcription)
        
        exports = TabExport.objects.filter(transcription=completed_transcription)
        assert exports.first().id == export2.id  # Most recent first
    
    @pytest.mark.unit
    def test_multiple_exports_per_transcription(self, completed_transcription):
        """Test that a transcription can have multiple exports."""
        export1 = baker.make_recipe('transcriber.tab_export_musicxml',
                                   transcription=completed_transcription)
        
        export2 = baker.make_recipe('transcriber.tab_export_gp5',
                                   transcription=completed_transcription)
        
        export3 = baker.make_recipe('transcriber.tab_export_ascii',
                                   transcription=completed_transcription)
        
        exports = TabExport.objects.filter(transcription=completed_transcription)
        assert exports.count() == 3
        
        formats = [e.format for e in exports]
        assert "musicxml" in formats
        assert "gp5" in formats
        assert "ascii" in formats