"""
Integration tests for variant selection and export views
"""

import pytest
import json
import uuid
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, Mock
from transcriber.models import Transcription, FingeringVariant, PlayabilityMetrics
from model_bakery import baker


class TestVariantViews(TestCase):
    """Test variant-related views"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.client = Client()
        
        # Create a completed transcription
        self.transcription = baker.make_recipe('transcriber.transcription_completed',
                                              filename='test_song.mp3',
                                              estimated_tempo=120,
                                              estimated_key='C')
        
        # Create variants
        self.easy_variant = baker.make_recipe('transcriber.fingering_variant_easy',
                                             transcription=self.transcription,
                                             difficulty_score=30,
                                             playability_score=70,
                                             is_selected=True)
        
        self.technical_variant = baker.make_recipe('transcriber.fingering_variant_technical',
                                                  transcription=self.transcription,
                                                  difficulty_score=70,
                                                  playability_score=30,
                                                  is_selected=False)
        
        # Create metrics
        self.metrics = baker.make_recipe('transcriber.playability_metrics',
                                        transcription=self.transcription,
                                        playability_score=70,
                                        recommended_skill_level='intermediate',
                                        max_fret_span=4,
                                        position_changes=2,
                                        open_strings_used=0)
        
    def test_variants_list_view(self):
        """Test listing all variants for a transcription"""
        url = reverse('transcriber:variants_list', kwargs={'pk': self.transcription.id})
        response = self.client.get(url)
        
        assert response.status_code == 200
        data = json.loads(response.content)
        
        assert data['transcription_id'] == str(self.transcription.id)
        assert len(data['variants']) == 2
        
        # Check variant data
        easy = next(v for v in data['variants'] if v['name'] == 'easy')
        assert easy['playability_score'] == 70
        assert easy['is_selected'] is True
        
        technical = next(v for v in data['variants'] if v['name'] == 'technical')
        assert technical['playability_score'] == 30
        assert technical['is_selected'] is False
        
    def test_variants_list_htmx(self):
        """Test variants list with HTMX request"""
        url = reverse('transcriber:variants_list', kwargs={'pk': self.transcription.id})
        response = self.client.get(url, HTTP_HX_REQUEST='true')
        
        assert response.status_code == 200
        assert b'variants-container' in response.content
        assert b'Easy' in response.content
        assert b'Technical' in response.content
        assert b'70%' in response.content  # Playability score
        
    def test_select_variant(self):
        """Test selecting a variant"""
        url = reverse('transcriber:select_variant', kwargs={
            'pk': self.transcription.id,
            'variant_id': self.technical_variant.id
        })
        
        response = self.client.post(url)
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['status'] == 'success'
        assert data['selected_variant'] == 'technical'
        
        # Check database was updated
        self.easy_variant.refresh_from_db()
        self.technical_variant.refresh_from_db()
        
        assert self.easy_variant.is_selected is False
        assert self.technical_variant.is_selected is True
        
        # Check parent transcription was updated
        self.transcription.refresh_from_db()
        assert self.transcription.guitar_notes == self.technical_variant.tab_data
        
    def test_select_variant_htmx(self):
        """Test selecting variant with HTMX request"""
        url = reverse('transcriber:select_variant', kwargs={
            'pk': self.transcription.id,
            'variant_id': self.technical_variant.id
        })
        
        response = self.client.post(url, HTTP_HX_REQUEST='true')
        
        assert response.status_code == 200
        assert b'variant-selected' in response.content
        assert b'Selected' in response.content
        
    def test_preview_variant(self):
        """Test previewing a variant without selecting it"""
        url = reverse('transcriber:preview_variant', kwargs={
            'pk': self.transcription.id,
            'variant_id': self.technical_variant.id
        })
        
        response = self.client.get(url)
        
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/xml'
        
        # Variant should not be selected
        self.technical_variant.refresh_from_db()
        assert self.technical_variant.is_selected is False
        
    def test_preview_variant_htmx(self):
        """Test variant preview with HTMX"""
        url = reverse('transcriber:preview_variant', kwargs={
            'pk': self.transcription.id,
            'variant_id': self.technical_variant.id
        })
        
        response = self.client.get(url, HTTP_HX_REQUEST='true')
        
        assert response.status_code == 200
        assert b'variant-preview' in response.content
        assert b'alphaTab' in response.content
        
    @patch('transcriber.tasks.generate_variants.delay')
    def test_regenerate_variants(self, mock_task):
        """Test regenerating all variants"""
        mock_task.return_value.id = 'test-task-id'
        
        url = reverse('transcriber:regenerate_variants', kwargs={
            'pk': self.transcription.id
        })
        
        response = self.client.post(url)
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['status'] == 'started'
        assert data['task_id'] == 'test-task-id'
        
        mock_task.assert_called_once_with(str(self.transcription.id), None)
        
    @patch('transcriber.tasks.generate_variants.delay')
    def test_regenerate_specific_variant(self, mock_task):
        """Test regenerating a specific variant preset"""
        mock_task.return_value.id = 'test-task-id'
        
        url = reverse('transcriber:regenerate_variants', kwargs={
            'pk': self.transcription.id
        })
        
        response = self.client.post(url, {'preset': 'easy'})
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['preset'] == 'easy'
        
        mock_task.assert_called_once_with(str(self.transcription.id), 'easy')
        
    def test_variant_stats(self):
        """Test getting variant statistics"""
        # Create measure stats
        from transcriber.models import FingeringMeasureStat
        FingeringMeasureStat.objects.create(
            variant=self.easy_variant,
            measure_number=1,
            avg_fret=5.0,
            max_jump=2,
            chord_span=3,
            string_crossings=1
        )
        
        url = reverse('transcriber:variant_stats', kwargs={
            'pk': self.transcription.id,
            'variant_id': self.easy_variant.id
        })
        
        response = self.client.get(url)
        
        assert response.status_code == 200
        data = json.loads(response.content)
        
        assert data['variant_name'] == 'easy'
        assert data['playability_score'] == 70
        assert len(data['measure_stats']) == 1
        
        measure = data['measure_stats'][0]
        assert measure['measure'] == 1
        assert measure['avg_fret'] == 5.0
        assert measure['max_jump'] == 2
        
    def test_export_variant_musicxml(self):
        """Test exporting a variant as MusicXML"""
        url = reverse('transcriber:export_variant', kwargs={
            'pk': self.transcription.id,
            'variant_id': self.easy_variant.id
        })
        
        response = self.client.get(url, {'format': 'musicxml'})
        
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/xml'
        assert 'attachment' in response['Content-Disposition']
        assert 'easy.xml' in response['Content-Disposition']
        
    @patch('transcriber.services.export_manager.ExportManager.generate_gp5_bytes')
    def test_export_variant_gp5(self, mock_gp5):
        """Test exporting a variant as Guitar Pro 5"""
        mock_gp5.return_value = b'GP5 content'
        
        url = reverse('transcriber:export_variant', kwargs={
            'pk': self.transcription.id,
            'variant_id': self.easy_variant.id
        })
        
        response = self.client.get(url, {'format': 'gp5'})
        
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/x-guitar-pro'
        assert response.content == b'GP5 content'
        
    def test_export_variant_ascii(self):
        """Test exporting a variant as ASCII tab"""
        url = reverse('transcriber:export_variant', kwargs={
            'pk': self.transcription.id,
            'variant_id': self.easy_variant.id
        })
        
        response = self.client.get(url, {'format': 'ascii'})
        
        assert response.status_code == 200
        assert response['Content-Type'] == 'text/plain'
        assert 'attachment' in response['Content-Disposition']
        
    def test_export_variant_invalid_format(self):
        """Test exporting with invalid format"""
        url = reverse('transcriber:export_variant', kwargs={
            'pk': self.transcription.id,
            'variant_id': self.easy_variant.id
        })
        
        response = self.client.get(url, {'format': 'invalid'})
        
        assert response.status_code == 400
        data = json.loads(response.content)
        assert 'error' in data
        
    def test_select_nonexistent_variant(self):
        """Test selecting a variant that doesn't exist"""
        fake_id = uuid.uuid4()
        url = reverse('transcriber:select_variant', kwargs={
            'pk': self.transcription.id,
            'variant_id': fake_id
        })
        
        response = self.client.post(url)
        
        assert response.status_code == 404
        
    def test_variants_for_nonexistent_transcription(self):
        """Test accessing variants for non-existent transcription"""
        fake_id = uuid.uuid4()
        url = reverse('transcriber:variants_list', kwargs={'pk': fake_id})
        
        response = self.client.get(url)
        
        assert response.status_code == 404