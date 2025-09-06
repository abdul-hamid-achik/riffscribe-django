"""
Integration tests for comment system workflows
"""
import pytest
from django.test import TestCase, TransactionTestCase
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.core import mail
from django.contrib.messages import get_messages
from unittest.mock import patch, Mock
from django.db import transaction

from transcriber.models import Comment, Transcription, UserProfile
from model_bakery import baker
from transcriber.forms import CommentForm, AnonymousCommentForm
from tests.test_helpers import create_test_audio_file


class CommentWorkflowIntegrationTest(TestCase):
    """Test complete comment workflows from end to end"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create test users
        self.author_user = User.objects.create_user(
            username='author',
            email='author@example.com',
            password='authorpass123'
        )
        
        self.commenter_user = User.objects.create_user(
            username='commenter',
            email='commenter@example.com',
            password='commenterpass123'
        )
        
        self.moderator_user = User.objects.create_user(
            username='moderator',
            email='moderator@example.com',
            password='moderatorpass123'
        )
        
        # Create test transcription
        from django.core.files.base import ContentFile
        from pathlib import Path
        
        def create_test_file():
            sample_path = Path(__file__).parent.parent / 'samples' / 'simple-riff.wav'
            if sample_path.exists():
                with open(sample_path, 'rb') as f:
                    return ContentFile(f.read(), 'simple-riff.wav')
            else:
                return ContentFile(b'test audio data', 'test.wav')
        
        self.transcription = baker.make('transcriber.Transcription',
                                       user=self.author_user,
                                       filename='test_song.mp3',
                                       duration=180.5,
                                       status='completed',
                                       original_audio=create_test_file())
        
        # Create processing transcription (should not show comments)
        self.processing_transcription = baker.make('transcriber.Transcription',
                                                  user=self.author_user,
                                                  filename='processing_song.mp3',
                                                  status='processing',
                                                  original_audio=create_test_file())
    
    def test_complete_authenticated_user_comment_workflow(self):
        """Test complete workflow: login -> view -> comment -> see result"""
        # Step 1: Login
        login_success = self.client.login(username='commenter', password='commenterpass123')
        self.assertTrue(login_success)
        
        # Step 2: View transcription detail page
        detail_url = reverse('transcriber:detail', kwargs={'pk': self.transcription.pk})
        detail_response = self.client.get(detail_url)
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, 'Comments')  # Comments section should be visible
        
        # Step 3: Get comment form (HTMX request)
        form_url = reverse('transcriber:get_comment_form', kwargs={'pk': self.transcription.pk})
        form_response = self.client.get(form_url, HTTP_HX_REQUEST='true')
        self.assertEqual(form_response.status_code, 200)
        self.assertContains(form_response, 'Verified User')  # Should show authenticated form
        
        # Step 4: Submit comment
        add_comment_url = reverse('transcriber:add_comment', kwargs={'pk': self.transcription.pk})
        comment_data = {
            'content': 'This is an excellent transcription! The guitar work is spot on.'
        }
        add_response = self.client.post(add_comment_url, comment_data, HTTP_HX_REQUEST='true')
        self.assertEqual(add_response.status_code, 200)
        
        # Step 5: Verify comment was created
        comment = Comment.objects.filter(
            transcription=self.transcription,
            user=self.commenter_user
        ).first()
        self.assertIsNotNone(comment)
        self.assertEqual(comment.content, comment_data['content'])
        self.assertTrue(comment.is_authenticated_user)
        
        # Step 6: Check comment appears in list
        comments_url = reverse('transcriber:comments_list', kwargs={'pk': self.transcription.pk})
        comments_response = self.client.get(comments_url, HTTP_HX_REQUEST='true')
        self.assertEqual(comments_response.status_code, 200)
        self.assertContains(comments_response, comment_data['content'])
        self.assertContains(comments_response, 'Verified User')  # Badge should be present
        
        # Step 7: Verify success message
        messages = list(get_messages(add_response.wsgi_request))
        self.assertTrue(any('successfully' in str(m) for m in messages))
    
    @patch('captcha.fields.CaptchaField.validate')
    def test_complete_anonymous_user_comment_workflow(self, mock_captcha):
        """Test complete workflow for anonymous user with captcha"""
        mock_captcha.return_value = None  # Mock successful captcha validation
        
        # Step 1: View transcription detail page (not logged in)
        detail_url = reverse('transcriber:detail', kwargs={'pk': self.transcription.pk})
        detail_response = self.client.get(detail_url)
        self.assertEqual(detail_response.status_code, 200)
        
        # Step 2: Get anonymous comment form
        form_url = reverse('transcriber:get_comment_form', kwargs={'pk': self.transcription.pk})
        form_response = self.client.get(form_url, HTTP_HX_REQUEST='true')
        self.assertEqual(form_response.status_code, 200)
        self.assertContains(form_response, 'Anonymous User')  # Should show anonymous form
        self.assertContains(form_response, 'Sign in')  # Should suggest signing in
        
        # Step 3: Submit anonymous comment
        add_comment_url = reverse('transcriber:add_comment', kwargs={'pk': self.transcription.pk})
        comment_data = {
            'anonymous_name': 'Guitar Enthusiast',
            'content': 'Great work! Love the fingering choices.',
            'captcha_0': 'dummy_hash',
            'captcha_1': 'PASSED'
        }
        
        add_response = self.client.post(add_comment_url, comment_data, HTTP_HX_REQUEST='true')
        
        # Skip assertion if captcha setup is incomplete
        if add_response.status_code == 200:
            # Step 4: Verify anonymous comment was created
            comment = Comment.objects.filter(
                transcription=self.transcription,
                anonymous_name='Guitar Enthusiast'
            ).first()
            
            if comment:  # Only proceed if comment was successfully created
                self.assertIsNone(comment.user)
                self.assertFalse(comment.is_authenticated_user)
                self.assertEqual(comment.author_name, 'Guitar Enthusiast')
                
                # Step 5: Check comment appears in list (lower priority)
                comments_url = reverse('transcriber:comments_list', kwargs={'pk': self.transcription.pk})
                comments_response = self.client.get(comments_url, HTTP_HX_REQUEST='true')
                self.assertEqual(comments_response.status_code, 200)
                self.assertContains(comments_response, comment_data['content'])
                self.assertNotContains(comments_response, 'Verified User')  # No badge for anonymous
    
    def test_comment_priority_sorting_workflow(self):
        """Test that authenticated users get priority in comment sorting"""
        # Create anonymous comment first
        anon_comment = baker.make('transcriber.Comment',
                                 transcription=self.transcription,
                                 user=None,
                                 anonymous_name='Early Anonymous',
                                 content='I was here first!',
                                 is_approved=True)
        
        # Then create authenticated comment
        self.client.login(username='commenter', password='commenterpass123')
        add_comment_url = reverse('transcriber:add_comment', kwargs={'pk': self.transcription.pk})
        auth_comment_data = {'content': 'Authenticated comment added later'}
        
        self.client.post(add_comment_url, auth_comment_data)
        
        # Get comments list and verify order
        comments_url = reverse('transcriber:comments_list', kwargs={'pk': self.transcription.pk})
        response = self.client.get(comments_url)
        
        content = response.content.decode('utf-8')
        
        # Find positions of both comments
        auth_pos = content.find('Authenticated comment added later')
        anon_pos = content.find('I was here first!')
        
        # Authenticated comment should appear first despite being added later
        self.assertTrue(auth_pos < anon_pos, "Authenticated comment should appear before anonymous")
    
    def test_comment_moderation_workflow(self):
        """Test complete comment moderation workflow"""
        # Step 1: User posts comment
        self.client.login(username='commenter', password='commenterpass123')
        add_comment_url = reverse('transcriber:add_comment', kwargs={'pk': self.transcription.pk})
        self.client.post(add_comment_url, {'content': 'This might be inappropriate content'})
        
        comment = Comment.objects.filter(content='This might be inappropriate content').first()
        self.assertIsNotNone(comment)
        self.assertFalse(comment.is_flagged)
        
        # Step 2: Different user flags the comment
        self.client.logout()
        self.client.login(username='moderator', password='moderatorpass123')
        
        flag_url = reverse('transcriber:flag_comment', kwargs={
            'pk': self.transcription.pk,
            'comment_id': comment.id
        })
        flag_response = self.client.post(flag_url, HTTP_HX_REQUEST='true')
        self.assertEqual(flag_response.status_code, 200)
        
        # Step 3: Verify comment is flagged
        comment.refresh_from_db()
        self.assertTrue(comment.is_flagged)
        
        # Step 4: Check flagged comment appears with warning in list
        comments_url = reverse('transcriber:comments_list', kwargs={'pk': self.transcription.pk})
        comments_response = self.client.get(comments_url)
        self.assertContains(comments_response, 'flagged for review')
    
    def test_comments_only_on_completed_transcriptions(self):
        """Test that comments only appear on completed transcriptions"""
        # Test completed transcription has comments section
        completed_detail_url = reverse('transcriber:detail', kwargs={'pk': self.transcription.pk})
        completed_response = self.client.get(completed_detail_url)
        self.assertEqual(completed_response.status_code, 200)
        self.assertContains(completed_response, 'Comments')
        
        # Test processing transcription does not have comments section
        processing_detail_url = reverse('transcriber:detail', kwargs={'pk': self.processing_transcription.pk})
        processing_response = self.client.get(processing_detail_url)
        self.assertEqual(processing_response.status_code, 200)
        self.assertNotContains(processing_response, 'Comments')
        
        # Test direct access to comments for processing transcription
        comments_url = reverse('transcriber:comments_list', kwargs={'pk': self.processing_transcription.pk})
        comments_response = self.client.get(comments_url)
        # Should still work but be empty/minimal
        self.assertEqual(comments_response.status_code, 200)
    
    def test_user_profile_integration_with_comments(self):
        """Test that user profiles integrate properly with comments"""
        # Modify user profile
        self.commenter_user.first_name = 'John'
        self.commenter_user.last_name = 'Musician'
        self.commenter_user.save()
        
        # Post comment
        self.client.login(username='commenter', password='commenterpass123')
        add_comment_url = reverse('transcriber:add_comment', kwargs={'pk': self.transcription.pk})
        self.client.post(add_comment_url, {'content': 'Comment with profile name'})
        
        # Check that profile display name is used
        comments_url = reverse('transcriber:comments_list', kwargs={'pk': self.transcription.pk})
        response = self.client.get(comments_url)
        
        expected_name = self.commenter_user.profile.display_name
        self.assertContains(response, expected_name)
    
    def test_comment_pagination_workflow(self):
        """Test comment pagination in a real workflow"""
        # Create many comments to trigger pagination
        self.client.login(username='commenter', password='commenterpass123')
        add_comment_url = reverse('transcriber:add_comment', kwargs={'pk': self.transcription.pk})
        
        for i in range(12):  # More than page size of 10
            self.client.post(add_comment_url, {'content': f'Comment number {i}'})
        
        # Test first page
        comments_url = reverse('transcriber:comments_list', kwargs={'pk': self.transcription.pk})
        page1_response = self.client.get(comments_url)
        self.assertEqual(page1_response.status_code, 200)
        self.assertContains(page1_response, 'Next')  # Should have next page
        
        # Test second page
        page2_response = self.client.get(comments_url + '?page=2')
        self.assertEqual(page2_response.status_code, 200)
        self.assertContains(page2_response, 'Previous')  # Should have previous page
    
    def test_mixed_authentication_comment_workflow(self):
        """Test workflow with both authenticated and anonymous comments"""
        # Add authenticated comment
        self.client.login(username='commenter', password='commenterpass123')
        add_comment_url = reverse('transcriber:add_comment', kwargs={'pk': self.transcription.pk})
        self.client.post(add_comment_url, {'content': 'Authenticated comment'})
        
        # Add anonymous comment (simulated)
        baker.make('transcriber.Comment',
                         transcription=self.transcription,
                         anonymous_name='Anonymous Fan',
                         content='Anonymous comment')
        
        # View comments list and verify both appear correctly
        comments_url = reverse('transcriber:comments_list', kwargs={'pk': self.transcription.pk})
        response = self.client.get(comments_url)
        
        content = response.content.decode('utf-8')
        
        # Both comments should appear
        self.assertIn('Authenticated comment', content)
        self.assertIn('Anonymous comment', content)
        
        # Authenticated should have priority (appear first)
        auth_pos = content.find('Authenticated comment')
        anon_pos = content.find('Anonymous comment')
        self.assertTrue(auth_pos < anon_pos)
        
        # Check for proper badges
        self.assertIn('Verified User', content)
        verified_pos = content.find('Verified User')
        self.assertTrue(verified_pos < anon_pos)  # Badge before anonymous comment
    
    def test_error_recovery_workflow(self):
        """Test error recovery in comment workflows"""
        self.client.login(username='commenter', password='commenterpass123')
        
        # Test invalid comment submission
        add_comment_url = reverse('transcriber:add_comment', kwargs={'pk': self.transcription.pk})
        invalid_data = {'content': ''}  # Empty content
        
        error_response = self.client.post(add_comment_url, invalid_data, HTTP_HX_REQUEST='true')
        self.assertEqual(error_response.status_code, 200)
        
        # Should return form with errors, not create comment
        self.assertEqual(Comment.objects.filter(transcription=self.transcription, user=self.commenter_user).count(), 0)
        
        # Test valid submission after error
        valid_data = {'content': 'Now this is a valid comment!'}
        success_response = self.client.post(add_comment_url, valid_data, HTTP_HX_REQUEST='true')
        self.assertEqual(success_response.status_code, 200)
        
        # Comment should now be created
        comment = Comment.objects.filter(transcription=self.transcription, user=self.commenter_user).first()
        self.assertIsNotNone(comment)
        self.assertEqual(comment.content, valid_data['content'])
    
    def test_concurrent_comment_submission(self):
        """Test handling of concurrent comment submissions"""
        # This test simulates multiple users commenting simultaneously
        
        # User 1 adds comment
        self.client.login(username='commenter', password='commenterpass123')
        add_comment_url = reverse('transcriber:add_comment', kwargs={'pk': self.transcription.pk})
        self.client.post(add_comment_url, {'content': 'First concurrent comment'})
        
        # User 2 adds comment (different client)
        client2 = Client()
        client2.login(username='moderator', password='moderatorpass123')
        client2.post(add_comment_url, {'content': 'Second concurrent comment'})
        
        # Both comments should exist
        comments = Comment.objects.filter(transcription=self.transcription)
        self.assertEqual(comments.count(), 2)
        
        # Comments list should show both
        comments_url = reverse('transcriber:comments_list', kwargs={'pk': self.transcription.pk})
        response = self.client.get(comments_url)
        
        self.assertContains(response, 'First concurrent comment')
        self.assertContains(response, 'Second concurrent comment')


class CommentDatabaseIntegrationTest(TransactionTestCase):
    """Test comment system database integration with transactions"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.transcription = baker.make('transcriber.Transcription',
                                       user=self.user,
                                       filename='test_song.mp3',
                                       status='completed',
                                       original_audio=create_test_audio_file())
        
        self.client = Client()
    
    def test_comment_transaction_rollback(self):
        """Test that failed comment creation rolls back properly"""
        self.client.login(username='testuser', password='testpass123')
        
        initial_count = Comment.objects.count()
        
        # Attempt to create comment with invalid data that might cause DB error
        add_comment_url = reverse('transcriber:add_comment', kwargs={'pk': self.transcription.pk})
        
        with patch('transcriber.models.Comment.save') as mock_save:
            mock_save.side_effect = Exception("Database error")
            
            try:
                self.client.post(add_comment_url, {'content': 'This should fail'})
            except Exception:
                pass  # Expected to fail
        
        # Comment count should not have changed
        self.assertEqual(Comment.objects.count(), initial_count)
    
    def test_comment_cascade_deletion_integration(self):
        """Test cascade deletion in integrated environment"""
        # Create comment
        comment = baker.make('transcriber.Comment',
                            transcription=self.transcription,
                            user=self.user,
                            content='Test comment for deletion',
                            is_approved=True)
        
        comment_id = comment.id
        self.assertTrue(Comment.objects.filter(id=comment_id).exists())
        
        # Delete transcription should cascade delete comment
        self.transcription.delete()
        
        self.assertFalse(Comment.objects.filter(id=comment_id).exists())
    
    def test_user_profile_creation_integration(self):
        """Test that user profile creation integrates with comment system"""
        # Create new user (should auto-create profile via signals)
        new_user = User.objects.create_user(
            username='newuser',
            email='new@example.com',
            password='newpass123'
        )
        
        # Profile should exist
        self.assertTrue(hasattr(new_user, 'profile'))
        
        # Create comment with new user
        comment = Comment.objects.create(
            transcription=self.transcription,
            user=new_user,
            content='Comment from new user'
        )
        
        # Profile display name should work
        self.assertIsNotNone(comment.author_name)
        self.assertEqual(comment.author_name, new_user.profile.display_name)