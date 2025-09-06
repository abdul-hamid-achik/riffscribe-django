"""
Comprehensive seeding management command for RiffScribe Django.

This command creates a rich dataset using model_bakery recipes including:
- Diverse user accounts with authentic profiles
- Sample audio transcriptions (simple and complex riffs)
- Abundant community interaction (comments, votes, replies)
- Background job processing with Celery
- Export generation and variant creation

Usage:
    python manage.py seed_data
    python manage.py seed_data --users 50 --comments 200
    python manage.py seed_data --skip-processing  # Skip Celery jobs
    python manage.py seed_data --clear-existing   # Clear existing data first
"""

import os
import random
import shutil
from pathlib import Path
from typing import List, Dict, Any

from django.core.management.base import BaseCommand, CommandError
from django.core.files import File
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone
from django.db import transaction

from model_bakery import baker
from transcriber.models import (
    Transcription, Comment, CommentVote, FingeringVariant, 
    TabExport, Track, TrackVariant, PlayabilityMetrics
)
from transcriber.tasks import process_transcription, generate_export, generate_variants

User = get_user_model()


class Command(BaseCommand):
    help = 'Seed the database with comprehensive test data using model_bakery recipes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--users',
            type=int,
            default=25,
            help='Number of user accounts to create (default: 25)'
        )
        parser.add_argument(
            '--comments',
            type=int,
            default=150,
            help='Number of comments to generate (default: 150)'
        )
        parser.add_argument(
            '--skip-processing',
            action='store_true',
            help='Skip Celery background job processing'
        )
        parser.add_argument(
            '--clear-existing',
            action='store_true',
            help='Clear existing data before seeding (WARNING: destructive)'
        )
        parser.add_argument(
            '--no-jobs',
            action='store_true',
            help='Don\'t trigger any Celery jobs (useful for testing)'
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🎸 Starting RiffScribe database seeding...\n')
        )

        # Configuration from options
        self.user_count = options['users']
        self.comment_count = options['comments']
        self.skip_processing = options['skip_processing'] or options['no_jobs']
        self.clear_existing = options['clear_existing']

        # Sample file paths
        self.samples_dir = Path(settings.BASE_DIR) / 'samples'
        self.simple_riff = self.samples_dir / 'simple-riff.mp3'
        self.complex_riff = self.samples_dir / 'complex-riff.mp3'

        # Verify sample files exist
        if not self.simple_riff.exists() or not self.complex_riff.exists():
            raise CommandError(
                f'Sample files not found. Expected:\n'
                f'  - {self.simple_riff}\n'
                f'  - {self.complex_riff}'
            )

        try:
            with transaction.atomic():
                if self.clear_existing:
                    self._clear_existing_data()
                
                # Step 1: Create diverse user accounts
                self.stdout.write('👥 Creating user accounts...')
                users = self._create_users()
                
                # Step 2: Upload sample audio files as transcriptions
                self.stdout.write('🎵 Uploading sample audio files...')
                transcriptions = self._create_transcriptions(users)
                
                # Step 3: Generate community interaction
                self.stdout.write('💬 Generating community interactions...')
                self._generate_comments_and_votes(users, transcriptions)
                
                # Step 4: Create additional data (exports, variants)
                self.stdout.write('📄 Creating exports and variants...')
                self._create_additional_data(transcriptions)
                
                # Step 5: Process jobs with Celery (outside transaction)
                if not self.skip_processing:
                    self.stdout.write('⚙️  Queuing background processing jobs...')
                    
            # Process jobs outside transaction to avoid locking issues
            if not self.skip_processing:
                self._process_celery_jobs(transcriptions)
                
            self._print_summary()
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Seeding failed: {str(e)}')
            )
            raise

    def _clear_existing_data(self):
        """Clear existing data (WARNING: destructive operation)."""
        self.stdout.write('🗑️  Clearing existing data...')
        
        # Delete in dependency order
        CommentVote.objects.all().delete()
        Comment.objects.all().delete()
        TabExport.objects.all().delete()
        FingeringVariant.objects.all().delete()
        TrackVariant.objects.all().delete()
        Track.objects.all().delete()
        PlayabilityMetrics.objects.all().delete()
        Transcription.objects.all().delete()
        
        # Keep superuser, delete other users
        User.objects.filter(is_superuser=False).delete()
        
        self.stdout.write(self.style.WARNING('  ✓ Existing data cleared'))

    def _create_users(self) -> List[User]:
        """Create diverse user accounts using baker recipes."""
        users = []
        
        # Create diverse user personas
        user_personas = [
            {'username': 'guitar_pro_mike', 'first_name': 'Mike', 'last_name': 'Rodriguez', 'email': 'mike@example.com'},
            {'username': 'shredder_sarah', 'first_name': 'Sarah', 'last_name': 'Johnson', 'email': 'sarah@example.com'},
            {'username': 'tab_master_tom', 'first_name': 'Tom', 'last_name': 'Chen', 'email': 'tom@example.com'},
            {'username': 'riff_analyzer', 'first_name': 'Alex', 'last_name': 'Thompson', 'email': 'alex@example.com'},
            {'username': 'metal_detector', 'first_name': 'Jordan', 'last_name': 'Williams', 'email': 'jordan@example.com'},
            {'username': 'blues_scholar', 'first_name': 'Riley', 'last_name': 'Davis', 'email': 'riley@example.com'},
            {'username': 'jazz_fusion_fan', 'first_name': 'Casey', 'last_name': 'Miller', 'email': 'casey@example.com'},
            {'username': 'bedroom_producer', 'first_name': 'Sam', 'last_name': 'Garcia', 'email': 'sam@example.com'},
        ]
        
        # Create named personas first
        for i, persona in enumerate(user_personas):
            user = baker.make_recipe('transcriber.user', **persona)
            users.append(user)
            
            # Give some users premium status for variety
            if i % 3 == 0:
                profile = user.profile
                profile.subscription_tier = 'premium'
                profile.monthly_uploads_used = random.randint(5, 15)
                profile.save()
        
        # Create remaining random users
        remaining_count = max(0, self.user_count - len(user_personas))
        additional_users = baker.make_recipe('transcriber.user', _quantity=remaining_count)
        users.extend(additional_users)
        
        # Add some variety to user profiles
        for user in users[len(user_personas):]:  # Skip personas
            profile = user.profile
            profile.subscription_tier = random.choice(['free', 'free', 'premium'])
            profile.monthly_uploads_used = random.randint(0, 20)
            profile.save()
        
        self.stdout.write(f'  ✓ Created {len(users)} users ({len(user_personas)} personas, {remaining_count} random)')
        return users

    def _create_transcriptions(self, users: List[User]) -> List[Transcription]:
        """Upload and create transcriptions from sample audio files."""
        transcriptions = []
        
        sample_files = [
            {
                'path': self.simple_riff,
                'complexity': 'simple',
                'tempo': 90,
                'key': 'E Minor',
                'instruments': ['electric_guitar'],
                'user_count': 8  # More users will interact with simple riffs
            },
            {
                'path': self.complex_riff,
                'complexity': 'complex',
                'tempo': 140,
                'key': 'F# Minor',
                'instruments': ['electric_guitar', 'bass'],
                'user_count': 5  # Fewer users for complex content
            }
        ]
        
        for sample_config in sample_files:
            sample_path = sample_config['path']
            sample_users = random.sample(users, sample_config['user_count'])
            
            for i, user in enumerate(sample_users):
                # Create transcription with sample file
                transcription = baker.make_recipe(
                    'transcriber.transcription_completed_with_user',
                    user=user,
                    filename=f"{sample_path.stem}_upload_{i+1}.mp3",
                    complexity=sample_config['complexity'],
                    estimated_tempo=sample_config['tempo'],
                    estimated_key=sample_config['key'],
                    detected_instruments=sample_config['instruments'],
                    duration=random.uniform(30.0, 120.0),
                    status='completed'  # Start as completed for immediate interaction
                )
                
                # Copy sample file to transcription
                with open(sample_path, 'rb') as f:
                    transcription.original_audio.save(
                        transcription.filename,
                        File(f),
                        save=True
                    )
                
                transcriptions.append(transcription)
                
        # Create some additional random transcriptions (pending processing)
        selected_users = random.sample(users, 6)
        additional_transcriptions = []
        for user in selected_users:
            transcription = baker.make_recipe(
                'transcriber.transcription_with_user',
                user=user
            )
            additional_transcriptions.append(transcription)
        transcriptions.extend(additional_transcriptions)
        
        self.stdout.write(f'  ✓ Created {len(transcriptions)} transcriptions')
        self.stdout.write(f'    - {len([t for t in transcriptions if t.status == "completed"])} completed')
        self.stdout.write(f'    - {len([t for t in transcriptions if t.status == "pending"])} pending processing')
        
        return transcriptions

    def _generate_comments_and_votes(self, users: List[User], transcriptions: List[Transcription]):
        """Generate authentic community interactions."""
        completed_transcriptions = [t for t in transcriptions if t.status == 'completed']
        
        # Comment templates for variety
        comment_templates = [
            "Amazing transcription! The {technique} section is spot on.",
            "This helped me learn the song so much faster. Thank you!",
            "Love the {variant} variant - much more playable for beginners.",
            "The timing on measure {measure} seems a bit off, but overall great work!",
            "Perfect for practicing! The {tempo}bpm tempo is just right.",
            "This is exactly what I was looking for. Bookmarked!",
            "Could you add a slower variant? This is a bit challenging for me.",
            "Fantastic work on the {section} - really captures the original feel.",
            "The fingering suggestions make this so much easier to play.",
            "Brilliant! Now I can finally nail this riff.",
        ]
        
        anonymous_templates = [
            "Guest here - this is awesome!",
            "Thanks for sharing, really helpful!",
            "Could use more variants but overall good.",
            "Exactly what I needed for practice.",
            "This transcription rocks!",
        ]
        
        # Generate authenticated comments
        auth_comment_count = int(self.comment_count * 0.75)  # 75% authenticated
        for _ in range(auth_comment_count):
            transcription = random.choice(completed_transcriptions)
            user = random.choice(users)
            
            # Skip if user is the transcription owner
            if transcription.user == user:
                continue
                
            template = random.choice(comment_templates)
            content = template.format(
                technique=random.choice(['hammer-on', 'slide', 'bend', 'vibrato']),
                variant=random.choice(['easy', 'balanced', 'technical']),
                measure=random.randint(1, 8),
                tempo=random.randint(80, 120),
                section=random.choice(['intro', 'verse', 'chorus', 'solo', 'bridge'])
            )
            
            comment = baker.make_recipe(
                'transcriber.comment_authenticated',
                transcription=transcription,
                user=user,
                content=content
            )
            
            # Generate votes for this comment (80% chance of votes)
            if random.random() < 0.8:
                self._create_votes_for_comment(comment, users)
        
        # Generate anonymous comments  
        anon_comment_count = self.comment_count - auth_comment_count
        for _ in range(anon_comment_count):
            transcription = random.choice(completed_transcriptions)
            content = random.choice(anonymous_templates)
            
            baker.make_recipe(
                'transcriber.comment_anonymous',
                transcription=transcription,
                content=content,
                anonymous_name=f"GuitarFan{random.randint(100, 999)}"
            )
        
        # Generate some comment replies (10% of total comments)
        reply_count = int(self.comment_count * 0.1)
        parent_comments = Comment.objects.filter(parent__isnull=True)[:reply_count]
        
        for parent_comment in parent_comments:
            # Don't reply to own comments
            available_users = [u for u in users if u != parent_comment.user]
            if available_users:
                user = random.choice(available_users)
                reply_content = random.choice([
                    "I agree! Really well done.",
                    "Thanks for the feedback!",
                    "Have you tried the balanced variant?",
                    "Great point about the timing.",
                    "This helped me too!",
                ])
                
                baker.make_recipe(
                    'transcriber.comment_reply',
                    transcription=parent_comment.transcription,
                    user=user,
                    parent=parent_comment,
                    content=reply_content
                )
        
        total_comments = Comment.objects.count()
        total_votes = CommentVote.objects.count()
        
        self.stdout.write(f'  ✓ Generated {total_comments} comments')
        self.stdout.write(f'    - {total_comments - anon_comment_count - reply_count} authenticated')
        self.stdout.write(f'    - {anon_comment_count} anonymous')  
        self.stdout.write(f'    - {reply_count} replies')
        self.stdout.write(f'  ✓ Generated {total_votes} votes')

    def _create_votes_for_comment(self, comment: Comment, users: List[User]):
        """Create realistic voting patterns for a comment."""
        # Don't let users vote on their own comments
        available_voters = [u for u in users if u != comment.user]
        
        # Generate 1-5 votes per comment, weighted toward fewer votes
        vote_count = random.choices([1, 2, 3, 4, 5], weights=[40, 30, 15, 10, 5])[0]
        vote_count = min(vote_count, len(available_voters))
        
        voters = random.sample(available_voters, vote_count)
        
        for voter in voters:
            # 80% upvotes, 20% downvotes (realistic social media ratio)
            vote_type = random.choices(['up', 'down'], weights=[80, 20])[0]
            
            baker.make_recipe(
                'transcriber.comment_vote_up' if vote_type == 'up' else 'transcriber.comment_vote_down',
                comment=comment,
                user=voter
            )

    def _create_additional_data(self, transcriptions: List[Transcription]):
        """Create exports, variants, and additional metadata."""
        completed_transcriptions = [t for t in transcriptions if t.status == 'completed']
        
        # Create fingering variants for completed transcriptions
        for transcription in completed_transcriptions:
            # Create 2-4 variants per transcription
            variant_count = random.randint(2, 4)
            variant_types = random.sample(['easy', 'balanced', 'technical', 'original'], variant_count)
            
            for i, variant_type in enumerate(variant_types):
                baker.make_recipe(
                    f'transcriber.fingering_variant_{variant_type}',
                    transcription=transcription,
                    is_selected=(i == 0)  # First variant is selected
                )
        
        # Create some tab exports
        export_formats = ['musicxml', 'gp5', 'ascii', 'pdf']
        for transcription in random.sample(completed_transcriptions, min(8, len(completed_transcriptions))):
            format_choice = random.choice(export_formats)
            baker.make_recipe(
                f'transcriber.tab_export_{format_choice}',
                transcription=transcription
            )
        
        # Create playability metrics
        for transcription in completed_transcriptions:
            baker.make_recipe(
                'transcriber.playability_metrics',
                transcription=transcription
            )
        
        variant_count = FingeringVariant.objects.count()
        export_count = TabExport.objects.count()
        metrics_count = PlayabilityMetrics.objects.count()
        
        self.stdout.write(f'  ✓ Created {variant_count} fingering variants')
        self.stdout.write(f'  ✓ Created {export_count} tab exports')
        self.stdout.write(f'  ✓ Created {metrics_count} playability metrics')

    def _process_celery_jobs(self, transcriptions: List[Transcription]):
        """Queue background processing jobs with Celery."""
        pending_transcriptions = [t for t in transcriptions if t.status == 'pending']
        completed_transcriptions = [t for t in transcriptions if t.status == 'completed']
        
        job_count = 0
        
        # Process pending transcriptions
        for transcription in pending_transcriptions:
            try:
                task = process_transcription.delay(str(transcription.id))
                self.stdout.write(f'    ⚙️ Queued processing: {transcription.filename} (task: {task.id})')
                job_count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f'    ⚠️  Failed to queue processing for {transcription.filename}: {e}')
                )
        
        # Generate some exports for completed transcriptions
        export_jobs = random.sample(completed_transcriptions, min(4, len(completed_transcriptions)))
        for transcription in export_jobs:
            format_choice = random.choice(['musicxml', 'midi', 'pdf'])
            try:
                task = generate_export.delay(str(transcription.id), format_choice)
                self.stdout.write(f'    📄 Queued export: {transcription.filename} -> {format_choice} (task: {task.id})')
                job_count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f'    ⚠️  Failed to queue export for {transcription.filename}: {e}')
                )
        
        # Generate some variant regeneration jobs
        variant_jobs = random.sample(completed_transcriptions, min(3, len(completed_transcriptions)))
        for transcription in variant_jobs:
            preset = random.choice(['easy', 'technical', 'balanced'])
            try:
                task = generate_variants.delay(str(transcription.id), preset)
                self.stdout.write(f'    🎸 Queued variants: {transcription.filename} -> {preset} (task: {task.id})')
                job_count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f'    ⚠️  Failed to queue variants for {transcription.filename}: {e}')
                )
        
        self.stdout.write(f'  ✓ Queued {job_count} background jobs')
        self.stdout.write('    💡 Use "celery -A riffscribe worker" to process these jobs')

    def _print_summary(self):
        """Print comprehensive summary of seeded data."""
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('🎉 SEEDING COMPLETED SUCCESSFULLY!'))
        self.stdout.write('='*60)
        
        # Data summary
        user_count = User.objects.count()
        transcription_count = Transcription.objects.count()
        comment_count = Comment.objects.count()
        vote_count = CommentVote.objects.count()
        variant_count = FingeringVariant.objects.count()
        export_count = TabExport.objects.count()
        
        self.stdout.write(f'📊 DATA SUMMARY:')
        self.stdout.write(f'  👥 Users: {user_count}')
        self.stdout.write(f'  🎵 Transcriptions: {transcription_count}')
        self.stdout.write(f'     - Completed: {Transcription.objects.filter(status="completed").count()}')
        self.stdout.write(f'     - Pending: {Transcription.objects.filter(status="pending").count()}')
        self.stdout.write(f'  💬 Comments: {comment_count}')
        self.stdout.write(f'  👍 Votes: {vote_count}')
        self.stdout.write(f'  🎸 Variants: {variant_count}')
        self.stdout.write(f'  📄 Exports: {export_count}')
        
        self.stdout.write(f'\n🚀 WHAT\'S NEXT:')
        self.stdout.write(f'  1. Start Celery worker: celery -A riffscribe worker')
        self.stdout.write(f'  2. Visit the app to see your seeded data!')
        self.stdout.write(f'  3. Check the library page for sample transcriptions')
        self.stdout.write(f'  4. Explore comments and community features')
        
        if not self.skip_processing:
            pending_count = Transcription.objects.filter(status='pending').count()
            if pending_count > 0:
                self.stdout.write(f'  📌 {pending_count} transcriptions are queued for processing')
        
        self.stdout.write('\n💡 TIP: Use --clear-existing to reset and re-seed anytime')
        self.stdout.write('='*60 + '\n')
