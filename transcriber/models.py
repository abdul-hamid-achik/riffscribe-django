from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models.signals import post_save
from django.dispatch import receiver
import uuid


class UserProfile(models.Model):
    """Extended user profile for RiffScribe users"""
    
    SKILL_LEVELS = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
        ('expert', 'Expert'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    
    # Profile information
    bio = models.TextField(blank=True, max_length=500)
    skill_level = models.CharField(max_length=20, choices=SKILL_LEVELS, default='intermediate')
    preferred_genres = models.JSONField(default=list, blank=True)
    
    # Social profiles (if connected via OAuth)
    github_username = models.CharField(max_length=100, blank=True)
    github_profile_url = models.URLField(blank=True)
    google_profile_url = models.URLField(blank=True)
    
    # User preferences
    default_tempo_adjustment = models.FloatField(default=1.0, validators=[MinValueValidator(0.5), MaxValueValidator(2.0)])
    preferred_difficulty = models.CharField(max_length=20, choices=[
        ('easy', 'Easy'),
        ('balanced', 'Balanced'),
        ('technical', 'Technical'),
        ('original', 'Original'),
    ], default='balanced')
    
    # Usage statistics
    transcriptions_count = models.IntegerField(default=0)
    total_duration_processed = models.FloatField(default=0.0)  # in seconds
    favorite_transcriptions = models.ManyToManyField('Transcription', blank=True, related_name='favorited_by')
    
    # Karma system
    karma_score = models.IntegerField(default=0)
    comments_received_upvotes = models.IntegerField(default=0)
    comments_received_downvotes = models.IntegerField(default=0)
    
    # Subscription/limits (for future use)
    is_premium = models.BooleanField(default=False)
    monthly_upload_limit = models.IntegerField(default=10)
    uploads_this_month = models.IntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.email}'s profile"
    
    @property
    def display_name(self):
        """Return the best available display name"""
        if self.user.first_name and self.user.last_name:
            return f"{self.user.first_name} {self.user.last_name}"
        elif self.user.first_name:
            return self.user.first_name
        elif self.github_username:
            return self.github_username
        else:
            return self.user.email.split('@')[0]
    
    def can_upload(self):
        """Check if user can upload more files this month"""
        if self.is_premium:
            return True
        return self.uploads_this_month < self.monthly_upload_limit
    
    def increment_usage(self, duration=0):
        """Increment usage statistics"""
        self.transcriptions_count += 1
        self.uploads_this_month += 1
        if duration:
            self.total_duration_processed += duration
        self.save()
    
    def update_karma(self):
        """Update karma score based on received votes on user's comments"""
        from django.db.models import Sum
        
        # Get all comments by this user
        user_comments = Comment.objects.filter(user=self.user)
        
        # Calculate total upvotes and downvotes received
        upvotes = user_comments.aggregate(
            total=Sum('upvotes_count')
        )['total'] or 0
        
        downvotes = user_comments.aggregate(
            total=Sum('downvotes_count')
        )['total'] or 0
        
        # Update cached values
        self.comments_received_upvotes = upvotes
        self.comments_received_downvotes = downvotes
        
        # Calculate karma score (upvotes worth +1, downvotes worth -1)
        self.karma_score = upvotes - downvotes
        
        self.save(update_fields=['karma_score', 'comments_received_upvotes', 'comments_received_downvotes'])
    
    @property
    def karma_level(self):
        """Return karma level based on score"""
        if self.karma_score >= 500:
            return 'legendary'
        elif self.karma_score >= 100:
            return 'expert'
        elif self.karma_score >= 50:
            return 'experienced'
        elif self.karma_score >= 10:
            return 'contributor'
        elif self.karma_score >= 1:
            return 'newcomer'
        else:
            return 'beginner'
    
    @property
    def karma_level_display(self):
        """Return formatted karma level display"""
        levels = {
            'legendary': 'Legendary Contributor',
            'expert': 'Expert Musician',
            'experienced': 'Experienced Player',
            'contributor': 'Community Contributor',
            'newcomer': 'Newcomer',
            'beginner': 'Beginner'
        }
        return levels.get(self.karma_level, 'Beginner')
    
    @property
    def karma_badge_color(self):
        """Return CSS color class for karma badge"""
        colors = {
            'legendary': 'bg-purple-600',
            'expert': 'bg-yellow-500',
            'experienced': 'bg-blue-500',
            'contributor': 'bg-green-500',
            'newcomer': 'bg-gray-500',
            'beginner': 'bg-gray-400'
        }
        return colors.get(self.karma_level, 'bg-gray-400')


class Transcription(models.Model):
    """Model for audio transcriptions"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    COMPLEXITY_CHOICES = [
        ('simple', 'Simple'),
        ('moderate', 'Moderate'),
        ('complex', 'Complex'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transcriptions', null=True, blank=True)
    filename = models.CharField(max_length=255)
    original_audio = models.FileField(upload_to='audio/%Y/%m/%d/', null=True, blank=True)
    is_public = models.BooleanField(default=False, help_text="Allow public access to this transcription")
    
    # Status tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True, null=True)
    
    # Audio analysis
    duration = models.FloatField(null=True, blank=True)  # in seconds
    sample_rate = models.IntegerField(null=True, blank=True)
    channels = models.IntegerField(default=1)
    estimated_tempo = models.IntegerField(null=True, blank=True)  # BPM
    estimated_key = models.CharField(max_length=20, blank=True)
    complexity = models.CharField(max_length=20, choices=COMPLEXITY_CHOICES, blank=True)
    
    # Detected instruments (stored as JSON)
    detected_instruments = models.JSONField(default=list, blank=True)
    
    # Transcription results
    midi_data = models.JSONField(null=True, blank=True)
    musicxml_content = models.TextField(blank=True)
    gp5_file = models.FileField(upload_to='gp5/%Y/%m/%d/', null=True, blank=True)
    guitar_notes = models.JSONField(null=True, blank=True)
    
    # Whisper AI analysis
    whisper_analysis = models.JSONField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def get_secure_audio_url(self):
        """Get secure URL for audio file access"""
        from transcriber.views.media import get_secure_audio_url
        return get_secure_audio_url(self)
    
    @property
    def audio_url(self):
        """Property for easy template access to secure audio URL"""
        return self.get_secure_audio_url()
    
    def save(self, *args, **kwargs):
        """Override save to ensure JSON fields don't contain numpy arrays"""
        from .utils.json_utils import ensure_json_serializable
        
        # Clean JSON fields
        if self.midi_data is not None:
            self.midi_data = ensure_json_serializable(self.midi_data)
        if self.guitar_notes is not None:
            self.guitar_notes = ensure_json_serializable(self.guitar_notes)
        if self.whisper_analysis is not None:
            self.whisper_analysis = ensure_json_serializable(self.whisper_analysis)
        if self.detected_instruments is not None:
            self.detected_instruments = ensure_json_serializable(self.detected_instruments)
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.filename} - {self.get_status_display()}"
    
    def get_absolute_url(self):
        return reverse('transcriber:detail', kwargs={'pk': self.pk})
    
    @property
    def duration_formatted(self):
        """Return duration in MM:SS format"""
        if self.duration:
            minutes = int(self.duration // 60)
            seconds = int(self.duration % 60)
            return f"{minutes}:{seconds:02d}"
        return "--:--"
    
    @property
    def instruments_display(self):
        """Return instruments as comma-separated string"""
        if self.detected_instruments:
            return ", ".join(self.detected_instruments)
        return "Not detected"


class TabExport(models.Model):
    """Track exported tab files"""
    
    FORMAT_CHOICES = [
        ('musicxml', 'MusicXML'),
        ('gp5', 'Guitar Pro 5'),
        ('pdf', 'PDF'),
        ('ascii', 'ASCII Tab'),
    ]
    
    transcription = models.ForeignKey(Transcription, on_delete=models.CASCADE, related_name='exports')
    format = models.CharField(max_length=20, choices=FORMAT_CHOICES)
    file = models.FileField(upload_to='exports/%Y/%m/%d/')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.transcription.filename} - {self.get_format_display()}"


class PlayabilityMetrics(models.Model):
    """Global rollup metrics for the selected fingering variant"""
    
    transcription = models.OneToOneField(
        Transcription, 
        on_delete=models.CASCADE, 
        related_name='metrics'
    )
    
    # Playability scoring (0-100, higher = easier to play)
    playability_score = models.FloatField(
        null=True, 
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    
    # Skill level recommendation
    SKILL_LEVELS = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
        ('expert', 'Expert'),
    ]
    recommended_skill_level = models.CharField(
        max_length=16, 
        choices=SKILL_LEVELS,
        null=True, 
        blank=True
    )
    
    # Physical constraints
    max_fret_span = models.IntegerField(null=True, blank=True)  # Max chord/hand stretch in frets
    position_changes = models.IntegerField(null=True, blank=True)  # Count of large position shifts
    open_strings_used = models.IntegerField(null=True, blank=True)  # Count of open-string notes
    
    # Problem areas
    problem_sections = models.JSONField(null=True, blank=True)  # e.g. [{"measure": 3, "reason": "wide stretch"}]
    
    # Recommendations
    slow_tempo_suggestion = models.IntegerField(null=True, blank=True)  # Suggested practice tempo in BPM
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Metrics for {self.transcription.filename}"


class FingeringVariant(models.Model):
    """Different fingering arrangements for the same transcription"""
    
    transcription = models.ForeignKey(
        Transcription,
        on_delete=models.CASCADE,
        related_name='variants'
    )
    
    # Variant identification
    VARIANT_NAMES = [
        ('easy', 'Easy'),
        ('balanced', 'Balanced'),
        ('technical', 'Technical'),
        ('original', 'Original'),
    ]
    variant_name = models.CharField(max_length=32, choices=VARIANT_NAMES)
    
    # Scoring
    difficulty_score = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )  # 0-100, higher = harder
    playability_score = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )  # 0-100, higher = easier
    
    # Tab data (same structure as transcription.guitar_notes)
    tab_data = models.JSONField()
    
    # Simplifications applied
    removed_techniques = models.JSONField(null=True, blank=True)  # e.g. {"bends": 12, "slides": 4}
    
    # Optimizer configuration used
    config = models.JSONField(null=True, blank=True)  # Weight parameters used by optimizer
    
    # Selection status
    is_selected = models.BooleanField(default=False)  # Currently active variant
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['difficulty_score']
        unique_together = [['transcription', 'variant_name']]
    
    def __str__(self):
        return f"{self.transcription.filename} - {self.get_variant_name_display()}"
    
    def save(self, *args, **kwargs):
        # Ensure only one variant is selected per transcription
        if self.is_selected:
            FingeringVariant.objects.filter(
                transcription=self.transcription,
                is_selected=True
            ).exclude(pk=self.pk).update(is_selected=False)
        super().save(*args, **kwargs)


class FingeringMeasureStat(models.Model):
    """Per-measure statistics for a fingering variant"""
    
    variant = models.ForeignKey(
        FingeringVariant,
        on_delete=models.CASCADE,
        related_name='measure_stats'
    )
    
    measure_number = models.IntegerField()
    avg_fret = models.FloatField()  # Average fret position
    max_jump = models.IntegerField()  # Maximum fret jump
    chord_span = models.IntegerField()  # Fret span for chords
    string_crossings = models.IntegerField()  # Number of string changes
    
    class Meta:
        ordering = ['measure_number']
        unique_together = [['variant', 'measure_number']]
    
    def __str__(self):
        return f"{self.variant} - Measure {self.measure_number}"


class Track(models.Model):
    """Individual audio track from source separation"""
    
    TRACK_TYPES = [
        ('drums', 'Drums'),
        ('bass', 'Bass'), 
        ('vocals', 'Vocals'),
        ('other', 'Other/Accompaniment'),
        ('original', 'Original Mix'),
    ]
    
    INSTRUMENT_TYPES = [
        ('drums', 'Drums'),
        ('bass', 'Bass Guitar'),
        ('electric_guitar', 'Electric Guitar'),
        ('acoustic_guitar', 'Acoustic Guitar'),
        ('vocals', 'Vocals'),
        ('piano', 'Piano'),
        ('strings', 'Strings'),
        ('synthesizer', 'Synthesizer'),
        ('other', 'Other'),
    ]
    
    transcription = models.ForeignKey(
        Transcription,
        on_delete=models.CASCADE,
        related_name='tracks'
    )
    
    # Track identification
    track_type = models.CharField(max_length=20, choices=TRACK_TYPES)
    instrument_type = models.CharField(max_length=20, choices=INSTRUMENT_TYPES, null=True, blank=True)
    track_name = models.CharField(max_length=100, blank=True)  # Custom name
    track_order = models.IntegerField(default=0)  # Display order
    
    # Audio files
    separated_audio = models.FileField(upload_to='tracks/%Y/%m/%d/', null=True, blank=True)
    
    # Track-specific analysis
    volume_level = models.FloatField(null=True, blank=True)  # RMS amplitude
    prominence_score = models.FloatField(null=True, blank=True)  # How prominent this track is (0-1)
    
    # Track-specific transcription data
    midi_data = models.JSONField(null=True, blank=True)
    guitar_notes = models.JSONField(null=True, blank=True)  # Only for guitar tracks
    chord_progressions = models.JSONField(null=True, blank=True)  # Only for harmonic tracks
    
    # Processing status
    is_processed = models.BooleanField(default=False)
    processing_error = models.TextField(blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['track_order', 'track_type']
        unique_together = [['transcription', 'track_type']]
    
    def __str__(self):
        name = self.track_name or self.get_track_type_display()
        return f"{self.transcription.filename} - {name}"
    
    @property
    def display_name(self):
        """Return the display name for this track"""
        return self.track_name or self.get_track_type_display()


class TrackVariant(models.Model):
    """Fingering variants specific to a track (for guitar tracks)"""
    
    track = models.ForeignKey(
        Track,
        on_delete=models.CASCADE,
        related_name='variants'
    )
    
    # Same variant types as FingeringVariant
    VARIANT_NAMES = [
        ('easy', 'Easy'),
        ('balanced', 'Balanced'),
        ('technical', 'Technical'),
        ('original', 'Original'),
    ]
    variant_name = models.CharField(max_length=32, choices=VARIANT_NAMES)
    
    # Scoring
    difficulty_score = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    playability_score = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    
    # Tab data specific to this track
    tab_data = models.JSONField()
    
    # Simplifications applied
    removed_techniques = models.JSONField(null=True, blank=True)
    
    # Optimizer configuration used
    config = models.JSONField(null=True, blank=True)
    
    # Selection status
    is_selected = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['difficulty_score']
        unique_together = [['track', 'variant_name']]
    
    def __str__(self):
        return f"{self.track} - {self.get_variant_name_display()}"
    
    def save(self, *args, **kwargs):
        # Ensure only one variant is selected per track
        if self.is_selected:
            TrackVariant.objects.filter(
                track=self.track,
                is_selected=True
            ).exclude(pk=self.pk).update(is_selected=False)
        super().save(*args, **kwargs)


class MultiTrackExport(models.Model):
    """Export that includes multiple tracks"""
    
    FORMAT_CHOICES = [
        ('musicxml', 'MusicXML (Multi-track)'),
        ('gp5', 'Guitar Pro 5 (Multi-track)'),
        ('midi', 'MIDI (Multi-track)'),
        ('stems', 'Audio Stems (ZIP)'),
    ]
    
    transcription = models.ForeignKey(
        Transcription,
        on_delete=models.CASCADE,
        related_name='multi_exports'
    )
    
    format = models.CharField(max_length=20, choices=FORMAT_CHOICES)
    file = models.FileField(upload_to='multi_exports/%Y/%m/%d/')
    
    # Which tracks are included
    included_tracks = models.ManyToManyField(Track, related_name='exports')
    
    # Export settings
    export_settings = models.JSONField(null=True, blank=True)  # Format-specific settings
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        track_count = self.included_tracks.count()
        return f"{self.transcription.filename} - {self.get_format_display()} ({track_count} tracks)"


class Comment(models.Model):
    """Comments for transcriptions"""
    
    transcription = models.ForeignKey(
        Transcription,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    
    # User information (nullable for anonymous comments)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    
    # Anonymous user details
    anonymous_name = models.CharField(max_length=100, blank=True)
    anonymous_email = models.EmailField(blank=True)
    
    # Comment content
    content = models.TextField(max_length=2000)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Moderation
    is_approved = models.BooleanField(default=True)  # Auto-approve by default
    is_flagged = models.BooleanField(default=False)
    
    # For reply threading (optional future feature)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    
    # Voting metrics (cached for performance)
    upvotes_count = models.IntegerField(default=0)
    downvotes_count = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-created_at']  # Default ordering, will be overridden in views
    
    def __str__(self):
        author = self.user.username if self.user else self.anonymous_name
        return f"Comment by {author} on {self.transcription.filename}"
    
    @property
    def author_name(self):
        """Return the display name for the comment author"""
        if self.user:
            return self.user.profile.display_name if hasattr(self.user, 'profile') else self.user.username
        return self.anonymous_name or 'Anonymous'
    
    @property
    def is_authenticated_user(self):
        """Check if comment is from an authenticated user"""
        return self.user is not None
    
    @property
    def score(self):
        """Calculate comment score (upvotes - downvotes)"""
        return self.upvotes_count - self.downvotes_count
    
    def update_vote_counts(self):
        """Update cached vote counts from actual votes"""
        upvotes = self.votes.filter(vote_type='up').count()
        downvotes = self.votes.filter(vote_type='down').count()
        
        if upvotes != self.upvotes_count or downvotes != self.downvotes_count:
            self.upvotes_count = upvotes
            self.downvotes_count = downvotes
            self.save(update_fields=['upvotes_count', 'downvotes_count'])
    
    def get_user_vote(self, user):
        """Get the current user's vote on this comment"""
        if not user or not user.is_authenticated:
            return None
        
        try:
            vote = self.votes.get(user=user)
            return vote.vote_type
        except CommentVote.DoesNotExist:
            return None


class CommentVote(models.Model):
    """Votes on comments for upvote/downvote system"""
    
    VOTE_CHOICES = [
        ('up', 'Upvote'),
        ('down', 'Downvote'),
    ]
    
    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        related_name='votes'
    )
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='comment_votes'
    )
    
    vote_type = models.CharField(max_length=4, choices=VOTE_CHOICES)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['comment', 'user']  # One vote per user per comment
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} {self.vote_type}voted comment {self.comment.id}"
    
    def save(self, *args, **kwargs):
        """Update comment vote counts when vote is saved"""
        super().save(*args, **kwargs)
        
        # Update comment vote counts
        self.comment.update_vote_counts()
        
        # Update user karma
        if self.comment.user:
            self.comment.user.profile.update_karma()
    
    def delete(self, *args, **kwargs):
        """Update comment vote counts when vote is deleted"""
        comment = self.comment
        comment_user = comment.user
        
        super().delete(*args, **kwargs)
        
        # Update comment vote counts
        comment.update_vote_counts()
        
        # Update user karma
        if comment_user:
            comment_user.profile.update_karma()


# Signals to create UserProfile automatically
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create a UserProfile when a new User is created"""
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User) 
def save_user_profile(sender, instance, **kwargs):
    """Save the UserProfile when the User is saved"""
    if hasattr(instance, 'profile'):
        instance.profile.save()
