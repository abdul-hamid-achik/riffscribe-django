"""
Management command to generate fingering variants for transcriptions
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from transcriber.models import Transcription, FingeringVariant
from transcriber.services.variant_generator import VariantGenerator
from transcriber.services.fingering_optimizer import FINGERING_PRESETS
import uuid


class Command(BaseCommand):
    """Generate fingering variants for transcriptions"""
    
    help = 'Generate fingering variants for one or more transcriptions'
    
    def add_arguments(self, parser):
        """Add command arguments"""
        parser.add_argument(
            'transcription_id',
            type=str,
            help='UUID of the transcription (or "all" for all completed transcriptions)'
        )
        
        parser.add_argument(
            '--preset',
            type=str,
            choices=['easy', 'balanced', 'technical', 'original', 'all'],
            default='all',
            help='Which preset variant to generate (default: all)'
        )
        
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force regeneration even if variants already exist'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes'
        )
        
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output'
        )
        
    def handle(self, *args, **options):
        """Execute the command"""
        transcription_id = options['transcription_id']
        preset = options['preset']
        force = options['force']
        dry_run = options['dry_run']
        verbose = options['verbose']
        
        # Get transcriptions to process
        if transcription_id.lower() == 'all':
            transcriptions = Transcription.objects.filter(status='completed')
            if not transcriptions.exists():
                self.stdout.write(self.style.WARNING('No completed transcriptions found'))
                return
            self.stdout.write(f'Found {transcriptions.count()} completed transcriptions')
        else:
            try:
                transcription_id = uuid.UUID(transcription_id)
                transcriptions = Transcription.objects.filter(id=transcription_id)
                if not transcriptions.exists():
                    raise CommandError(f'Transcription {transcription_id} not found')
            except ValueError:
                raise CommandError(f'Invalid UUID: {transcription_id}')
        
        # Process each transcription
        success_count = 0
        error_count = 0
        
        for transcription in transcriptions:
            try:
                self.process_transcription(transcription, preset, force, dry_run, verbose)
                success_count += 1
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f'Error processing {transcription.filename}: {str(e)}')
                )
        
        # Summary
        self.stdout.write('')
        if success_count:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully processed {success_count} transcription(s)')
            )
        if error_count:
            self.stdout.write(
                self.style.ERROR(f'Failed to process {error_count} transcription(s)')
            )
            
    def process_transcription(self, transcription, preset, force, dry_run, verbose):
        """Process a single transcription"""
        
        # Check if transcription has required data
        if not transcription.midi_data:
            raise CommandError(f'{transcription.filename}: No MIDI data available')
            
        if not transcription.guitar_notes:
            raise CommandError(f'{transcription.filename}: No guitar notes available')
            
        # Check existing variants
        existing_variants = transcription.variants.all()
        if existing_variants.exists() and not force:
            if verbose:
                self.stdout.write(
                    f'{transcription.filename}: Skipping, {existing_variants.count()} variants already exist (use --force to regenerate)'
                )
            return
            
        if verbose:
            self.stdout.write(f'\nProcessing: {transcription.filename}')
            self.stdout.write(f'  Status: {transcription.status}')
            self.stdout.write(f'  Tempo: {transcription.estimated_tempo} BPM')
            self.stdout.write(f'  Key: {transcription.estimated_key}')
            
        if dry_run:
            self.stdout.write(self.style.WARNING('  [DRY RUN] Would generate variants'))
            if existing_variants.exists():
                self.stdout.write(f'  Would delete {existing_variants.count()} existing variants')
            if preset == 'all':
                self.stdout.write(f'  Would generate 4 variants: easy, balanced, technical, original')
            else:
                self.stdout.write(f'  Would generate {preset} variant')
            return
            
        # Generate variants
        generator = VariantGenerator(transcription)
        
        with transaction.atomic():
            if preset == 'all':
                # Delete existing variants if forcing
                if force and existing_variants.exists():
                    deleted_count = existing_variants.count()
                    existing_variants.delete()
                    if verbose:
                        self.stdout.write(f'  Deleted {deleted_count} existing variants')
                        
                # Generate all variants
                variants = generator.generate_all_variants()
                self.stdout.write(
                    self.style.SUCCESS(f'  Generated {len(variants)} variants for {transcription.filename}')
                )
                
                if verbose:
                    for variant in variants:
                        self.stdout.write(
                            f'    - {variant.get_variant_name_display()}: '
                            f'Playability {variant.playability_score:.0f}%, '
                            f'Difficulty {variant.difficulty_score:.0f}%'
                            f'{" [SELECTED]" if variant.is_selected else ""}'
                        )
                        
            else:
                # Generate specific preset
                if preset not in FINGERING_PRESETS:
                    raise CommandError(f'Unknown preset: {preset}')
                    
                # Delete existing variant of this preset if forcing
                existing = existing_variants.filter(variant_name=preset).first()
                if existing and force:
                    existing.delete()
                    if verbose:
                        self.stdout.write(f'  Deleted existing {preset} variant')
                        
                weights = FINGERING_PRESETS[preset]
                variant = generator.generate_variant(preset, weights)
                
                if variant:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'  Generated {preset} variant: '
                            f'Playability {variant.playability_score:.0f}%, '
                            f'Difficulty {variant.difficulty_score:.0f}%'
                        )
                    )
                    
                    # If this is the only variant, select it
                    if transcription.variants.count() == 1:
                        variant.is_selected = True
                        variant.save()
                        generator._update_parent_transcription(variant)
                        if verbose:
                            self.stdout.write('  Selected as default variant')
                else:
                    raise CommandError(f'Failed to generate {preset} variant')
                    
        # Show metrics if verbose
        if verbose and hasattr(transcription, 'metrics'):
            metrics = transcription.metrics
            self.stdout.write('  Metrics:')
            self.stdout.write(f'    - Recommended skill: {metrics.recommended_skill_level}')
            self.stdout.write(f'    - Max fret span: {metrics.max_fret_span} frets')
            self.stdout.write(f'    - Position changes: {metrics.position_changes}')
            self.stdout.write(f'    - Open strings used: {metrics.open_strings_used}')
            if metrics.slow_tempo_suggestion:
                self.stdout.write(f'    - Practice tempo: {metrics.slow_tempo_suggestion} BPM')