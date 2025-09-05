"""
Export manager for generating various tab file formats.
"""
import os
import tempfile
import logging
from typing import Dict, Optional
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
import json

import music21
from music21 import stream, note, tempo, meter, instrument
import pretty_midi
from midiutil import MIDIFile

try:
    import guitarpro as gp
except ImportError:
    gp = None

logger = logging.getLogger(__name__)


class ExportManager:
    """
    Manages export of transcription data to various formats.
    Supports MusicXML, Guitar Pro 5, MIDI, PDF, and ASCII tab.
    """
    
    def __init__(self, transcription):
        self.transcription = transcription
        self.tab_data = transcription.guitar_notes
        
    def generate_musicxml(self, tab_data: Dict) -> str:
        """
        Generate MusicXML content for AlphaTab rendering.
        """
        try:
            # Create music21 score
            score = stream.Score()
            part = stream.Part()
            part.append(instrument.Guitar())
            
            # Add tempo
            if tab_data.get('tempo'):
                part.append(tempo.MetronomeMark(number=tab_data['tempo']))
            
            # Add time signature
            time_sig = tab_data.get('time_signature', '4/4')
            part.append(meter.TimeSignature(time_sig))
            
            # Process measures
            for measure_data in tab_data.get('measures', []):
                measure = stream.Measure()
                
                for note_data in measure_data['notes']:
                    # Convert tab position to pitch
                    midi_note = self._tab_to_midi(
                        note_data['string'], 
                        note_data['fret'],
                        tab_data.get('tuning', [40, 45, 50, 55, 59, 64])
                    )
                    
                    # Create note
                    n = note.Note(midi_note)
                    n.duration.quarterLength = note_data['duration'] * 4  # Convert to quarter notes
                    
                    # Add string and fret info as articulations
                    n.articulations.append(
                        music21.articulations.TechnicalIndication(
                            f"string:{note_data['string']+1},fret:{note_data['fret']}"
                        )
                    )
                    
                    # Add techniques
                    technique = note_data.get('technique', 'normal')
                    if technique == 'hammer_on':
                        n.articulations.append(music21.articulations.HammerOn())
                    elif technique == 'pull_off':
                        n.articulations.append(music21.articulations.PullOff())
                    elif technique == 'slide_up':
                        n.articulations.append(music21.articulations.GlissandoUp())
                    elif technique == 'slide_down':
                        n.articulations.append(music21.articulations.GlissandoDown())
                    elif technique == 'bend':
                        n.articulations.append(music21.articulations.Bend())
                    
                    measure.append(n)
                
                part.append(measure)
            
            score.append(part)
            
            # Convert to MusicXML
            musicxml = score.write('musicxml', fmt='xml')
            return musicxml
            
        except Exception as e:
            logger.error(f"Error generating MusicXML: {str(e)}")
            return self._generate_basic_musicxml(tab_data)
    
    def _generate_basic_musicxml(self, tab_data: Dict) -> str:
        """
        Generate basic MusicXML without music21 library.
        """
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
        part_name.text = 'Guitar'
        
        # Add part
        part = SubElement(score, 'part', id='P1')
        
        # Process measures
        for i, measure_data in enumerate(tab_data.get('measures', [])):
            measure = SubElement(part, 'measure', number=str(i + 1))
            
            # Add attributes for first measure
            if i == 0:
                attributes = SubElement(measure, 'attributes')
                divisions = SubElement(attributes, 'divisions')
                divisions.text = '4'
                
                # Time signature
                time_sig = tab_data.get('time_signature', '4/4').split('/')
                time = SubElement(attributes, 'time')
                beats = SubElement(time, 'beats')
                beats.text = time_sig[0]
                beat_type = SubElement(time, 'beat-type')
                beat_type.text = time_sig[1]
                
                # Clef
                clef = SubElement(attributes, 'clef')
                sign = SubElement(clef, 'sign')
                sign.text = 'TAB'
                line = SubElement(clef, 'line')
                line.text = '5'
                
                # Staff details (6 strings)
                staff_details = SubElement(attributes, 'staff-details')
                staff_lines = SubElement(staff_details, 'staff-lines')
                staff_lines.text = '6'
                
                # Tuning
                for string_num, tuning_note in enumerate(tab_data.get('tuning', [40, 45, 50, 55, 59, 64])):
                    staff_tuning = SubElement(staff_details, 'staff-tuning', line=str(string_num + 1))
                    tuning_step = SubElement(staff_tuning, 'tuning-step')
                    tuning_octave = SubElement(staff_tuning, 'tuning-octave')
                    pitch_name = self._midi_to_note_name(tuning_note)
                    tuning_step.text = pitch_name[0]
                    tuning_octave.text = str(pitch_name[1])
            
            # Add notes
            for note_data in measure_data['notes']:
                note_elem = SubElement(measure, 'note')
                
                # Pitch
                pitch = SubElement(note_elem, 'pitch')
                midi_note = self._tab_to_midi(
                    note_data['string'],
                    note_data['fret'],
                    tab_data.get('tuning', [40, 45, 50, 55, 59, 64])
                )
                pitch_name = self._midi_to_note_name(midi_note)
                step = SubElement(pitch, 'step')
                step.text = pitch_name[0]
                if '#' in pitch_name[0] or 'b' in pitch_name[0]:
                    alter = SubElement(pitch, 'alter')
                    alter.text = '1' if '#' in pitch_name[0] else '-1'
                octave = SubElement(pitch, 'octave')
                octave.text = str(pitch_name[1])
                
                # Duration
                duration = SubElement(note_elem, 'duration')
                duration.text = str(int(note_data['duration'] * 16))
                
                # Type
                note_type = SubElement(note_elem, 'type')
                note_type.text = self._duration_to_type(note_data['duration'])
                
                # Notations for tab
                notations = SubElement(note_elem, 'notations')
                technical = SubElement(notations, 'technical')
                
                string_elem = SubElement(technical, 'string')
                string_elem.text = str(note_data['string'] + 1)
                
                fret_elem = SubElement(technical, 'fret')
                fret_elem.text = str(note_data['fret'])
                
                # Add technique
                technique = note_data.get('technique', 'normal')
                if technique != 'normal':
                    if technique == 'hammer_on':
                        SubElement(technical, 'hammer-on', type='start')
                    elif technique == 'pull_off':
                        SubElement(technical, 'pull-off', type='start')
                    elif technique in ['slide_up', 'slide_down']:
                        gliss = SubElement(notations, 'glissando', type='start')
                        gliss.text = 'slide'
        
        # Convert to pretty XML string
        rough_string = tostring(score, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ")
    
    def generate_gp5(self, tab_data: Dict) -> Optional[str]:
        """
        Generate Guitar Pro 5 file.
        """
        if not gp:
            logger.warning("guitarpro library not available")
            return None
        
        try:
            # Create GP song
            song = gp.Song()
            song.title = self.transcription.filename
            song.artist = "RiffScribe"
            song.tempo = tab_data.get('tempo', 120)
            
            # Create track
            track = gp.Track()
            track.name = "Guitar"
            track.channel = gp.MidiChannel()
            track.channel.instrument = 24  # Acoustic guitar
            
            # Set tuning
            tuning = tab_data.get('tuning', [40, 45, 50, 55, 59, 64])
            track.strings = []
            for midi_note in tuning:
                string = gp.GuitarString()
                string.value = midi_note
                track.strings.append(string)
            
            song.tracks.append(track)
            
            # Create measures
            for measure_data in tab_data.get('measures', []):
                measure = gp.Measure()
                measure.timeSignature = gp.TimeSignature()
                ts_parts = tab_data.get('time_signature', '4/4').split('/')
                measure.timeSignature.numerator = int(ts_parts[0])
                measure.timeSignature.denominator = gp.Duration()
                measure.timeSignature.denominator.value = int(ts_parts[1])
                
                voice = gp.Voice()
                beat_time = 0
                
                for note_data in measure_data['notes']:
                    beat = gp.Beat()
                    beat.start = int(beat_time * 960)  # GP uses 960 ticks per quarter note
                    beat.duration = gp.Duration()
                    beat.duration.value = self._duration_to_gp_duration(note_data['duration'])
                    
                    # Create note
                    note = gp.Note()
                    note.string = note_data['string'] + 1  # GP uses 1-based indexing
                    note.value = note_data['fret']
                    note.velocity = note_data.get('velocity', 80)
                    
                    # Add effects
                    technique = note_data.get('technique', 'normal')
                    if technique == 'hammer_on':
                        note.effect.hammer = True
                    elif technique == 'pull_off':
                        note.effect.pullOff = True
                    elif technique == 'slide_up':
                        note.effect.slides = [gp.SlideType.shiftSlideTo]
                    elif technique == 'slide_down':
                        note.effect.slides = [gp.SlideType.shiftSlideFrom]
                    elif technique == 'bend':
                        note.effect.bend = gp.BendEffect()
                        note.effect.bend.points = [gp.BendPoint(0, 0), gp.BendPoint(50, 100)]
                    elif technique == 'vibrato':
                        note.effect.vibrato = True
                    elif technique == 'palm_mute':
                        note.effect.palmMute = True
                    
                    beat.notes.append(note)
                    voice.beats.append(beat)
                    
                    beat_time += note_data['duration']
                
                measure.voices.append(voice)
                track.measures.append(measure)
                song.measures.append(measure)
            
            # Save to file
            temp_file = tempfile.NamedTemporaryFile(suffix='.gp5', delete=False)
            gp.write(song, temp_file.name)
            
            return temp_file.name
            
        except Exception as e:
            logger.error(f"Error generating GP5: {str(e)}")
            return None
    
    def export_musicxml(self) -> str:
        """Export as MusicXML file."""
        content = self.generate_musicxml(self.tab_data)
        
        temp_file = tempfile.NamedTemporaryFile(
            suffix='.xml', 
            prefix=f'{self.transcription.filename}_',
            delete=False,
            mode='w'
        )
        temp_file.write(content)
        temp_file.close()
        
        return temp_file.name
    
    def export_gp5(self) -> Optional[str]:
        """Export as Guitar Pro 5 file."""
        return self.generate_gp5(self.tab_data)
    
    def export_midi(self) -> str:
        """Export as MIDI file."""
        midi = MIDIFile(1)
        track = 0
        channel = 0
        time = 0
        tempo_bpm = self.tab_data.get('tempo', 120)
        
        midi.addTempo(track, time, tempo_bpm)
        
        # Add notes
        for measure in self.tab_data.get('measures', []):
            for note_data in measure['notes']:
                midi_note = self._tab_to_midi(
                    note_data['string'],
                    note_data['fret'],
                    self.tab_data.get('tuning', [40, 45, 50, 55, 59, 64])
                )
                
                midi.addNote(
                    track, channel, midi_note,
                    time + note_data['time'],
                    note_data['duration'],
                    note_data.get('velocity', 80)
                )
        
        # Save to file
        temp_file = tempfile.NamedTemporaryFile(
            suffix='.mid',
            prefix=f'{self.transcription.filename}_',
            delete=False
        )
        midi.writeFile(temp_file)
        temp_file.close()
        
        return temp_file.name
    
    def export_pdf(self) -> Optional[str]:
        """Export as PDF (requires lilypond or similar)."""
        # This would require additional setup with lilypond
        # For now, return None
        logger.warning("PDF export not yet implemented")
        return None
    
    def export_ascii_tab(self) -> str:
        """Export as ASCII tab text file."""
        from .tab_generator import TabGenerator
        
        # Reconstruct notes from tab data
        notes = []
        for measure in self.tab_data.get('measures', []):
            for note in measure['notes']:
                notes.append({
                    'start_time': note['time'] + measure['start_time'],
                    'end_time': note['time'] + measure['start_time'] + note['duration'],
                    'midi_note': self._tab_to_midi(
                        note['string'], note['fret'],
                        self.tab_data.get('tuning', [40, 45, 50, 55, 59, 64])
                    ),
                    'velocity': note.get('velocity', 80)
                })
        
        generator = TabGenerator(
            notes,
            self.tab_data.get('tempo', 120),
            self.tab_data.get('time_signature', '4/4')
        )
        
        ascii_tab = generator.to_ascii_tab()
        
        # Save to file
        temp_file = tempfile.NamedTemporaryFile(
            suffix='.txt',
            prefix=f'{self.transcription.filename}_tab_',
            delete=False,
            mode='w'
        )
        temp_file.write(ascii_tab)
        temp_file.close()
        
        return temp_file.name
    
    def _tab_to_midi(self, string: int, fret: int, tuning: list) -> int:
        """Convert tab position to MIDI note number."""
        return tuning[string] + fret
    
    def _midi_to_note_name(self, midi_note: int) -> tuple:
        """Convert MIDI note to note name and octave."""
        notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        octave = (midi_note // 12) - 1
        note_name = notes[midi_note % 12]
        return (note_name, octave)
    
    def _duration_to_type(self, duration: float) -> str:
        """Convert duration to note type."""
        if duration >= 1:
            return 'whole'
        elif duration >= 0.5:
            return 'half'
        elif duration >= 0.25:
            return 'quarter'
        elif duration >= 0.125:
            return 'eighth'
        else:
            return 'sixteenth'
    
    def _duration_to_gp_duration(self, duration: float) -> int:
        """Convert duration to Guitar Pro duration value."""
        if duration >= 1:
            return 1  # Whole note
        elif duration >= 0.5:
            return 2  # Half note
        elif duration >= 0.25:
            return 4  # Quarter note
        elif duration >= 0.125:
            return 8  # Eighth note
        else:
            return 16  # Sixteenth note