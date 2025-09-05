"""
Model Bakery recipes for the transcriber app.

Usage examples:
    from model_bakery import baker
    t = baker.make_recipe('transcriber.transcription_completed')
    v = baker.make_recipe('transcriber.fingering_variant_easy', transcription=t)

Notes:
- We intentionally avoid a direct UserProfile recipe because a post_save signal
  auto-creates a profile for every User. Use the `user` recipe and access
  `user.profile` instead; customize fields there in tests if needed.
"""

import uuid
from datetime import date
from itertools import cycle

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.utils import timezone

from model_bakery.recipe import Recipe, seq, foreign_key, related

from .models import (
    Transcription,
    TabExport,
    PlayabilityMetrics,
    FingeringVariant,
    FingeringMeasureStat,
    Track,
    TrackVariant,
    MultiTrackExport,
    Comment,
    CommentVote,
)


# -----------------------------------------------------------------------------
# Helpers (callables) used by recipes
# -----------------------------------------------------------------------------

def _fake_audio_file():
    """Return a small in-memory audio-ish file suitable for FileField."""
    name = f"sample_{uuid.uuid4().hex[:8]}.wav"
    # Minimal bytes; tests don't parse actual audio
    return ContentFile(b"RIFF\x00\x00WAVEdata", name)


def _fake_gp5_file():
    name = f"sample_{uuid.uuid4().hex[:8]}.gp5"
    return ContentFile(b"GP5FILE", name)


def _fake_midi_file():
    name = f"sample_{uuid.uuid4().hex[:8]}.mid"
    return ContentFile(b'MThd\x00\x00', name)


def _fake_zip_file():
    name = f"sample_{uuid.uuid4().hex[:8]}.zip"
    return ContentFile(b'PK\x03\x04', name)


def _fake_pdf_file():
    name = f"sample_{uuid.uuid4().hex[:8]}.pdf"
    return ContentFile(b'%PDF-1.4', name)


def _fake_txt_file():
    name = f"sample_{uuid.uuid4().hex[:8]}.txt"
    return ContentFile(b'ASCII TAB\nE|---\nB|---\n', name)


def _sample_midi_notes():
    """A tiny, serializable MIDI-like notes payload."""
    return {
        'notes': [
            {'start_time': 0.00, 'end_time': 0.25, 'pitch': 329.63, 'midi_note': 64, 'velocity': 90, 'confidence': 0.9},
            {'start_time': 0.25, 'end_time': 0.50, 'pitch': 349.23, 'midi_note': 65, 'velocity': 88, 'confidence': 0.85},
            {'start_time': 0.50, 'end_time': 0.75, 'pitch': 392.00, 'midi_note': 67, 'velocity': 92, 'confidence': 0.9},
            {'start_time': 0.75, 'end_time': 1.00, 'pitch': 440.00, 'midi_note': 69, 'velocity': 95, 'confidence': 0.92},
        ]
    }


def _sample_tab_data():
    """Tab data in the format used across the app (see ExportManager/TabGenerator)."""
    return {
        'tempo': 120,
        'time_signature': '4/4',
        'tuning': [40, 45, 50, 55, 59, 64],
        'measures': [
            {
                'number': 1,
                'start_time': 0.0,
                'notes': [
                    {'string': 1, 'fret': 0, 'time': 0.00, 'duration': 0.25, 'velocity': 80},
                    {'string': 2, 'fret': 2, 'time': 0.25, 'duration': 0.25, 'velocity': 82},
                    {'string': 3, 'fret': 2, 'time': 0.50, 'duration': 0.25, 'velocity': 84},
                    {'string': 1, 'fret': 0, 'time': 0.75, 'duration': 0.25, 'velocity': 86},
                ],
            },
            {
                'number': 2,
                'start_time': 1.0,
                'notes': [
                    {'string': 2, 'fret': 3, 'time': 1.00, 'duration': 0.25, 'velocity': 82},
                    {'string': 3, 'fret': 2, 'time': 1.25, 'duration': 0.25, 'velocity': 84},
                ],
            },
        ],
        'techniques_used': {'hammer_on': 1, 'slide': 0},
    }


def _sample_whisper_analysis():
    return {
        'status': 'success',
        'analysis': 'Electric guitar with steady 4/4 rhythm, key of E minor.',
        'musical_elements': {
            'instruments': ['electric guitar'],
            'techniques': ['hammer', 'slide'],
        },
        'audio_features': {'tempo': 120, 'estimated_key': 'Em'},
        'confidence': 0.88,
    }


# -----------------------------------------------------------------------------
# Core/simple objects
# -----------------------------------------------------------------------------

User = get_user_model()

user = Recipe(
    User,
    username=seq('user_'),
    email=seq('user', suffix='@example.com'),
    first_name='Test',
    last_name='User',
    is_active=True,
)


# -----------------------------------------------------------------------------
# Transcriptions
# -----------------------------------------------------------------------------

transcription_basic = Recipe(
    Transcription,
    filename=seq('riff_', suffix='.wav'),
    status='pending',
    duration=2.5,
    sample_rate=22050,
    channels=1,
    estimated_tempo=120,
    estimated_key='E Minor',
    complexity='simple',
    detected_instruments=['guitar'],
)

transcription_completed = transcription_basic.extend(
    status='completed',
    midi_data=_sample_midi_notes,
    guitar_notes=_sample_tab_data,
    whisper_analysis=_sample_whisper_analysis,
)

transcription_failed = transcription_basic.extend(
    status='failed',
    error_message='Processing error for testing',
)

# Ownership variants
transcription_with_user = transcription_basic.extend(
    user=foreign_key(user),
)

transcription_completed_with_user = transcription_completed.extend(
    user=foreign_key(user),
)


# -----------------------------------------------------------------------------
# Variants and Metrics
# -----------------------------------------------------------------------------

fingering_variant_easy = Recipe(
    FingeringVariant,
    transcription=foreign_key(transcription_completed),
    variant_name='easy',
    difficulty_score=20.0,
    playability_score=85.0,
    tab_data=_sample_tab_data,
    removed_techniques={'bends': 0, 'slides': 0},
    config={'preset': 'easy'},
    is_selected=True,
)

fingering_variant_balanced = fingering_variant_easy.extend(
    variant_name='balanced',
    difficulty_score=40.0,
    playability_score=70.0,
    is_selected=False,
    config={'preset': 'balanced'},
)

fingering_variant_technical = fingering_variant_easy.extend(
    variant_name='technical',
    difficulty_score=65.0,
    playability_score=45.0,
    is_selected=False,
    config={'preset': 'technical'},
)

fingering_variant_original = fingering_variant_easy.extend(
    variant_name='original',
    difficulty_score=50.0,
    playability_score=55.0,
    is_selected=False,
    config={'preset': 'original'},
)

fingering_measure_stat = Recipe(
    FingeringMeasureStat,
    variant=foreign_key(fingering_variant_easy),
    measure_number=seq(1),
    avg_fret=5.0,
    max_jump=3,
    chord_span=2,
    string_crossings=1,
)

playability_metrics = Recipe(
    PlayabilityMetrics,
    transcription=foreign_key(transcription_completed, one_to_one=True),
    playability_score=80.0,
    recommended_skill_level='beginner',
    max_fret_span=4,
    position_changes=2,
    open_strings_used=3,
    problem_sections=[{'measure': 2, 'reason': 'wide stretch'}],
    slow_tempo_suggestion=90,
)


# -----------------------------------------------------------------------------
# Tracks and multi-track exports
# -----------------------------------------------------------------------------

track_drums = Recipe(
    Track,
    transcription=foreign_key(transcription_completed),
    track_type='drums',
    instrument_type='drums',
    track_name='Drums',
    track_order=0,
    volume_level=0.2,
    prominence_score=0.5,
    midi_data={'tempo': 120, 'drum_hits': []},
    guitar_notes={'drum_tab': 'HH|x-x-x-x-|', 'format': 'drum_notation', 'measures': []},
    is_processed=True,
)

track_bass = track_drums.extend(
    track_type='bass',
    instrument_type='bass',
    track_name='Bass',
    track_order=1,
)

track_guitar = track_drums.extend(
    track_type='other',
    instrument_type='electric_guitar',
    track_name='Guitar',
    track_order=2,
    guitar_notes=_sample_tab_data,
)

track_original = track_drums.extend(
    track_type='original',
    instrument_type=None,
    track_name='Original Mix',
    track_order=4,
)

track_variant_easy = Recipe(
    TrackVariant,
    track=foreign_key(track_guitar),
    variant_name='easy',
    difficulty_score=25.0,
    playability_score=80.0,
    tab_data=_sample_tab_data,
    removed_techniques=None,
    config={'preset': 'easy'},
    is_selected=True,
)

track_variant_balanced = track_variant_easy.extend(
    variant_name='balanced',
    difficulty_score=45.0,
    playability_score=65.0,
    is_selected=False,
    config={'preset': 'balanced'},
)

multi_export_musicxml = Recipe(
    MultiTrackExport,
    transcription=foreign_key(transcription_completed),
    format='musicxml',
    export_settings={'parts': ['guitar', 'drums']},
)

multi_export_midi = Recipe(
    MultiTrackExport,
    transcription=foreign_key(transcription_completed),
    format='midi',
    export_settings={'quantize': True},
)

multi_export_stems = Recipe(
    MultiTrackExport,
    transcription=foreign_key(transcription_completed),
    format='stems',
    export_settings={'bitrate': '128k'},
)


# -----------------------------------------------------------------------------
# Exports
# -----------------------------------------------------------------------------

tab_export_musicxml = Recipe(
    TabExport,
    transcription=foreign_key(transcription_completed),
    format='musicxml',
)

tab_export_gp5 = tab_export_musicxml.extend(
    format='gp5',
)

tab_export_ascii = tab_export_musicxml.extend(
    format='ascii',
)

tab_export_pdf = tab_export_musicxml.extend(
    format='pdf',
)


# -----------------------------------------------------------------------------
# Comments and voting
# -----------------------------------------------------------------------------

comment_authenticated = Recipe(
    Comment,
    transcription=foreign_key(transcription_completed),
    user=foreign_key(user),
    content=seq('Great take #'),
    is_approved=True,
    is_flagged=False,
    upvotes_count=0,
    downvotes_count=0,
)

comment_anonymous = Recipe(
    Comment,
    transcription=foreign_key(transcription_completed),
    user=None,
    anonymous_name=seq('Guest'),
    anonymous_email=seq('guest', suffix='@example.com'),
    content=seq('Anonymous feedback #'),
    is_approved=True,
)

comment_vote_up = Recipe(
    CommentVote,
    comment=foreign_key(comment_authenticated),
    user=foreign_key(user),
    vote_type='up',
)

comment_vote_down = comment_vote_up.extend(
    vote_type='down',
)

comment_reply = Recipe(
    Comment,
    transcription=foreign_key(transcription_completed),
    user=foreign_key(user),
    parent=foreign_key(comment_authenticated),
    content=seq('Reply #'),
    is_approved=True,
)


# -----------------------------------------------------------------------------
# Additional variants pack (useful for bulk generation in tests)
# -----------------------------------------------------------------------------

# Cycle different complexity labels for completed transcriptions
transcription_varied = transcription_completed.extend(
    complexity=cycle(['simple', 'moderate', 'complex']),
    detected_instruments=['guitar', 'bass'],
)


