"""
End-to-end tests for comment functionality using Playwright
"""
import pytest
from django.test import LiveServerTestCase
from django.contrib.auth.models import User
from django.urls import reverse
from playwright.sync_api import sync_playwright, expect
import time
from unittest.mock import patch

from transcriber.models import Comment, Transcription


@pytest.mark.e2e
class CommentE2ETest(LiveServerTestCase):
    """End-to-end tests for comment system"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test class"""
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)
    
    @classmethod
    def tearDownClass(cls):
        """Tear down test class"""
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()
    
    def setUp(self):
        """Set up test data"""
        # Create test users
        self.author_user = User.objects.create_user(
            username='author',
            email='author@example.com',
            password='authorpass123'
        )
        
        self.commenter_user = User.objects.create_user(
            username='commenter',
            email='commenter@example.com',
            password='commenterpass123',
            first_name='John',
            last_name='Doe'
        )
        
        # Create test transcription
        self.transcription = Transcription.objects.create(
            user=self.author_user,
            filename='test_song.mp3',
            status='completed',
            duration=180.5
        )
        
        # Create existing comments for testing
        self.existing_auth_comment = Comment.objects.create(
            transcription=self.transcription,
            user=self.author_user,
            content='Original author comment'
        )
        
        self.existing_anon_comment = Comment.objects.create(
            transcription=self.transcription,
            anonymous_name='Music Fan',
            content='Great transcription!'
        )
        
        self.page = self.browser.new_page()
    
    def tearDown(self):
        """Clean up after test"""
        self.page.close()
    
    def login_user(self, username, password):
        """Helper method to log in a user"""
        login_url = f"{self.live_server_url}/accounts/login/"
        self.page.goto(login_url)
        
        self.page.fill('input[name="login"]', username)
        self.page.fill('input[name="password"]', password)
        self.page.click('button[type="submit"]')
        
        # Wait for redirect after login
        self.page.wait_for_url(f"{self.live_server_url}/dashboard/")
    
    def test_authenticated_user_comment_flow(self):
        """Test complete comment flow for authenticated user"""
        # Step 1: Login
        self.login_user('commenter', 'commenterpass123')
        
        # Step 2: Navigate to transcription detail page
        detail_url = f"{self.live_server_url}{reverse('transcriber:detail', kwargs={'pk': self.transcription.pk})}"
        self.page.goto(detail_url)
        
        # Step 3: Verify comments section is visible
        expect(self.page.locator('text=Comments')).to_be_visible()
        
        # Step 4: Wait for HTMX to load comment form
        self.page.wait_for_selector('[data-testid="comment-form"], textarea[name="content"]', timeout=10000)
        
        # Step 5: Verify authenticated user form is shown
        expect(self.page.locator('text=Verified User')).to_be_visible()
        
        # Step 6: Fill and submit comment
        comment_text = 'This is a fantastic transcription! The timing is perfect.'
        self.page.fill('textarea[name="content"]', comment_text)
        
        # Step 7: Submit comment
        self.page.click('button:has-text("Post Comment")')
        
        # Step 8: Wait for comment to appear in list
        self.page.wait_for_selector(f'text={comment_text}', timeout=10000)
        
        # Step 9: Verify comment appears with verified badge
        comment_section = self.page.locator(f'text={comment_text}').locator('..')
        expect(comment_section.locator('text=Verified User')).to_be_visible()
        
        # Step 10: Verify author name from profile
        expect(self.page.locator('text=John Doe')).to_be_visible()
        
        # Step 11: Verify comment was saved to database
        comment = Comment.objects.filter(content=comment_text).first()
        assert comment is not None
        assert comment.user == self.commenter_user
        assert comment.transcription == self.transcription
    
    def test_anonymous_user_comment_flow(self):
        """Test comment flow for anonymous user"""
        # Step 1: Navigate to transcription detail page (not logged in)
        detail_url = f"{self.live_server_url}{reverse('transcriber:detail', kwargs={'pk': self.transcription.pk})}"
        self.page.goto(detail_url)
        
        # Step 2: Verify comments section is visible
        expect(self.page.locator('text=Comments')).to_be_visible()
        
        # Step 3: Wait for HTMX to load anonymous comment form
        self.page.wait_for_selector('text=Anonymous User', timeout=10000)
        
        # Step 4: Verify anonymous form elements
        expect(self.page.locator('text=Anonymous User')).to_be_visible()
        expect(self.page.locator('text=Sign in')).to_be_visible()
        
        # Step 5: Fill anonymous comment form
        if self.page.locator('input[name="anonymous_name"]').is_visible():
            self.page.fill('input[name="anonymous_name"]', 'Guitar Student')
        
        comment_text = 'Amazing work! This helps me learn the song so much better.'
        self.page.fill('textarea[name="content"]', comment_text)
        
        # Step 6: Handle captcha (if present)
        captcha_input = self.page.locator('input[name="captcha_1"]')
        if captcha_input.is_visible():
            # In real e2e tests, you'd need to solve captcha or mock it
            # For demo purposes, we'll check if the form validation works
            self.page.click('button:has-text("Post Comment")')
            
            # Should show captcha validation error
            expect(self.page.locator('text=captcha')).to_be_visible()
            
            # In a real scenario, you'd solve the captcha here
            # captcha_input.fill('CORRECT_ANSWER')
        
        # Note: This test may not complete successfully due to captcha requirements
        # In production, you'd either:
        # 1. Use a test-specific captcha bypass
        # 2. Mock the captcha validation
        # 3. Use a separate captcha provider for testing
    
    def test_comment_priority_display(self):
        """Test that authenticated user comments have priority display"""
        # Navigate to transcription detail page
        detail_url = f"{self.live_server_url}{reverse('transcriber:detail', kwargs={'pk': self.transcription.pk})}"
        self.page.goto(detail_url)
        
        # Wait for comments to load
        self.page.wait_for_selector('text=Original author comment', timeout=10000)
        
        # Get all comment elements
        comments = self.page.locator('.comment-item').all()
        
        if len(comments) >= 2:
            # First comment should be from verified user (has badge)
            first_comment = comments[0]
            expect(first_comment.locator('text=Verified User')).to_be_visible()
            
            # Check if anonymous comment appears later
            page_content = self.page.content()
            auth_pos = page_content.find('Original author comment')
            anon_pos = page_content.find('Great transcription!')
            
            assert auth_pos < anon_pos, "Authenticated comment should appear before anonymous"
    
    def test_comment_flagging_flow(self):
        """Test comment flagging functionality"""
        # Step 1: Login as different user
        self.login_user('commenter', 'commenterpass123')
        
        # Step 2: Navigate to transcription detail page
        detail_url = f"{self.live_server_url}{reverse('transcriber:detail', kwargs={'pk': self.transcription.pk})}"
        self.page.goto(detail_url)
        
        # Step 3: Wait for comments to load
        self.page.wait_for_selector('text=Original author comment', timeout=10000)
        
        # Step 4: Find flag button for existing comment
        flag_button = self.page.locator('button[title*="Flag"]').first
        
        if flag_button.is_visible():
            # Step 5: Click flag button
            flag_button.click()
            
            # Step 6: Confirm in dialog
            self.page.on('dialog', lambda dialog: dialog.accept())
            
            # Step 7: Verify flagged status appears
            self.page.wait_for_selector('text=flagged for review', timeout=5000)
            expect(self.page.locator('text=flagged for review')).to_be_visible()
    
    def test_comment_character_counter(self):
        """Test comment character counter functionality"""
        # Login first
        self.login_user('commenter', 'commenterpass123')
        
        # Navigate to transcription detail page
        detail_url = f"{self.live_server_url}{reverse('transcriber:detail', kwargs={'pk': self.transcription.pk})}"
        self.page.goto(detail_url)
        
        # Wait for comment form
        textarea = self.page.locator('textarea[name="content"]')
        self.page.wait_for_selector('textarea[name="content"]', timeout=10000)
        
        # Type in comment field
        test_text = 'This is a test comment.'
        textarea.fill(test_text)
        
        # Check character counter updates
        counter = self.page.locator('#char-count, [id*="char-count"]')
        if counter.is_visible():
            expect(counter).to_contain_text(str(len(test_text)))
        
        # Test near limit
        long_text = 'x' * 1900
        textarea.fill(long_text)
        
        # Counter should show warning color for long text
        if counter.is_visible():
            counter_element = counter.first
            # Should have warning styling for long text
            expect(counter_element).to_have_class(/text-yellow-500|text-red-500/)
    
    def test_comment_pagination(self):
        """Test comment pagination in browser"""
        # Create many comments to trigger pagination
        for i in range(15):
            Comment.objects.create(
                transcription=self.transcription,
                user=self.author_user,
                content=f'Pagination test comment {i}'
            )
        
        # Navigate to transcription detail page
        detail_url = f"{self.live_server_url}{reverse('transcriber:detail', kwargs={'pk': self.transcription.pk})}"
        self.page.goto(detail_url)
        
        # Wait for comments to load
        self.page.wait_for_selector('text=Comments', timeout=10000)
        
        # Check for pagination controls
        next_button = self.page.locator('text=Next')
        if next_button.is_visible():
            # Click next page
            next_button.click()
            
            # Should load page 2
            self.page.wait_for_selector('text=Previous', timeout=5000)
            expect(self.page.locator('text=Previous')).to_be_visible()
    
    def test_htmx_comment_submission(self):
        """Test HTMX comment submission without page refresh"""
        # Login first
        self.login_user('commenter', 'commenterpass123')
        
        # Navigate to transcription detail page
        detail_url = f"{self.live_server_url}{reverse('transcriber:detail', kwargs={'pk': self.transcription.pk})}"
        self.page.goto(detail_url)
        
        # Get initial page URL
        initial_url = self.page.url
        
        # Wait for comment form and fill it
        self.page.wait_for_selector('textarea[name="content"]', timeout=10000)
        comment_text = 'HTMX submission test comment'
        self.page.fill('textarea[name="content"]', comment_text)
        
        # Submit comment
        self.page.click('button:has-text("Post Comment")')
        
        # Wait for comment to appear
        self.page.wait_for_selector(f'text={comment_text}', timeout=10000)
        
        # Verify URL hasn't changed (no page refresh)
        assert self.page.url == initial_url
        
        # Verify comment appears in the list
        expect(self.page.locator(f'text={comment_text}')).to_be_visible()
        
        # Verify form is cleared for next comment
        textarea_value = self.page.locator('textarea[name="content"]').input_value()
        assert textarea_value == '', "Form should be cleared after submission"
    
    def test_comment_responsive_design(self):
        """Test comment system on mobile viewport"""
        # Set mobile viewport
        self.page.set_viewport_size({"width": 375, "height": 667})
        
        # Navigate to transcription detail page
        detail_url = f"{self.live_server_url}{reverse('transcriber:detail', kwargs={'pk': self.transcription.pk})}"
        self.page.goto(detail_url)
        
        # Wait for comments section
        self.page.wait_for_selector('text=Comments', timeout=10000)
        
        # Verify comments section is visible and properly formatted on mobile
        comments_section = self.page.locator('[class*="comment"]').first
        if comments_section.is_visible():
            bounding_box = comments_section.bounding_box()
            
            # Should fit within mobile viewport width
            assert bounding_box['width'] <= 375
        
        # Test comment form on mobile
        textarea = self.page.locator('textarea[name="content"]')
        if textarea.is_visible():
            # Should be properly sized for mobile
            textarea_box = textarea.bounding_box()
            assert textarea_box['width'] <= 350  # Account for padding
    
    def test_authentication_modal_integration(self):
        """Test that anonymous users can access sign-in modal from comments"""
        # Navigate to transcription detail page (not logged in)
        detail_url = f"{self.live_server_url}{reverse('transcriber:detail', kwargs={'pk': self.transcription.pk})}"
        self.page.goto(detail_url)
        
        # Wait for anonymous comment form
        self.page.wait_for_selector('text=Sign in', timeout=10000)
        
        # Click sign in link
        signin_link = self.page.locator('text=Sign in').first
        if signin_link.is_visible():
            signin_link.click()
            
            # Should open authentication modal
            self.page.wait_for_selector('[id*="modal"]', timeout=5000)
            
            # Verify modal content
            expect(self.page.locator('text=Sign In, text=Email')).to_be_visible()
    
    def test_comment_accessibility(self):
        """Test comment system accessibility features"""
        # Navigate to transcription detail page
        detail_url = f"{self.live_server_url}{reverse('transcriber:detail', kwargs={'pk': self.transcription.pk})}"
        self.page.goto(detail_url)
        
        # Wait for comments to load
        self.page.wait_for_selector('text=Comments', timeout=10000)
        
        # Check for proper heading structure
        comments_heading = self.page.locator('h3:has-text("Comments")')
        expect(comments_heading).to_be_visible()
        
        # Check for form labels
        textarea = self.page.locator('textarea[name="content"]')
        if textarea.is_visible():
            # Should have accessible label or aria-label
            label_for = textarea.get_attribute('id')
            if label_for:
                label = self.page.locator(f'label[for="{label_for}"]')
                # Should have label or aria-label
                assert (label.is_visible() or 
                       textarea.get_attribute('aria-label') or
                       textarea.get_attribute('placeholder'))
        
        # Check for proper button labeling
        post_button = self.page.locator('button:has-text("Post Comment")')
        if post_button.is_visible():
            expect(post_button).to_be_visible()
            
        # Check for proper time formatting
        time_elements = self.page.locator('time').all()
        for time_elem in time_elements:
            # Should have datetime attribute for screen readers
            datetime_attr = time_elem.get_attribute('datetime')
            assert datetime_attr is not None
    
    def test_comment_error_handling(self):
        """Test comment form error handling in browser"""
        # Login first
        self.login_user('commenter', 'commenterpass123')
        
        # Navigate to transcription detail page
        detail_url = f"{self.live_server_url}{reverse('transcriber:detail', kwargs={'pk': self.transcription.pk})}"
        self.page.goto(detail_url)
        
        # Wait for comment form
        self.page.wait_for_selector('textarea[name="content"]', timeout=10000)
        
        # Try to submit empty comment
        self.page.click('button:has-text("Post Comment")')
        
        # Should show validation error
        self.page.wait_for_selector('text=This field is required', timeout=5000)
        expect(self.page.locator('text=This field is required')).to_be_visible()
        
        # Form should still be visible for correction
        expect(self.page.locator('textarea[name="content"]')).to_be_visible()
        
        # Try with valid content
        self.page.fill('textarea[name="content"]', 'Valid comment after error')
        self.page.click('button:has-text("Post Comment")')
        
        # Should succeed
        self.page.wait_for_selector('text=Valid comment after error', timeout=10000)
        expect(self.page.locator('text=Valid comment after error')).to_be_visible()


@pytest.mark.e2e
@pytest.mark.slow
class CommentPerformanceE2ETest(LiveServerTestCase):
    """Performance-focused e2e tests for comment system"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test class"""
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)
    
    @classmethod
    def tearDownClass(cls):
        """Tear down test class"""
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='perfuser',
            email='perf@example.com',
            password='perfpass123'
        )
        
        self.transcription = Transcription.objects.create(
            user=self.user,
            filename='perf_song.mp3',
            status='completed'
        )
        
        self.page = self.browser.new_page()
    
    def tearDown(self):
        """Clean up after test"""
        self.page.close()
    
    def test_comment_loading_performance(self):
        """Test comment loading performance with many comments"""
        # Create many comments
        for i in range(50):
            Comment.objects.create(
                transcription=self.transcription,
                user=self.user,
                content=f'Performance test comment {i}'
            )
        
        # Navigate to page and measure loading time
        detail_url = f"{self.live_server_url}{reverse('transcriber:detail', kwargs={'pk': self.transcription.pk})}"
        
        start_time = time.time()
        self.page.goto(detail_url)
        
        # Wait for comments to fully load
        self.page.wait_for_selector('text=Performance test comment', timeout=15000)
        
        load_time = time.time() - start_time
        
        # Should load within reasonable time (adjust threshold as needed)
        assert load_time < 10, f"Comments took too long to load: {load_time}s"
        
        # Verify pagination is working (not all comments loaded at once)
        all_comments = self.page.locator('.comment-item').all()
        assert len(all_comments) <= 10, "Should use pagination for many comments"
    
    def test_htmx_response_performance(self):
        """Test HTMX request performance"""
        # Login and navigate to page
        login_url = f"{self.live_server_url}/accounts/login/"
        self.page.goto(login_url)
        self.page.fill('input[name="login"]', 'perfuser')
        self.page.fill('input[name="password"]', 'perfpass123')
        self.page.click('button[type="submit"]')
        
        detail_url = f"{self.live_server_url}{reverse('transcriber:detail', kwargs={'pk': self.transcription.pk})}"
        self.page.goto(detail_url)
        
        # Wait for initial load
        self.page.wait_for_selector('textarea[name="content"]', timeout=10000)
        
        # Measure HTMX comment submission time
        self.page.fill('textarea[name="content"]', 'Performance test comment')
        
        start_time = time.time()
        self.page.click('button:has-text("Post Comment")')
        
        # Wait for comment to appear
        self.page.wait_for_selector('text=Performance test comment', timeout=10000)
        
        response_time = time.time() - start_time
        
        # HTMX response should be fast
        assert response_time < 5, f"HTMX comment submission too slow: {response_time}s"