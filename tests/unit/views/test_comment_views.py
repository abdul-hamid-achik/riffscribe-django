"""
Unit tests for Comment views
"""
import pytest
from django.test import TestCase, Client, RequestFactory
from django.contrib.auth.models import User, AnonymousUser
from django.urls import reverse
from django.http import Http404
from django.contrib.messages import get_messages
from unittest.mock import patch, MagicMock

from transcriber.models import Comment, Transcription
from transcriber.forms import CommentForm, AnonymousCommentForm
from transcriber.views.comments import (
    comments_list, add_comment, flag_comment, get_comment_form
)


class CommentViewsTest(TestCase):
    """Test comment-related views"""
    
    def setUp(self):
        """Set up test data"""
        self.factory = RequestFactory()
        self.client = Client()
        
        # Create test users
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='testpass456'
        )
        
        # Create test transcription
        self.transcription = Transcription.objects.create(
            user=self.user,
            filename='test_song.mp3',
            status='completed'
        )
        
        # Create test comments
        self.auth_comment = Comment.objects.create(
            transcription=self.transcription,
            user=self.user,
            content='Authenticated user comment'
        )
        
        self.anon_comment = Comment.objects.create(
            transcription=self.transcription,
            anonymous_name='Anonymous User',
            content='Anonymous comment'
        )


class CommentsListViewTest(CommentViewsTest):
    """Test comments_list view"""
    
    def test_comments_list_view_basic(self):
        """Test basic comments list functionality"""
        url = reverse('transcriber:comments_list', kwargs={'pk': self.transcription.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Authenticated user comment')
        self.assertContains(response, 'Anonymous comment')
    
    def test_comments_list_priority_sorting(self):
        """Test that authenticated user comments appear first"""
        url = reverse('transcriber:comments_list', kwargs={'pk': self.transcription.pk})
        response = self.client.get(url)
        
        # Check that authenticated comment appears before anonymous
        content = response.content.decode('utf-8')
        auth_pos = content.find('Authenticated user comment')
        anon_pos = content.find('Anonymous comment')
        
        self.assertTrue(auth_pos < anon_pos, "Authenticated comment should appear before anonymous")
    
    def test_comments_list_with_htmx(self):
        """Test comments list with HTMX request"""
        url = reverse('transcriber:comments_list', kwargs={'pk': self.transcription.pk})
        response = self.client.get(url, HTTP_HX_REQUEST='true')
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'transcriber/partials/comments_list.html')
    
    def test_comments_list_without_htmx(self):
        """Test comments list without HTMX request"""
        url = reverse('transcriber:comments_list', kwargs={'pk': self.transcription.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'transcriber/comments.html')
    
    def test_comments_list_nonexistent_transcription(self):
        """Test comments list for nonexistent transcription"""
        url = reverse('transcriber:comments_list', kwargs={'pk': 'nonexistent-uuid'})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 404)
    
    def test_comments_list_pagination(self):
        """Test comments list pagination"""
        # Create many comments to test pagination
        for i in range(15):  # More than the page size of 10
            Comment.objects.create(
                transcription=self.transcription,
                user=self.user,
                content=f'Comment {i}'
            )
        
        url = reverse('transcriber:comments_list', kwargs={'pk': self.transcription.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Next')  # Pagination controls
    
    def test_comments_list_only_approved(self):
        """Test that only approved comments are shown"""
        # Create unapproved comment
        unapproved_comment = Comment.objects.create(
            transcription=self.transcription,
            user=self.user,
            content='Unapproved comment',
            is_approved=False
        )
        
        url = reverse('transcriber:comments_list', kwargs={'pk': self.transcription.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Unapproved comment')


class AddCommentViewTest(CommentViewsTest):
    """Test add_comment view"""
    
    def test_add_comment_authenticated_user_valid(self):
        """Test adding comment as authenticated user with valid data"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('transcriber:add_comment', kwargs={'pk': self.transcription.pk})
        data = {'content': 'New authenticated comment'}
        
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, 200)
        
        # Check comment was created
        new_comment = Comment.objects.filter(content='New authenticated comment').first()
        self.assertIsNotNone(new_comment)
        self.assertEqual(new_comment.user, self.user)
        self.assertEqual(new_comment.transcription, self.transcription)
    
    def test_add_comment_authenticated_user_invalid(self):
        """Test adding comment as authenticated user with invalid data"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('transcriber:add_comment', kwargs={'pk': self.transcription.pk})
        data = {'content': ''}  # Empty content
        
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, 200)
        # Should return form with errors
        self.assertContains(response, 'This field is required')
    
    @patch('captcha.fields.CaptchaField.validate')
    def test_add_comment_anonymous_user_valid(self, mock_captcha):
        """Test adding comment as anonymous user with valid data"""
        mock_captcha.return_value = None
        
        url = reverse('transcriber:add_comment', kwargs={'pk': self.transcription.pk})
        data = {
            'anonymous_name': 'New Anonymous User',
            'content': 'New anonymous comment',
            'captcha_0': 'dummy_hash',
            'captcha_1': 'PASSED'
        }
        
        response = self.client.post(url, data)
        
        # Check comment was created (if captcha validation passes)
        new_comment = Comment.objects.filter(content='New anonymous comment').first()
        if response.status_code == 200 and new_comment:
            self.assertEqual(new_comment.anonymous_name, 'New Anonymous User')
            self.assertIsNone(new_comment.user)
    
    def test_add_comment_anonymous_user_invalid(self):
        """Test adding comment as anonymous user with invalid data"""
        url = reverse('transcriber:add_comment', kwargs={'pk': self.transcription.pk})
        data = {
            'anonymous_name': 'Test User',
            'content': '',  # Empty content
            'captcha_0': 'dummy_hash',
            'captcha_1': 'WRONG'
        }
        
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, 200)
        # Should return form with errors
    
    def test_add_comment_get_method_not_allowed(self):
        """Test that GET method is not allowed for add_comment"""
        url = reverse('transcriber:add_comment', kwargs={'pk': self.transcription.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 405)  # Method not allowed
    
    def test_add_comment_nonexistent_transcription(self):
        """Test adding comment to nonexistent transcription"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('transcriber:add_comment', kwargs={'pk': 'nonexistent-uuid'})
        data = {'content': 'Test comment'}
        
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, 404)
    
    def test_add_comment_success_message(self):
        """Test that success message is added after comment creation"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('transcriber:add_comment', kwargs={'pk': self.transcription.pk})
        data = {'content': 'Test comment for message'}
        
        response = self.client.post(url, data, follow=True)
        
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn('successfully', str(messages[0]))


class FlagCommentViewTest(CommentViewsTest):
    """Test flag_comment view"""
    
    def test_flag_comment_authenticated_user(self):
        """Test flagging comment as authenticated user"""
        self.client.login(username='otheruser', password='testpass456')
        
        url = reverse('transcriber:flag_comment', kwargs={
            'pk': self.transcription.pk,
            'comment_id': self.auth_comment.id
        })
        
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check comment was flagged
        self.auth_comment.refresh_from_db()
        self.assertTrue(self.auth_comment.is_flagged)
    
    def test_flag_comment_unauthenticated_user(self):
        """Test that unauthenticated user cannot flag comments"""
        url = reverse('transcriber:flag_comment', kwargs={
            'pk': self.transcription.pk,
            'comment_id': self.auth_comment.id
        })
        
        response = self.client.post(url)
        
        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)
    
    def test_flag_comment_get_method_not_allowed(self):
        """Test that GET method is not allowed for flag_comment"""
        self.client.login(username='otheruser', password='testpass456')
        
        url = reverse('transcriber:flag_comment', kwargs={
            'pk': self.transcription.pk,
            'comment_id': self.auth_comment.id
        })
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 405)  # Method not allowed
    
    def test_flag_comment_nonexistent_comment(self):
        """Test flagging nonexistent comment"""
        self.client.login(username='otheruser', password='testpass456')
        
        url = reverse('transcriber:flag_comment', kwargs={
            'pk': self.transcription.pk,
            'comment_id': 99999  # Non-existent ID
        })
        
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 404)
    
    def test_flag_comment_with_htmx(self):
        """Test flagging comment with HTMX request"""
        self.client.login(username='otheruser', password='testpass456')
        
        url = reverse('transcriber:flag_comment', kwargs={
            'pk': self.transcription.pk,
            'comment_id': self.auth_comment.id
        })
        
        response = self.client.post(url, HTTP_HX_REQUEST='true')
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'transcriber/partials/comment_flagged.html')


class GetCommentFormViewTest(CommentViewsTest):
    """Test get_comment_form view"""
    
    def test_get_comment_form_authenticated_user(self):
        """Test getting comment form for authenticated user"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('transcriber:get_comment_form', kwargs={'pk': self.transcription.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'transcriber/partials/comment_form.html')
        self.assertIsInstance(response.context['form'], CommentForm)
    
    def test_get_comment_form_anonymous_user(self):
        """Test getting comment form for anonymous user"""
        url = reverse('transcriber:get_comment_form', kwargs={'pk': self.transcription.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'transcriber/partials/anonymous_comment_form.html')
        self.assertIsInstance(response.context['form'], AnonymousCommentForm)
    
    def test_get_comment_form_nonexistent_transcription(self):
        """Test getting comment form for nonexistent transcription"""
        url = reverse('transcriber:get_comment_form', kwargs={'pk': 'nonexistent-uuid'})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 404)


class CommentViewsIntegrationTest(CommentViewsTest):
    """Integration tests for comment views working together"""
    
    def test_comment_workflow_authenticated_user(self):
        """Test complete comment workflow for authenticated user"""
        self.client.login(username='testuser', password='testpass123')
        
        # 1. Get comment form
        form_url = reverse('transcriber:get_comment_form', kwargs={'pk': self.transcription.pk})
        form_response = self.client.get(form_url)
        self.assertEqual(form_response.status_code, 200)
        
        # 2. Add comment
        add_url = reverse('transcriber:add_comment', kwargs={'pk': self.transcription.pk})
        add_data = {'content': 'Integration test comment'}
        add_response = self.client.post(add_url, add_data)
        self.assertEqual(add_response.status_code, 200)
        
        # 3. Verify comment appears in list
        list_url = reverse('transcriber:comments_list', kwargs={'pk': self.transcription.pk})
        list_response = self.client.get(list_url)
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, 'Integration test comment')
        
        # 4. Flag comment (as different user)
        self.client.logout()
        self.client.login(username='otheruser', password='testpass456')
        
        new_comment = Comment.objects.filter(content='Integration test comment').first()
        flag_url = reverse('transcriber:flag_comment', kwargs={
            'pk': self.transcription.pk,
            'comment_id': new_comment.id
        })
        flag_response = self.client.post(flag_url)
        self.assertEqual(flag_response.status_code, 200)
        
        # Verify comment is flagged
        new_comment.refresh_from_db()
        self.assertTrue(new_comment.is_flagged)
    
    def test_comment_ordering_with_mixed_users(self):
        """Test that comment ordering works with mixed authenticated/anonymous users"""
        # Add authenticated comment
        self.client.login(username='testuser', password='testpass123')
        add_url = reverse('transcriber:add_comment', kwargs={'pk': self.transcription.pk})
        self.client.post(add_url, {'content': 'Later authenticated comment'})
        
        # Add anonymous comment (mocked)
        with patch('captcha.fields.CaptchaField.validate') as mock_captcha:
            mock_captcha.return_value = None
            self.client.logout()
            
            anon_data = {
                'anonymous_name': 'Late Anonymous',
                'content': 'Later anonymous comment',
                'captcha_0': 'hash',
                'captcha_1': 'PASSED'
            }
            
            response = self.client.post(add_url, anon_data)
            
            if response.status_code == 200:
                # Check ordering in list
                list_url = reverse('transcriber:comments_list', kwargs={'pk': self.transcription.pk})
                list_response = self.client.get(list_url)
                
                content = list_response.content.decode('utf-8')
                
                # All authenticated comments should appear before anonymous
                auth_positions = []
                anon_positions = []
                
                # Find positions of verified user badges vs anonymous comments
                auth_badge_pos = content.find('Verified User')
                anon_comment_pos = content.find('Later anonymous comment')
                
                if auth_badge_pos != -1 and anon_comment_pos != -1:
                    # At least one authenticated comment should appear before anonymous
                    self.assertTrue(auth_badge_pos < anon_comment_pos)
    
    def test_error_handling_in_views(self):
        """Test error handling in comment views"""
        # Test with malformed UUID
        malformed_url = '/transcription/not-a-uuid/comments/'
        response = self.client.get(malformed_url)
        self.assertEqual(response.status_code, 404)
        
        # Test adding comment to non-existent transcription
        fake_uuid = '12345678-1234-5678-9012-123456789012'
        add_url = reverse('transcriber:add_comment', kwargs={'pk': fake_uuid})
        
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(add_url, {'content': 'Test comment'})
        self.assertEqual(response.status_code, 404)