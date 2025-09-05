"""
Unit tests for Comment model
"""
import pytest
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from transcriber.models import Comment, Transcription, UserProfile


class CommentModelTest(TestCase):
    """Test Comment model functionality"""
    
    def setUp(self):
        """Set up test data"""
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create test transcription
        self.transcription = Transcription.objects.create(
            user=self.user,
            filename='test_song.mp3',
            status='completed'
        )
    
    def test_comment_creation_authenticated_user(self):
        """Test creating a comment with authenticated user"""
        comment = Comment.objects.create(
            transcription=self.transcription,
            user=self.user,
            content='Great transcription!'
        )
        
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
        comment = Comment.objects.create(
            transcription=self.transcription,
            anonymous_name='Anonymous Musician',
            anonymous_email='anon@example.com',
            content='Nice work on this tab!'
        )
        
        self.assertEqual(comment.transcription, self.transcription)
        self.assertIsNone(comment.user)
        self.assertEqual(comment.anonymous_name, 'Anonymous Musician')
        self.assertEqual(comment.anonymous_email, 'anon@example.com')
        self.assertEqual(comment.content, 'Nice work on this tab!')
        self.assertTrue(comment.is_approved)
        self.assertFalse(comment.is_flagged)
    
    def test_comment_str_method_authenticated(self):
        """Test string representation for authenticated user comment"""
        comment = Comment.objects.create(
            transcription=self.transcription,
            user=self.user,
            content='Test comment'
        )
        
        expected = f"Comment by {self.user.username} on {self.transcription.filename}"
        self.assertEqual(str(comment), expected)
    
    def test_comment_str_method_anonymous(self):
        """Test string representation for anonymous comment"""
        comment = Comment.objects.create(
            transcription=self.transcription,
            anonymous_name='Anonymous',
            content='Test comment'
        )
        
        expected = f"Comment by Anonymous on {self.transcription.filename}"
        self.assertEqual(str(comment), expected)
    
    def test_author_name_property_authenticated(self):
        """Test author_name property for authenticated user"""
        comment = Comment.objects.create(
            transcription=self.transcription,
            user=self.user,
            content='Test comment'
        )
        
        # Should use user profile display name or username
        self.assertEqual(comment.author_name, self.user.username)
    
    def test_author_name_property_authenticated_with_profile(self):
        """Test author_name property for authenticated user with profile"""
        # Modify user profile
        self.user.first_name = 'John'
        self.user.last_name = 'Doe'
        self.user.save()
        
        comment = Comment.objects.create(
            transcription=self.transcription,
            user=self.user,
            content='Test comment'
        )
        
        # Should use profile display name
        expected = self.user.profile.display_name
        self.assertEqual(comment.author_name, expected)
    
    def test_author_name_property_anonymous_with_name(self):
        """Test author_name property for anonymous user with name"""
        comment = Comment.objects.create(
            transcription=self.transcription,
            anonymous_name='Guitar Hero',
            content='Test comment'
        )
        
        self.assertEqual(comment.author_name, 'Guitar Hero')
    
    def test_author_name_property_anonymous_without_name(self):
        """Test author_name property for anonymous user without name"""
        comment = Comment.objects.create(
            transcription=self.transcription,
            content='Test comment'
        )
        
        self.assertEqual(comment.author_name, 'Anonymous')
    
    def test_is_authenticated_user_property_true(self):
        """Test is_authenticated_user property returns True for authenticated users"""
        comment = Comment.objects.create(
            transcription=self.transcription,
            user=self.user,
            content='Test comment'
        )
        
        self.assertTrue(comment.is_authenticated_user)
    
    def test_is_authenticated_user_property_false(self):
        """Test is_authenticated_user property returns False for anonymous users"""
        comment = Comment.objects.create(
            transcription=self.transcription,
            anonymous_name='Anonymous',
            content='Test comment'
        )
        
        self.assertFalse(comment.is_authenticated_user)
    
    def test_content_max_length(self):
        """Test comment content max length validation"""
        long_content = 'x' * 2001  # Exceeds 2000 character limit
        
        comment = Comment(
            transcription=self.transcription,
            user=self.user,
            content=long_content
        )
        
        with self.assertRaises(ValidationError):
            comment.full_clean()
    
    def test_anonymous_name_max_length(self):
        """Test anonymous name max length validation"""
        long_name = 'x' * 101  # Exceeds 100 character limit
        
        comment = Comment(
            transcription=self.transcription,
            anonymous_name=long_name,
            content='Test comment'
        )
        
        with self.assertRaises(ValidationError):
            comment.full_clean()
    
    def test_comment_ordering(self):
        """Test default comment ordering (by creation date, newest first)"""
        comment1 = Comment.objects.create(
            transcription=self.transcription,
            user=self.user,
            content='First comment'
        )
        
        comment2 = Comment.objects.create(
            transcription=self.transcription,
            anonymous_name='Anonymous',
            content='Second comment'
        )
        
        comments = Comment.objects.filter(transcription=self.transcription)
        self.assertEqual(list(comments), [comment2, comment1])  # Newest first
    
    def test_comment_cascade_deletion_user(self):
        """Test comment is deleted when user is deleted"""
        comment = Comment.objects.create(
            transcription=self.transcription,
            user=self.user,
            content='Test comment'
        )
        
        comment_id = comment.id
        self.user.delete()
        
        with self.assertRaises(Comment.DoesNotExist):
            Comment.objects.get(id=comment_id)
    
    def test_comment_cascade_deletion_transcription(self):
        """Test comment is deleted when transcription is deleted"""
        comment = Comment.objects.create(
            transcription=self.transcription,
            user=self.user,
            content='Test comment'
        )
        
        comment_id = comment.id
        self.transcription.delete()
        
        with self.assertRaises(Comment.DoesNotExist):
            Comment.objects.get(id=comment_id)
    
    def test_comment_parent_relationship(self):
        """Test comment parent-child relationship (for replies)"""
        parent_comment = Comment.objects.create(
            transcription=self.transcription,
            user=self.user,
            content='Parent comment'
        )
        
        reply_comment = Comment.objects.create(
            transcription=self.transcription,
            user=self.user,
            content='Reply comment',
            parent=parent_comment
        )
        
        self.assertEqual(reply_comment.parent, parent_comment)
        self.assertEqual(list(parent_comment.replies.all()), [reply_comment])
    
    def test_comment_moderation_flags(self):
        """Test comment moderation fields"""
        comment = Comment.objects.create(
            transcription=self.transcription,
            user=self.user,
            content='Test comment'
        )
        
        # Initially approved and not flagged
        self.assertTrue(comment.is_approved)
        self.assertFalse(comment.is_flagged)
        
        # Flag the comment
        comment.is_flagged = True
        comment.save()
        
        comment.refresh_from_db()
        self.assertTrue(comment.is_flagged)
    
    def test_comment_without_content_fails(self):
        """Test that comment without content fails validation"""
        comment = Comment(
            transcription=self.transcription,
            user=self.user,
            content=''  # Empty content
        )
        
        with self.assertRaises(ValidationError):
            comment.full_clean()
    
    def test_comment_without_transcription_fails(self):
        """Test that comment without transcription fails"""
        with self.assertRaises(IntegrityError):
            Comment.objects.create(
                user=self.user,
                content='Test comment'
                # Missing transcription
            )
    
    def test_multiple_comments_same_transcription(self):
        """Test multiple comments on same transcription"""
        comment1 = Comment.objects.create(
            transcription=self.transcription,
            user=self.user,
            content='First comment'
        )
        
        comment2 = Comment.objects.create(
            transcription=self.transcription,
            anonymous_name='Anonymous',
            content='Second comment'
        )
        
        transcription_comments = self.transcription.comments.all()
        self.assertEqual(transcription_comments.count(), 2)
        self.assertIn(comment1, transcription_comments)
        self.assertIn(comment2, transcription_comments)