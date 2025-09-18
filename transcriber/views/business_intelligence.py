"""
Business Intelligence Views
Provides detailed analytics and insights for transcriptions
"""
from django.shortcuts import get_object_or_404, render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Avg, Count, Sum, Min, Max
from datetime import timedelta
import json

from ..models import Transcription, Track, ConversionEvent, UsageAnalytics, UserProfile
from ..decorators import admin_required
from ..services.metrics_service import get_transcription_progress, metrics_service


@require_http_methods(["GET"])
def transcription_analytics(request, pk):
    """
    Detailed analytics view for a transcription - shows what users get for their money
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    # Get detailed analysis
    tracks = transcription.tracks.all()
    
    # Build comprehensive analytics data
    analytics = {
        'transcription': {
            'id': str(transcription.id),
            'filename': transcription.filename,
            'duration': transcription.duration_formatted,
            'tempo': transcription.estimated_tempo,
            'key': transcription.estimated_key,
            'complexity': transcription.complexity,
            'accuracy_score': transcription.accuracy_score,
            'processing_model': transcription.processing_model_version,
            'models_used': transcription.models_used
        },
        'instruments': [],
        'quality_metrics': {},
        'business_value': {}
    }
    
    # Per-instrument analysis
    total_confidence = 0
    total_notes = 0
    
    for track in tracks:
        instrument_data = {
            'name': track.display_name,
            'type': track.instrument_type,
            'confidence': track.confidence_score,
            'notes_count': len(track.guitar_notes) if track.guitar_notes else 0,
            'is_processed': track.is_processed,
            'processing_error': track.processing_error
        }
        
        # Add detailed note analysis
        if track.guitar_notes and isinstance(track.guitar_notes, list):
            notes = track.guitar_notes
            if notes:
                note_durations = [note.get('duration', 0) for note in notes]
                instrument_data.update({
                    'avg_note_duration': sum(note_durations) / len(note_durations),
                    'pitch_range': {
                        'lowest': min(note.get('midi_note', 60) for note in notes),
                        'highest': max(note.get('midi_note', 60) for note in notes)
                    },
                    'velocity_range': {
                        'softest': min(note.get('velocity', 80) for note in notes),
                        'loudest': max(note.get('velocity', 80) for note in notes)
                    }
                })
                total_notes += len(notes)
        
        analytics['instruments'].append(instrument_data)
        total_confidence += track.confidence_score or 0
    
    # Overall quality metrics
    if tracks.exists():
        analytics['quality_metrics'] = {
            'overall_confidence': total_confidence / tracks.count(),
            'total_notes_detected': total_notes,
            'instruments_detected': tracks.count(),
            'processing_success_rate': tracks.filter(is_processed=True).count() / tracks.count(),
            'accuracy_breakdown': {
                track.instrument_type: track.confidence_score 
                for track in tracks if track.confidence_score
            }
        }
    
    # Business value proposition
    analytics['business_value'] = {
        'formats_available': ['MusicXML (Free Preview)', 'GP5 (Premium)', 'MIDI (Premium)', 'ASCII Tabs (Premium)'],
        'estimated_time_saved': f"{transcription.duration / 60 * 20:.0f} minutes" if transcription.duration else "N/A",
        'professional_accuracy': f"{(analytics['quality_metrics'].get('overall_confidence', 0.8) * 100):.0f}%",
        'instruments_separated': len(analytics['instruments'])
    }
    
    return JsonResponse(analytics, indent=2)


@require_http_methods(["GET"])
@admin_required
def conversion_funnel_analysis(request):
    """
    Analyze conversion funnel for business optimization
    """
    # Get data for last 30 days
    start_date = timezone.now() - timedelta(days=30)
    
    # Funnel stages
    total_uploads = Transcription.objects.filter(created_at__gte=start_date).count()
    
    completed_transcriptions = Transcription.objects.filter(
        created_at__gte=start_date,
        status='completed'
    ).count()
    
    export_attempts = ConversionEvent.objects.filter(
        created_at__gte=start_date,
        event_type='attempted_export'
    ).count()
    
    signups = ConversionEvent.objects.filter(
        created_at__gte=start_date,
        event_type='signed_up'
    ).count()
    
    premium_upgrades = ConversionEvent.objects.filter(
        created_at__gte=start_date,
        event_type='upgraded_premium'
    ).count()
    
    successful_exports = ConversionEvent.objects.filter(
        created_at__gte=start_date,
        event_type='downloaded_gp5'  # Any successful export
    ).count()
    
    # Calculate conversion rates
    completion_rate = (completed_transcriptions / total_uploads * 100) if total_uploads > 0 else 0
    export_attempt_rate = (export_attempts / completed_transcriptions * 100) if completed_transcriptions > 0 else 0
    signup_rate = (signups / export_attempts * 100) if export_attempts > 0 else 0
    premium_conversion_rate = (premium_upgrades / signups * 100) if signups > 0 else 0
    
    # Revenue metrics
    total_premium_users = UserProfile.objects.filter(
        subscription_tier__in=['premium', 'professional']
    ).count()
    
    monthly_revenue_estimate = total_premium_users * 9.99  # Assuming $9.99/month
    
    funnel_data = {
        'period': '30 days',
        'funnel_stages': {
            'uploads': total_uploads,
            'completed_transcriptions': completed_transcriptions,
            'export_attempts': export_attempts,
            'signups': signups,
            'premium_upgrades': premium_upgrades,
            'successful_exports': successful_exports
        },
        'conversion_rates': {
            'completion_rate': f"{completion_rate:.1f}%",
            'export_attempt_rate': f"{export_attempt_rate:.1f}%",
            'signup_rate': f"{signup_rate:.1f}%",
            'premium_conversion_rate': f"{premium_conversion_rate:.1f}%"
        },
        'revenue_metrics': {
            'total_premium_users': total_premium_users,
            'estimated_monthly_revenue': f"${monthly_revenue_estimate:.2f}",
            'avg_revenue_per_user': f"${monthly_revenue_estimate / max(total_premium_users, 1):.2f}"
        },
        'recommendations': []
    }
    
    # Generate recommendations
    if completion_rate < 80:
        funnel_data['recommendations'].append("Low completion rate - improve transcription accuracy or user experience")
    
    if export_attempt_rate < 50:
        funnel_data['recommendations'].append("Low export attempt rate - users not seeing value in results")
    
    if signup_rate < 30:
        funnel_data['recommendations'].append("Low signup rate - improve signup incentives or reduce friction")
    
    if premium_conversion_rate < 10:
        funnel_data['recommendations'].append("Low premium conversion - enhance premium value proposition")
    
    return JsonResponse(funnel_data, indent=2)


@require_http_methods(["GET"])
@admin_required
def accuracy_dashboard(request):
    """
    Dashboard showing transcription accuracy across different models and instruments
    """
    # Get accuracy data for last 7 days
    start_date = timezone.now() - timedelta(days=7)
    
    recent_transcriptions = Transcription.objects.filter(
        created_at__gte=start_date,
        status='completed',
        accuracy_score__isnull=False
    )
    
    # Overall accuracy metrics
    overall_stats = recent_transcriptions.aggregate(
        avg_accuracy=Avg('accuracy_score'),
        min_accuracy=Min('accuracy_score'),
        max_accuracy=Max('accuracy_score'),
        total_transcriptions=Count('id')
    )
    
    # Accuracy by model version
    model_accuracy = recent_transcriptions.values('processing_model_version').annotate(
        avg_accuracy=Avg('accuracy_score'),
        count=Count('id')
    ).order_by('-avg_accuracy')
    
    # Accuracy by complexity
    complexity_accuracy = recent_transcriptions.values('complexity').annotate(
        avg_accuracy=Avg('accuracy_score'),
        count=Count('id')
    ).order_by('-avg_accuracy')
    
    # Per-instrument accuracy (from tracks)
    instrument_stats = {}
    for transcription in recent_transcriptions:
        for track in transcription.tracks.all():
            instrument = track.instrument_type
            if instrument not in instrument_stats:
                instrument_stats[instrument] = {
                    'total': 0,
                    'confidence_sum': 0,
                    'accuracy_sum': 0
                }
            
            instrument_stats[instrument]['total'] += 1
            instrument_stats[instrument]['confidence_sum'] += track.confidence_score or 0
            instrument_stats[instrument]['accuracy_sum'] += transcription.accuracy_score or 0
    
    # Calculate averages
    for instrument, stats in instrument_stats.items():
        if stats['total'] > 0:
            stats['avg_confidence'] = stats['confidence_sum'] / stats['total']
            stats['avg_accuracy'] = stats['accuracy_sum'] / stats['total']
    
    dashboard_data = {
        'period': '7 days',
        'overall': overall_stats,
        'by_model': list(model_accuracy),
        'by_complexity': list(complexity_accuracy),
        'by_instrument': instrument_stats,
        'top_performers': list(recent_transcriptions.order_by('-accuracy_score')[:5].values(
            'id', 'filename', 'accuracy_score', 'processing_model_version'
        )),
        'improvement_opportunities': []
    }
    
    # Generate improvement suggestions
    if overall_stats['avg_accuracy'] and overall_stats['avg_accuracy'] < 0.85:
        dashboard_data['improvement_opportunities'].append("Overall accuracy below target (85%)")
    
    for instrument, stats in instrument_stats.items():
        if stats.get('avg_accuracy', 0) < 0.8:
            dashboard_data['improvement_opportunities'].append(f"{instrument} accuracy needs improvement")
    
    return JsonResponse(dashboard_data, indent=2)


@require_http_methods(["GET"])
def user_transcription_insights(request, pk):
    """
    Show detailed insights about a transcription to demonstrate value to users
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    # Build user-friendly insights
    insights = {
        'summary': {
            'song': transcription.filename,
            'duration': transcription.duration_formatted,
            'complexity': transcription.complexity.title() if transcription.complexity else 'Unknown',
            'tempo': f"{transcription.estimated_tempo} BPM" if transcription.estimated_tempo else 'Unknown',
            'key': transcription.estimated_key or 'Unknown',
            'accuracy': f"{(transcription.accuracy_score or 0.8) * 100:.0f}%" 
        },
        'instruments_detected': [],
        'technical_details': {},
        'export_options': {},
        'learning_insights': []
    }
    
    # Instrument analysis
    tracks = transcription.tracks.all()
    for track in tracks:
        instrument_info = {
            'instrument': track.instrument_type.replace('_', ' ').title(),
            'confidence': f"{(track.confidence_score or 0.8) * 100:.0f}%",
            'notes_detected': len(track.guitar_notes) if track.guitar_notes else 0,
            'quality': 'Excellent' if (track.confidence_score or 0.8) > 0.9 
                      else 'Good' if (track.confidence_score or 0.8) > 0.7 
                      else 'Fair'
        }
        insights['instruments_detected'].append(instrument_info)
    
    # Technical details for music enthusiasts
    if transcription.whisper_analysis:
        analysis = transcription.whisper_analysis
        insights['technical_details'] = {
            'models_used': analysis.get('models_used', {}),
            'processing_time': f"{sum(analysis.get('processing_times', {}).values()):.1f} seconds",
            'ai_confidence': f"{(analysis.get('overall_confidence', 0.8) * 100):.0f}%",
            'service_version': analysis.get('service_version', 'advanced_v2.0')
        }
    
    # Export options based on user tier
    user_can_export = request.user.is_authenticated and request.user.profile.can_export_files()
    
    insights['export_options'] = {
        'musicxml_preview': {
            'available': True,
            'description': 'Interactive web player with sheet music',
            'cost': 'Free'
        },
        'guitar_pro_5': {
            'available': user_can_export,
            'description': 'Professional tablature for Guitar Pro software',
            'cost': 'Premium' if not user_can_export else 'Included'
        },
        'midi_file': {
            'available': user_can_export,
            'description': 'Compatible with all DAWs and music software',
            'cost': 'Premium' if not user_can_export else 'Included'
        },
        'ascii_tabs': {
            'available': user_can_export,
            'description': 'Plain text tabs for forums and sharing',
            'cost': 'Premium' if not user_can_export else 'Included'
        },
        'audio_stems': {
            'available': user_can_export and tracks.count() > 1,
            'description': 'Separated instrument tracks for remixing',
            'cost': 'Premium' if not user_can_export else 'Included'
        }
    }
    
    # Learning insights based on the transcription
    if transcription.complexity == 'simple':
        insights['learning_insights'].append("Great song for beginners! Clean, simple chord progression.")
    elif transcription.complexity == 'complex':
        insights['learning_insights'].append("Advanced song with complex arrangements. Perfect for skill building!")
    
    if transcription.estimated_tempo:
        tempo = transcription.estimated_tempo
        if tempo < 100:
            insights['learning_insights'].append(f"Slow tempo ({tempo} BPM) makes it easier to learn.")
        elif tempo > 140:
            insights['learning_insights'].append(f"Fast tempo ({tempo} BPM) - great for building speed!")
    
    # Add value proposition for free users
    if not user_can_export:
        insights['upgrade_value'] = {
            'current_view': 'You can see all the analysis for free!',
            'premium_gets': [
                'Download Guitar Pro 5 files',
                'Export to MIDI for your DAW',
                'Get ASCII tabs for sharing',
                'Access separated instrument tracks',
                'Commercial use rights'
            ],
            'price': '$9.99/month',
            'trial': '3 free exports to try premium features'
        }
    
    return JsonResponse(insights, indent=2)


@require_http_methods(["GET"])
@admin_required
def revenue_analytics(request):
    """
    Revenue and business analytics dashboard
    """
    # Time periods
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    # User metrics
    total_users = UserProfile.objects.count()
    premium_users = UserProfile.objects.filter(
        subscription_tier__in=['premium', 'professional']
    ).count()
    
    free_users = total_users - premium_users
    
    # Revenue calculations
    premium_revenue = premium_users * 9.99  # $9.99/month
    professional_revenue = UserProfile.objects.filter(
        subscription_tier='professional'
    ).count() * 29.99  # $29.99/month
    
    total_monthly_revenue = premium_revenue + professional_revenue
    
    # Usage analytics
    recent_usage = UsageAnalytics.objects.filter(date__gte=week_ago)
    
    # Conversion metrics
    recent_conversions = ConversionEvent.objects.filter(created_at__gte=week_ago)
    
    conversion_stats = {}
    for event_type in ['viewed_transcription', 'attempted_export', 'signed_up', 'upgraded_premium']:
        conversion_stats[event_type] = recent_conversions.filter(event_type=event_type).count()
    
    # Calculate key business metrics
    conversion_rate = (
        (conversion_stats['upgraded_premium'] / conversion_stats['attempted_export'] * 100) 
        if conversion_stats['attempted_export'] > 0 else 0
    )
    
    churn_rate = 0  # TODO: Implement churn tracking
    
    analytics = {
        'revenue': {
            'monthly_recurring': f"${total_monthly_revenue:.2f}",
            'premium_users': premium_users,
            'professional_users': UserProfile.objects.filter(subscription_tier='professional').count(),
            'free_users': free_users,
            'average_revenue_per_user': f"${total_monthly_revenue / max(premium_users, 1):.2f}"
        },
        'conversion': {
            'funnel': conversion_stats,
            'conversion_rate': f"{conversion_rate:.1f}%",
            'signup_to_premium': f"{(conversion_stats['upgraded_premium'] / max(conversion_stats['signed_up'], 1) * 100):.1f}%"
        },
        'usage': {
            'total_transcriptions_week': recent_usage.aggregate(
                total=Sum('transcriptions_created')
            )['total'] or 0,
            'total_exports_week': recent_usage.aggregate(
                total=Sum('exports_completed')
            )['total'] or 0,
            'avg_accuracy': recent_usage.aggregate(
                avg=Avg('avg_accuracy_score')
            )['avg'] or 0.8
        },
        'growth_opportunities': []
    }
    
    # Growth recommendations
    if conversion_rate < 5:
        analytics['growth_opportunities'].append("Low conversion rate - improve premium value proposition")
    
    if free_users > premium_users * 10:
        analytics['growth_opportunities'].append("Large free user base - opportunity for conversion campaigns")
    
    if analytics['usage']['avg_accuracy'] < 0.85:
        analytics['growth_opportunities'].append("Accuracy below 85% - invest in better models")
    
    return JsonResponse(analytics, indent=2)


@require_http_methods(["GET"]) 
@login_required
def my_transcription_history(request):
    """
    Show user their transcription history with insights
    """
    user_transcriptions = Transcription.objects.filter(
        user=request.user
    ).order_by('-created_at')[:20]  # Last 20
    
    # Calculate user stats
    total_duration = sum(
        t.duration for t in user_transcriptions if t.duration
    ) or 0
    
    avg_accuracy = user_transcriptions.filter(
        accuracy_score__isnull=False
    ).aggregate(avg=Avg('accuracy_score'))['avg'] or 0.8
    
    instruments_used = set()
    for transcription in user_transcriptions:
        if transcription.detected_instruments:
            instruments_used.update(transcription.detected_instruments)
    
    user_stats = {
        'total_transcriptions': user_transcriptions.count(),
        'total_music_analyzed': f"{total_duration / 60:.1f} minutes",
        'average_accuracy': f"{avg_accuracy * 100:.0f}%",
        'instruments_explored': list(instruments_used),
        'subscription_tier': request.user.profile.subscription_tier.title(),
        'can_export': request.user.profile.can_export_files(),
        'uploads_remaining': max(0, request.user.profile.get_monthly_limit() - request.user.profile.uploads_this_month)
    }
    
    # Recent transcription details
    transcription_details = []
    for t in user_transcriptions:
        details = {
            'id': str(t.id),
            'filename': t.filename,
            'status': t.status,
            'accuracy': f"{(t.accuracy_score or 0.8) * 100:.0f}%",
            'instruments': len(t.detected_instruments) if t.detected_instruments else 0,
            'created': t.created_at.strftime('%Y-%m-%d %H:%M'),
            'can_view': True,
            'can_export': request.user.profile.can_export_files()
        }
        transcription_details.append(details)
    
    return JsonResponse({
        'user_stats': user_stats,
        'recent_transcriptions': transcription_details
    }, indent=2)
