"""
Export views for RiffScribe
Handles all export functionality for transcriptions
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, FileResponse
from django.views.decorators.http import require_http_methods
from celery.result import AsyncResult
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
import json
import os

from ..models import Transcription, TabExport, FingeringVariant
from ..tasks import generate_export


def generate_basic_musicxml_from_guitar_notes(transcription):
    """
    Generate basic MusicXML from guitar_notes without heavy dependencies.
    This is used in the website container where music21 is not available.
    """
    guitar_notes = transcription.guitar_notes
    
    if not guitar_notes:
        return None
    
    # Ensure guitar_notes is a dictionary
    if isinstance(guitar_notes, str):
        try:
            guitar_notes = json.loads(guitar_notes)
        except:
            return None
    
    if not isinstance(guitar_notes, dict):
        return None
    
    # Create root element
    score = Element('score-partwise', version='3.1')
    
    # Add identification
    identification = SubElement(score, 'identification')
    creator = SubElement(identification, 'creator', type='composer')
    creator.text = 'RiffScribe'
    
    # Add part list
    part_list = SubElement(score, 'part-list')
    score_part = SubElement(part_list, 'score-part', id='P1')
    part_name = SubElement(score_part, 'part-name')
    part_name.text = transcription.filename or 'Guitar'
    
    # Add part
    part = SubElement(score, 'part', id='P1')
    
    # Get measures from guitar_notes
    measures_data = guitar_notes.get('measures', [])
    if not measures_data:
        # Create at least one empty measure
        measures_data = [{'notes': [], 'number': 1}]
    
    # Process first 10 measures for performance
    for i, measure_data in enumerate(measures_data[:10]):
        measure = SubElement(part, 'measure', number=str(i + 1))
        
        # Add attributes for first measure
        if i == 0:
            attributes = SubElement(measure, 'attributes')
            divisions = SubElement(attributes, 'divisions')
            divisions.text = '4'
            
            # Time signature
            time = SubElement(attributes, 'time')
            beats = SubElement(time, 'beats')
            beats.text = '4'
            beat_type = SubElement(time, 'beat-type')
            beat_type.text = '4'
            
            # Clef for TAB
            clef = SubElement(attributes, 'clef')
            sign = SubElement(clef, 'sign')
            sign.text = 'TAB'
            line = SubElement(clef, 'line')
            line.text = '5'
            
            # Staff details (6 strings)
            staff_details = SubElement(attributes, 'staff-details')
            staff_lines = SubElement(staff_details, 'staff-lines')
            staff_lines.text = '6'
        
        # Add notes or rest
        notes = measure_data.get('notes', [])
        if notes:
            for note_data in notes[:5]:  # Limit notes per measure
                note_elem = SubElement(measure, 'note')
                
                # Add pitch
                pitch = SubElement(note_elem, 'pitch')
                step = SubElement(pitch, 'step')
                step.text = 'C'
                octave = SubElement(pitch, 'octave')
                octave.text = '4'
                
                # Duration
                duration = SubElement(note_elem, 'duration')
                duration.text = '4'
                
                # Type
                type_elem = SubElement(note_elem, 'type')
                type_elem.text = 'quarter'
                
                # Add TAB notation
                notations = SubElement(note_elem, 'notations')
                technical = SubElement(notations, 'technical')
                
                string_elem = SubElement(technical, 'string')
                string_elem.text = str(note_data.get('string', 1))
                
                fret_elem = SubElement(technical, 'fret')
                fret_elem.text = str(note_data.get('fret', 0))
        else:
            # Add a rest
            note_elem = SubElement(measure, 'note')
            rest = SubElement(note_elem, 'rest')
            duration = SubElement(note_elem, 'duration')
            duration.text = '16'
            type_elem = SubElement(note_elem, 'type')
            type_elem.text = 'whole'
    
    # Convert to pretty XML string
    rough_string = tostring(score, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")


@require_http_methods(["GET", "POST"])
def export(request, pk):
    """
    Export selection page and export generation handler.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    if request.method == "POST":
        export_format = request.POST.get('format', 'musicxml')
        
        # Handle "all" format - generate all available formats
        if export_format == 'all':
            formats_to_generate = ['musicxml', 'gp5', 'midi', 'ascii']
            tasks = []
            
            for fmt in formats_to_generate:
                # Only generate if doesn't already exist
                existing = TabExport.objects.filter(
                    transcription=transcription,
                    format=fmt
                ).first()
                
                if not existing:
                    task = generate_export.delay(str(transcription.id), fmt)
                    tasks.append({'format': fmt, 'task_id': task.id})
            
            if request.headers.get('HX-Request'):
                return render(request, 'transcriber/partials/export_all_status.html', {
                    'tasks': tasks,
                    'transcription': transcription,
                })
            
            return JsonResponse({
                'tasks': tasks,
                'status': 'processing_all'
            })
        
        # Single format export
        # Check if export already exists
        existing_export = TabExport.objects.filter(
            transcription=transcription,
            format=export_format
        ).first()
        
        if existing_export:
            # If HTMX request, return success status
            if request.headers.get('HX-Request'):
                return render(request, 'transcriber/partials/export_status.html', {
                    'status': 'completed',
                    'format': export_format,
                    'download_url': f'/transcription/{transcription.pk}/download/{existing_export.id}/'
                })
            return redirect('transcriber:download', pk=transcription.pk, export_id=existing_export.id)
        
        # Queue export task
        task = generate_export.delay(str(transcription.id), export_format)
        
        # Return processing template for HTMX
        if request.headers.get('HX-Request'):
            return render(request, 'transcriber/partials/export_processing.html', {
                'task_id': task.id,
                'format': export_format,
                'transcription': transcription,
                'format_display': export_format.upper(),
            })
        
        return JsonResponse({
            'task_id': task.id,
            'format': export_format,
            'status': 'processing'
        })
    
    # GET request - show export options
    return render(request, 'transcriber/export.html', {
        'transcription': transcription
    })


def download(request, pk, export_id):
    """
    Download a specific export file.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    tab_export = get_object_or_404(TabExport, id=export_id, transcription=transcription)
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    if not tab_export.file:
        return JsonResponse({'error': 'Export file not found'}, status=404)
    
    # Determine content type based on format
    content_types = {
        'musicxml': 'application/xml',
        'gp5': 'application/x-guitar-pro',
        'midi': 'audio/midi',
        'pdf': 'application/pdf',
        'ascii': 'text/plain'
    }
    content_type = content_types.get(tab_export.format, 'application/octet-stream')
    
    try:
        # Safely open and read the file
        file_content = tab_export.file.read()
        
        # Create response with file
        response = HttpResponse(file_content, content_type=content_type)
        
        # Set filename for download
        base_filename = os.path.splitext(transcription.filename)[0]
        extension = tab_export.format if tab_export.format != 'gp5' else 'gp5'
        response['Content-Disposition'] = f'attachment; filename="{base_filename}.{extension}"'
        
        return response
        
    except Exception as e:
        # If there's an issue with the file path, try to regenerate or return error
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error downloading export {export_id}: {str(e)}")
        
        # Return a more user-friendly error
        return JsonResponse({
            'error': 'The export file could not be found or accessed. Please try regenerating the export.',
            'details': str(e) if request.user.is_superuser else None
        }, status=404)


@require_http_methods(["GET", "POST"])
def export_musicxml(request, pk):
    """
    Generate and return MusicXML export.
    Can return content directly for AlphaTab or download as file.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Check access permission - allow if:
    # 1. User owns the transcription
    # 2. Transcription is public
    # 3. User is superuser
    # 4. Anonymous transcription (no owner)
    if (transcription.user and 
        transcription.user != request.user and 
        not transcription.is_public and 
        not request.user.is_superuser):
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    # Check if this is a direct content request (for AlphaTab)
    direct_content = request.GET.get('content') == '1' or not request.GET.get('download')
    
    # First try to get from stored musicxml_content
    if transcription.musicxml_content:
        if direct_content:
            # Return raw MusicXML for AlphaTab
            response = HttpResponse(transcription.musicxml_content, content_type='application/xml')
            response['Access-Control-Allow-Origin'] = '*'
            return response
    
    # Check if export file exists
    existing_export = TabExport.objects.filter(
        transcription=transcription,
        format='musicxml'
    ).first()
    
    if existing_export and existing_export.file:
        if direct_content:
            try:
                # Return file content directly
                file_content = existing_export.file.read()
                response = HttpResponse(file_content, content_type='application/xml')
                response['Access-Control-Allow-Origin'] = '*'
                return response
            except:
                pass
        else:
            return redirect('transcriber:download', pk=transcription.pk, export_id=existing_export.id)
    
    # Generate export if needed
    try:
        # Try to generate MusicXML without heavy dependencies
        musicxml_content = generate_basic_musicxml_from_guitar_notes(transcription)
        
        if musicxml_content:
            if direct_content:
                # Return content directly for AlphaTab
                response = HttpResponse(musicxml_content, content_type='application/xml')
                response['Access-Control-Allow-Origin'] = '*'
                return response
            else:
                # Save export for download
                tab_export = TabExport.objects.create(
                    transcription=transcription,
                    format='musicxml'
                )
                
                # Save file
                from django.core.files.base import ContentFile
                tab_export.file.save(
                    f'{transcription.id}_musicxml.xml',
                    ContentFile(musicxml_content.encode('utf-8'))
                )
                
                return redirect('transcriber:download', pk=transcription.pk, export_id=tab_export.id)
        else:
            return JsonResponse({'error': 'Failed to generate MusicXML'}, status=500)
            
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"MusicXML export error: {str(e)}")
        
        # Return a basic MusicXML if generation fails
        if direct_content:
            basic_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <identification>
    <creator type="composer">RiffScribe</creator>
  </identification>
  <part-list>
    <score-part id="P1">
      <part-name>Guitar</part-name>
    </score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>4</divisions>
        <time>
          <beats>4</beats>
          <beat-type>4</beat-type>
        </time>
        <clef>
          <sign>TAB</sign>
          <line>5</line>
        </clef>
      </attributes>
    </measure>
  </part>
</score-partwise>'''
            response = HttpResponse(basic_xml, content_type='application/xml')
            response['Access-Control-Allow-Origin'] = '*'
            return response
        
        return JsonResponse({'error': f'Export failed: {str(e)}'}, status=500)


def download_gp5(request, pk):
    """
    Generate and download Guitar Pro 5 export.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    # Check if export already exists
    existing_export = TabExport.objects.filter(
        transcription=transcription,
        format='gp5'
    ).first()
    
    if existing_export and existing_export.file:
        return redirect('transcriber:download', pk=transcription.pk, export_id=existing_export.id)
    
    # Generate export
    try:
        export_manager = ExportManager(transcription)
        gp5_content = export_manager.generate_gp5_bytes()
        
        if gp5_content:
            # Save export
            tab_export = TabExport.objects.create(
                transcription=transcription,
                format='gp5'
            )
            
            # Save file
            from django.core.files.base import ContentFile
            tab_export.file.save(
                f'{transcription.id}_guitar_pro.gp5',
                ContentFile(gp5_content)
            )
            
            return redirect('transcriber:download', pk=transcription.pk, export_id=tab_export.id)
        else:
            return JsonResponse({'error': 'Failed to generate Guitar Pro file'}, status=500)
            
    except Exception as e:
        return JsonResponse({'error': f'Export failed: {str(e)}'}, status=500)


def debug_tab_data(request, pk):
    """
    Debug endpoint to check tab data structure for GP5 export issues.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        export_manager = ExportManager(transcription)
        debug_info = export_manager.debug_tab_data()
        return JsonResponse(debug_info, indent=2)
    except Exception as e:
        return JsonResponse({'error': f'Debug failed: {str(e)}'}, status=500)


def download_ascii_tab(request, pk):
    """
    Generate and download ASCII tab export.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    # Generate ASCII tab
    try:
        export_manager = ExportManager(transcription)
        ascii_tab = export_manager.export_ascii_tab()
        
        if ascii_tab:
            # Return as plain text
            response = HttpResponse(ascii_tab, content_type='text/plain')
            base_filename = os.path.splitext(transcription.filename)[0]
            response['Content-Disposition'] = f'attachment; filename="{base_filename}_tab.txt"'
            return response
        else:
            return JsonResponse({'error': 'No tab data available'}, status=404)
            
    except Exception as e:
        return JsonResponse({'error': f'Export failed: {str(e)}'}, status=500)


def download_midi(request, pk):
    """
    Generate and download MIDI export.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    # Check if export already exists
    existing_export = TabExport.objects.filter(
        transcription=transcription,
        format='midi'
    ).first()
    
    if existing_export and existing_export.file:
        return redirect('transcriber:download', pk=transcription.pk, export_id=existing_export.id)
    
    # Generate MIDI
    try:
        export_manager = ExportManager(transcription)
        midi_content = export_manager.export_midi()
        
        if midi_content:
            # Save export
            tab_export = TabExport.objects.create(
                transcription=transcription,
                format='midi'
            )
            
            # Save file
            from django.core.files.base import ContentFile
            tab_export.file.save(
                f'{transcription.id}_midi.mid',
                ContentFile(midi_content)
            )
            
            return redirect('transcriber:download', pk=transcription.pk, export_id=tab_export.id)
        else:
            return JsonResponse({'error': 'Failed to generate MIDI'}, status=500)
            
    except Exception as e:
        return JsonResponse({'error': f'Export failed: {str(e)}'}, status=500)


@require_http_methods(["POST"])
def clear_exports(request, pk):
    """
    Clear all exports for a transcription.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    
    # Check access permission
    if transcription.user and transcription.user != request.user:
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        # Delete all export files and records
        for export in transcription.exports.all():
            if export.file:
                export.file.delete()
            export.delete()
        
        # Return empty downloads section for HTMX
        if request.headers.get('HX-Request'):
            return HttpResponse('')  # Empty response removes the downloads section
        
        return JsonResponse({'status': 'success', 'message': 'All exports cleared'})
        
    except Exception as e:
        return JsonResponse({'error': f'Failed to clear exports: {str(e)}'}, status=500)