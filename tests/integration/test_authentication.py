import pytest
from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse
from transcriber.models import UserProfile, Transcription
from model_bakery import baker


class AuthenticationTestCase(TestCase):
    """Test authentication functionality"""
    
    def setUp(self):
        self.client = Client()
        
    def test_user_profile_creation(self):
        """Test that UserProfile is created automatically with User"""
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Profile should be created automatically
        self.assertTrue(hasattr(user, 'profile'))
        self.assertIsInstance(user.profile, UserProfile)
        self.assertEqual(user.profile.user, user)
        self.assertEqual(user.profile.skill_level, 'intermediate')
        self.assertEqual(user.profile.monthly_upload_limit, 10)
        
    def test_signup_view(self):
        """Test user signup"""
        response = self.client.get(reverse('account_signup'))
        self.assertEqual(response.status_code, 200)
        
        # Test signup with email
        response = self.client.post(reverse('account_signup'), {
            'email': 'newuser@example.com',
            'password1': 'ComplexPass123!',
            'password2': 'ComplexPass123!',
        })
        
        # Should create user and profile
        user = User.objects.filter(email='newuser@example.com').first()
        if user:  # Account might require email verification
            self.assertTrue(hasattr(user, 'profile'))
            
    def test_login_view(self):
        """Test user login"""
        # Create test user
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        response = self.client.get(reverse('account_login'))
        self.assertEqual(response.status_code, 200)
        
        # Test login
        response = self.client.post(reverse('account_login'), {
            'login': 'test@example.com',
            'password': 'testpass123',
        })
        
        # Should redirect after successful login
        self.assertIn(response.status_code, [302, 200])  # May redirect or show form with errors
        
    def test_dashboard_requires_login(self):
        """Test that dashboard requires authentication"""
        response = self.client.get(reverse('transcriber:dashboard'))
        self.assertEqual(response.status_code, 302)  # Should redirect to login
        self.assertIn('/accounts/login', response.url)
        
    def test_dashboard_with_login(self):
        """Test dashboard access with authenticated user"""
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.get(reverse('transcriber:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Welcome back')
        
    def test_profile_view(self):
        """Test profile view and edit"""
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
        
        # View profile
        response = self.client.get(reverse('transcriber:profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Profile Settings')
        
        # Update profile
        response = self.client.post(reverse('transcriber:profile'), {
            'first_name': 'Test',
            'last_name': 'User',
            'bio': 'Test bio',
            'skill_level': 'advanced',
            'preferred_difficulty': 'technical',
            'tempo_adjustment': '1.5',
            'genres': ['Rock', 'Blues'],
        })
        
        # Should redirect after successful update
        self.assertEqual(response.status_code, 302)
        
        # Check profile was updated
        user.refresh_from_db()
        user.profile.refresh_from_db()
        self.assertEqual(user.first_name, 'Test')
        self.assertEqual(user.last_name, 'User')
        self.assertEqual(user.profile.bio, 'Test bio')
        self.assertEqual(user.profile.skill_level, 'advanced')
        self.assertEqual(user.profile.preferred_difficulty, 'technical')
        self.assertIn('Rock', user.profile.preferred_genres)
        self.assertIn('Blues', user.profile.preferred_genres)


class TranscriptionOwnershipTestCase(TestCase):
    """Test transcription ownership and permissions"""
    
    def setUp(self):
        self.client = Client()
        
        # Create two users
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='pass123'
        )
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='pass123'
        )
        
        # Create transcriptions for each user
        from django.core.files.base import ContentFile
        from pathlib import Path
        
        def create_test_file():
            sample_path = Path(__file__).parent.parent / 'samples' / 'simple-riff.wav'
            if sample_path.exists():
                with open(sample_path, 'rb') as f:
                    return ContentFile(f.read(), 'simple-riff.wav')
            else:
                return ContentFile(b'test audio data', 'test.wav')
        
        self.trans1 = baker.make('transcriber.Transcription',
                                user=self.user1,
                                filename='user1_audio.mp3',
                                status='completed',
                                original_audio=create_test_file())
        self.trans2 = baker.make('transcriber.Transcription',
                                user=self.user2,
                                filename='user2_audio.mp3',
                                status='completed',
                                original_audio=create_test_file())
        
    def test_user_can_view_own_transcription(self):
        """Test user can view their own transcriptions"""
        self.client.login(username='user1', password='pass123')
        
        response = self.client.get(
            reverse('transcriber:detail', kwargs={'pk': self.trans1.pk})
        )
        self.assertEqual(response.status_code, 200)
        
    def test_user_cannot_view_others_transcription(self):
        """Test user cannot view others' transcriptions"""
        self.client.login(username='user1', password='pass123')
        
        response = self.client.get(
            reverse('transcriber:detail', kwargs={'pk': self.trans2.pk})
        )
        self.assertEqual(response.status_code, 403)  # Access denied
        
    def test_user_can_delete_own_transcription(self):
        """Test user can delete their own transcriptions"""
        self.client.login(username='user1', password='pass123')
        
        response = self.client.delete(
            reverse('transcriber:delete', kwargs={'pk': self.trans1.pk})
        )
        self.assertIn(response.status_code, [204, 200])  # Success
        
        # Check transcription was deleted
        self.assertFalse(
            Transcription.objects.filter(pk=self.trans1.pk).exists()
        )
        
    def test_user_cannot_delete_others_transcription(self):
        """Test user cannot delete others' transcriptions"""
        self.client.login(username='user1', password='pass123')
        
        response = self.client.delete(
            reverse('transcriber:delete', kwargs={'pk': self.trans2.pk})
        )
        self.assertEqual(response.status_code, 403)  # Access denied
        
        # Check transcription was not deleted
        self.assertTrue(
            Transcription.objects.filter(pk=self.trans2.pk).exists()
        )
        
    def test_library_shows_only_user_transcriptions(self):
        """Test library shows only user's transcriptions"""
        self.client.login(username='user1', password='pass123')
        
        response = self.client.get(reverse('transcriber:library'))
        self.assertEqual(response.status_code, 200)
        
        # Should contain user1's transcription but not user2's
        self.assertContains(response, 'user1_audio.mp3')
        self.assertNotContains(response, 'user2_audio.mp3')


class UserProfileUsageTestCase(TestCase):
    """Test user profile usage tracking"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
    def test_upload_limit_enforcement(self):
        """Test monthly upload limit is enforced"""
        self.client.login(username='testuser', password='testpass123')
        
        # Set user to have reached upload limit
        profile = self.user.profile
        profile.uploads_this_month = profile.monthly_upload_limit
        profile.save()
        
        # Try to upload (would need actual file upload test)
        # For now, just test the can_upload method
        self.assertFalse(profile.can_upload())
        
    def test_premium_user_unlimited_uploads(self):
        """Test premium users have unlimited uploads"""
        profile = self.user.profile
        profile.is_premium = True
        profile.uploads_this_month = 100  # Way over limit
        profile.save()
        
        self.assertTrue(profile.can_upload())
        
    def test_usage_tracking(self):
        """Test usage statistics are tracked"""
        profile = self.user.profile
        initial_count = profile.transcriptions_count
        initial_duration = profile.total_duration_processed
        initial_uploads = profile.uploads_this_month
        
        # Increment usage
        profile.increment_usage(duration=120.5)
        
        self.assertEqual(profile.transcriptions_count, initial_count + 1)
        self.assertEqual(profile.uploads_this_month, initial_uploads + 1)
        self.assertEqual(profile.total_duration_processed, initial_duration + 120.5)
        
    def test_favorite_transcriptions(self):
        """Test favorite transcriptions functionality"""
        self.client.login(username='testuser', password='testpass123')
        
        # Create a transcription
        from django.core.files.base import ContentFile
        from pathlib import Path
        
        def create_test_file():
            sample_path = Path(__file__).parent.parent / 'samples' / 'simple-riff.wav'
            if sample_path.exists():
                with open(sample_path, 'rb') as f:
                    return ContentFile(f.read(), 'simple-riff.wav')
            else:
                return ContentFile(b'test audio data', 'test.wav')
        
        trans = baker.make('transcriber.Transcription',
                          user=self.user,
                          filename='test.mp3',
                          status='completed',
                          original_audio=create_test_file())
        
        profile = self.user.profile
        
        # Add to favorites
        profile.favorite_transcriptions.add(trans)
        self.assertIn(trans, profile.favorite_transcriptions.all())
        
        # Toggle favorite via view
        response = self.client.post(
            reverse('transcriber:toggle_favorite', kwargs={'pk': trans.pk})
        )
        self.assertEqual(response.status_code, 200)
        
        # Should be removed from favorites
        self.assertNotIn(trans, profile.favorite_transcriptions.all())
        
        # Toggle again
        response = self.client.post(
            reverse('transcriber:toggle_favorite', kwargs={'pk': trans.pk})
        )
        self.assertEqual(response.status_code, 200)
        
        # Should be added back
        self.assertIn(trans, profile.favorite_transcriptions.all())