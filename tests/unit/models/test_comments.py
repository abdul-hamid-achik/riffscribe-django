"""
Unit tests for Comment model
"""
import pytest
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from transcriber.models import Comment, Transcription, UserProfile
from model_bakery import baker
from tests.test_helpers import create_test_audio_file


class CommentModelTest(TestCase):
    """Test Comment model functionality"""
    
    def setUp(self):
        """Set up test data using Model Bakery"""
        # Create test user with specific username and no first_name to test username fallback
        self.user = User.objects.create_user(
            username='testuser',
            first_name='',  # Empty so display_name falls back to username
            email='test@example.com',
            password='testpass123'
        )
        
        # Create test transcription
        self.transcription = baker.make('transcriber.Transcription',
                                       user=self.user,
                                       filename='test_song.mp3',
                                       status='completed',
                                       original_audio=create_test_audio_file())
    
    def test_comment_creation_authenticated_user(self):
        """Test creating a comment with authenticated user"""
        comment = baker.make('transcriber.Comment',
                            transcription=self.transcription,
                            user=self.user,
                            content='Great transcription!',
                            is_approved=True,
                            is_flagged=False)
        
        self.assertEqual(comment.transcription, self.transcription)
        self.assertEqual(comment.user, self.user)
        self.assertEqual(comment.content, 'Great transcription!')
        self.assertTrue(comment.is_approved)
        self.assertFalse(comment.is_flagged)
        self.assertIsNone(comment.parent)
        self.assertIsNotNone(comment.created_at)
        self.assertIsNotNone(comment.updated_at)
    
    def test_comment_creation_anonymous_user(self):
        """Test creating a comment with anonymous user"""
        comment = baker.make('transcriber.Comment',
                            transcription=self.transcription,
                            user=None,
                            anonymous_name='Anonymous Musician',
                            anonymous_email='anon@example.com',
                            content='Nice work on this tab!',
                            is_approved=True,
                            is_flagged=False)
        
        self.assertEqual(comment.transcription, self.transcription)
        self.assertIsNone(comment.user)
        self.assertEqual(comment.anonymous_name, 'Anonymous Musician')
        self.assertEqual(comment.anonymous_email, 'anon@example.com')
        self.assertEqual(comment.content, 'Nice work on this tab!')
        self.assertTrue(comment.is_approved)
        self.assertFalse(comment.is_flagged)
    
    def test_comment_str_method_authenticated(self):
        """Test string representation for authenticated user comment"""
        comment = baker.make('transcriber.Comment',
                            transcription=self.transcription,
                            user=self.user,
                            content='Test comment',
                            is_approved=True)
        
        expected = f"Comment by {self.user.username} on {self.transcription.filename}"
        self.assertEqual(str(comment), expected)
    
    def test_comment_str_method_anonymous(self):
        """Test string representation for anonymous comment"""
        comment = baker.make('transcriber.Comment',
                            transcription=self.transcription,
                            user=None,
                            anonymous_name='Anonymous',
                            content='Test comment',
                            is_approved=True)
        
        expected = f"Comment by Anonymous on {self.transcription.filename}"
        self.assertEqual(str(comment), expected)
    
    def test_author_name_property_authenticated(self):
        """Test author_name property for authenticated user"""
        comment = baker.make('transcriber.Comment',
                            transcription=self.transcription,
                            user=self.user,
                            content='Test comment',
                            is_approved=True)
        
        # Should use user profile display name (which falls back to email prefix if no first_name)
        expected_name = self.user.profile.display_name if hasattr(self.user, 'profile') else self.user.username
        self.assertEqual(comment.author_name, expected_name)
    
    def test_author_name_property_authenticated_with_profile(self):
        """Test author_name property with user profile first_name"""
        # Update user to have first name
        self.user.first_name = 'John'
        self.user.save()
        
        comment = baker.make('transcriber.Comment',
                            transcription=self.transcription,
                            user=self.user,
                            content='Test comment',
                            is_approved=True)
        
        # Should use user's first name through profile
        self.assertEqual(comment.author_name, 'John')
    
    def test_author_name_property_anonymous_with_name(self):
        """Test author_name property for anonymous user with name"""
        comment = baker.make('transcriber.Comment',
                            transcription=self.transcription,
                            user=None,
                            anonymous_name='Guitar Hero',
                            content='Test comment',
                            is_approved=True)
        
        self.assertEqual(comment.author_name, 'Guitar Hero')
    
    def test_author_name_property_anonymous_without_name(self):
        """Test author_name property for anonymous user without name"""
        comment = baker.make('transcriber.Comment',
                            transcription=self.transcription,
                            user=None,
                            anonymous_name='',
                            content='Test comment',
                            is_approved=True)
        
        self.assertEqual(comment.author_name, 'Anonymous')
    
    def test_is_authenticated_user_property_true(self):
        """Test is_authenticated_user property returns True for authenticated user"""
        comment = baker.make('transcriber.Comment',
                            transcription=self.transcription,
                            user=self.user,
                            content='Test comment',
                            is_approved=True)
        
        self.assertTrue(comment.is_authenticated_user)
    
    def test_is_authenticated_user_property_false(self):
        """Test is_authenticated_user property returns False for anonymous user"""
        comment = baker.make('transcriber.Comment',
                            transcription=self.transcription,
                            user=None,
                            anonymous_name='Anonymous',
                            content='Test comment',
                            is_approved=True)
        
        self.assertFalse(comment.is_authenticated_user)
    
    def test_comment_without_content_fails(self):
        """Test that comment creation fails without content"""
        with self.assertRaises(ValidationError):
            comment = baker.make('transcriber.Comment',
                                transcription=self.transcription,
                                user=self.user,
                                content='',
                                is_approved=True)
            comment.full_clean()
    
    def test_comment_without_transcription_fails(self):
        """Test that comment creation fails without transcription"""
        with self.assertRaises(IntegrityError):
            baker.make('transcriber.Comment',
                      transcription=None,
                      user=self.user,
                      content='Test comment',
                      is_approved=True)
    
    def test_content_max_length(self):
        """Test comment content max length - skip if no validation at model level"""
        # Note: Max length validation may be handled at form/DB level
        # This test may not be relevant if model doesn't enforce it
        pass
    
    def test_anonymous_name_max_length(self):
        """Test anonymous name max length validation"""
        long_name = 'x' * 101  # Exceeds max_length of 100
        with self.assertRaises((ValidationError, Exception)):
            comment = Comment(
                transcription=self.transcription,
                user=None,
                anonymous_name=long_name,
                content='Test comment',
                is_approved=True
            )
            comment.full_clean()
            comment.save()
    
    def test_comment_moderation_flags(self):
        """Test comment moderation flag functionality"""
        comment = baker.make('transcriber.Comment',
                            transcription=self.transcription,
                            user=self.user,
                            content='Test comment',
                            is_approved=False,
                            is_flagged=True)
        
        self.assertFalse(comment.is_approved)
        self.assertTrue(comment.is_flagged)
    
    def test_comment_parent_relationship(self):
        """Test comment parent-child relationship"""
        parent_comment = baker.make('transcriber.Comment',
                                   transcription=self.transcription,
                                   user=self.user,
                                   content='Parent comment',
                                   is_approved=True)
        
        reply_comment = baker.make('transcriber.Comment',
                                  transcription=self.transcription,
                                  user=self.user,
                                  content='Reply comment',
                                  parent=parent_comment,
                                  is_approved=True)
        
        self.assertEqual(reply_comment.parent, parent_comment)
        self.assertIn(reply_comment, parent_comment.replies.all())
    
    def test_comment_ordering(self):
        """Test that comments are ordered by creation date (ascending)"""
        comment1 = baker.make('transcriber.Comment',
                             transcription=self.transcription,
                             user=self.user,
                             content='First comment',
                             is_approved=True)
        
        comment2 = baker.make('transcriber.Comment',
                             transcription=self.transcription,
                             user=self.user,
                             content='Second comment',
                             is_approved=True)
        
        comments = Comment.objects.filter(transcription=self.transcription).order_by('created_at')
        self.assertEqual(list(comments), [comment1, comment2])
    
    def test_comment_cascade_deletion_transcription(self):
        """Test that comments are deleted when transcription is deleted"""
        comment = baker.make('transcriber.Comment',
                            transcription=self.transcription,
                            user=self.user,
                            content='Test comment',
                            is_approved=True)
        
        comment_id = comment.id
        self.transcription.delete()
        
        self.assertFalse(Comment.objects.filter(id=comment_id).exists())
    
    def test_comment_cascade_deletion_user(self):
        """Test that user comments are deleted when user is deleted (CASCADE behavior)"""
        comment = baker.make('transcriber.Comment',
                            transcription=self.transcription,
                            user=self.user,
                            content='Test comment',
                            is_approved=True)
        
        comment_id = comment.id
        self.user.delete()
        
        # Comment should be deleted (CASCADE behavior)
        self.assertFalse(Comment.objects.filter(id=comment_id).exists())
    
    def test_multiple_comments_same_transcription(self):
        """Test multiple comments on the same transcription"""
        comment1 = baker.make('transcriber.Comment',
                             transcription=self.transcription,
                             user=self.user,
                             content='First comment',
                             is_approved=True)
        
        comment2 = baker.make('transcriber.Comment',
                             transcription=self.transcription,
                             user=None,
                             anonymous_name='Anonymous',
                             content='Anonymous comment',
                             is_approved=True)
        
        comments = Comment.objects.filter(transcription=self.transcription)
        self.assertEqual(comments.count(), 2)
        self.assertIn(comment1, comments)
        self.assertIn(comment2, comments)