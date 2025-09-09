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

# Lazy import for music21 (heavy dependency)
def _get_music21():
    try:
        import music21
        from music21 import stream, note, tempo, meter, instrument
        return music21, stream, note, tempo, meter, instrument
    except ImportError:
        return None, None, None, None, None, None
from midiutil import MIDIFile

try:
    import guitarpro
except ImportError:
    try:
        import pyguitarpro as guitarpro
    except ImportError:
        guitarpro = None

logger = logging.getLogger(__name__)


class ExportManager:
    """
    Manages export of transcription data to various formats.
    Supports MusicXML, Guitar Pro 5, MIDI, PDF, and ASCII tab.
    """
    
    def __init__(self, transcription):
        self.transcription = transcription
        self.tab_data = transcription.guitar_notes
        
    def generate_musicxml(self, tab_data: Optional[Dict] = None) -> str:
        """
        Generate MusicXML content for AlphaTab rendering.
        Can use custom tab_data (e.g., from a variant) or default to transcription's data.
        """
        # Use provided tab_data or fall back to transcription's data
        if tab_data is None:
            tab_data = self.tab_data
            
        if not tab_data:
            return ""
            
        # Ensure tab_data is a dictionary
        if not isinstance(tab_data, dict):
            logger.warning(f"Invalid tab data type for MusicXML generation: {type(tab_data).__name__}")
            return ""
            
        try:
            # Lazy load music21
            music21, stream, note, tempo, meter, instrument = _get_music21()
            if not music21:
                logger.warning("music21 not available, using basic MusicXML generation")
                return self._generate_basic_musicxml(tab_data)
            
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
                    try:
                        # Use a fingering indication instead of TechnicalIndication
                        tech_indication = music21.articulations.Fingering(f"s{note_data['string']+1}f{note_data['fret']}")
                        n.articulations.append(tech_indication)
                    except Exception as e:
                        logger.warning(f"Could not add technical indication: {e}")
                        # Fall back to a simple approach - add as lyric instead
                        try:
                            n.addLyric(f"s{note_data['string']+1}f{note_data['fret']}")
                        except Exception:
                            pass  # If all methods fail, just skip
                    
                    # Add techniques
                    technique = note_data.get('technique', 'normal')
                    try:
                        if technique == 'hammer_on':
                            n.articulations.append(music21.articulations.HammerOn())
                        elif technique == 'pull_off':
                            n.articulations.append(music21.articulations.PullOff())
                        elif technique == 'slide_up':
                            # Use general Glissando for slide up
                            try:
                                n.articulations.append(music21.articulations.Glissando())
                            except AttributeError:
                                # Fallback to generic articulation or skip
                                n.addLyric("slide↑")
                        elif technique == 'slide_down':
                            # Use general Glissando for slide down  
                            try:
                                n.articulations.append(music21.articulations.Glissando())
                            except AttributeError:
                                # Fallback to generic articulation or skip
                                n.addLyric("slide↓")
                        elif technique == 'bend':
                            n.articulations.append(music21.articulations.Bend())
                    except Exception as e:
                        logger.warning(f"Could not add technique articulation '{technique}': {e}")
                        # Continue without the articulation
                    
                    measure.append(n)
                
                part.append(measure)
            
            score.append(part)
            
            # Convert to MusicXML
            # Create a temporary file to write the MusicXML
            with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as temp_file:
                score.write('musicxml', fp=temp_file.name)
                with open(temp_file.name, 'r') as f:
                    musicxml = f.read()
            
            return musicxml
            
        except Exception as e:
            logger.error(f"Error generating MusicXML: {str(e)}")
            return self._generate_basic_musicxml(tab_data)
    
    def _generate_basic_musicxml(self, tab_data: Dict) -> str:
        """
        Generate basic MusicXML without music21 library.
        """
        # Ensure tab_data is a dictionary
        if not isinstance(tab_data, dict):
            logger.warning(f"Invalid tab data type for basic MusicXML generation: {type(tab_data).__name__}")
            return ""
            
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
    
    def generate_gp5(self, tab_data: Optional[Dict] = None) -> Optional[str]:
        """
        Generate Guitar Pro 5 file.
        Can use custom tab_data (e.g., from a variant) or default to transcription's data.
        """
        # Use provided tab_data or fall back to transcription's data
        if tab_data is None:
            tab_data = self.tab_data
            
        if not tab_data:
            logger.warning("GP5 export: No tab data available")
            return None
            
        if not guitarpro:
            logger.error("GP5 export: guitarpro/pyguitarpro library not available - cannot export GP5 format")
            return None
            
        logger.info(f"GP5 export: Processing {len(tab_data.get('measures', []))} measures")
        
        try:
            # Get measures or create a default empty one
            measures_data = tab_data.get('measures', [])
            if not measures_data:
                logger.info("GP5 export: No measures found, creating empty measure")
                measures_data = [{'notes': [], 'start_time': 0.0, 'number': 1}]
            
            # Count total notes across all measures
            total_notes = sum(len(measure.get('notes', [])) for measure in measures_data)
            logger.info(f"GP5 export: Processing {len(measures_data)} measures with {total_notes} total notes")
            
            # Create basic GP5 structure using PyGuitarPro API
            logger.info("GP5 export: Creating GP5 song structure...")
            song = guitarpro.models.Song()
            song.title = self.transcription.filename or "Untitled"
            song.artist = "RiffScribe"
            logger.info("GP5 export: Song created successfully")
            
            # Set tempo if available
            tempo_value = tab_data.get('tempo', 120)
            song.tempo = tempo_value
            logger.info(f"GP5 export: Tempo set to {tempo_value}")
            
            # Create a single guitar track (requires song parameter)
            track = guitarpro.models.Track(song)
            track.name = "Guitar"
            track.channel = guitarpro.models.TrackChannel()
            track.channel.instrument = 24  # Acoustic guitar
            song.tracks = [track]
            logger.info("GP5 export: Track created and added to song")
            
            # Create basic measure structure
            for measure_data in measures_data:
                measure = guitarpro.models.Measure()
                # Initialize empty voices for the measure
                measure.voices = [guitarpro.models.Voice()]
                track.measures.append(measure)
            
            logger.info(f"GP5 export: Created {len(track.measures)} measures")
            
            # Write to temporary file
            temp_file = tempfile.NamedTemporaryFile(suffix='.gp5', delete=False)
            temp_file.close()
            
            guitarpro.write(song, temp_file.name)
            logger.info(f"GP5 export: Successfully wrote file to {temp_file.name}")
            
            return temp_file.name
            
        except Exception as e:
            logger.error(f"GP5 export failed: {str(e)}")
            return None
    
    def debug_tab_data(self) -> Dict:
        """
        Return diagnostic information about the tab data for debugging.
        """
        tab_data = self.tab_data
        if not tab_data:
            return {
                'status': 'error',
                'message': 'No tab data available',
                'transcription_id': str(self.transcription.id),
                'has_guitar_notes': False,
                'guitar_notes_type': type(tab_data).__name__
            }
            
        # Check if tab_data is a dictionary 
        if not isinstance(tab_data, dict):
            return {
                'status': 'error',
                'message': f'Invalid tab data type: {type(tab_data).__name__}',
                'transcription_id': str(self.transcription.id),
                'has_guitar_notes': bool(self.transcription.guitar_notes),
                'guitar_notes_type': type(tab_data).__name__
            }
            
        measures_data = tab_data.get('measures', [])
        total_notes = sum(len(measure.get('notes', [])) for measure in measures_data)
        
        return {
            'status': 'ok',
            'transcription_id': str(self.transcription.id),
            'has_guitar_notes': bool(self.transcription.guitar_notes),
            'measures_count': len(measures_data),
            'total_notes': total_notes,
            'tempo': tab_data.get('tempo'),
            'time_signature': tab_data.get('time_signature'),
            'tuning': tab_data.get('tuning'),
            'techniques_used': tab_data.get('techniques_used'),
            'sample_measures': [
                {
                    'measure_num': i + 1,
                    'notes_count': len(measure.get('notes', [])),
                    'sample_note': measure.get('notes', [])[0] if measure.get('notes') else None
                } 
                for i, measure in enumerate(measures_data[:3])  # Show first 3 measures
            ]
        }
    
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
        if not self.tab_data or not self.tab_data.get('measures'):
            logger.warning("No tab data available for MIDI export")
            # Create a minimal empty MIDI file
            midi = MIDIFile(1)
            midi.addTempo(0, 0, 120)
        else:
            midi = MIDIFile(1)
            track = 0
            channel = 0
            tempo_bpm = self.tab_data.get('tempo', 120)
            
            midi.addTempo(track, 0, tempo_bpm)
            
            # Add notes with proper timing calculation
            for measure in self.tab_data.get('measures', []):
                measure_start_time = measure.get('start_time', 0.0)
                
                for note_data in measure.get('notes', []):
                    try:
                        # Calculate absolute time for the note
                        note_time = measure_start_time + note_data.get('time', 0.0)
                        
                        # Ensure duration is positive and reasonable
                        duration = max(0.1, note_data.get('duration', 0.25))  # Minimum 0.1 beats
                        
                        # Get MIDI note number
                        midi_note = self._tab_to_midi(
                            note_data.get('string', 0),
                            note_data.get('fret', 0),
                            self.tab_data.get('tuning', [40, 45, 50, 55, 59, 64])
                        )
                        
                        # Validate MIDI note range (0-127)
                        midi_note = max(0, min(127, midi_note))
                        
                        # Get velocity
                        velocity = max(1, min(127, note_data.get('velocity', 80)))
                        
                        # Add the note to MIDI
                        midi.addNote(
                            track, channel, midi_note,
                            note_time,
                            duration,
                            velocity
                        )
                        
                        logger.debug(f"Added MIDI note: pitch={midi_note}, time={note_time:.2f}, duration={duration:.2f}")
                        
                    except Exception as e:
                        logger.warning(f"Error processing note in MIDI export: {e}")
                        # Skip problematic notes but continue processing
                        continue
        
        # Save to file
        temp_file = tempfile.NamedTemporaryFile(
            suffix='.mid',
            prefix=f'{self.transcription.filename}_',
            delete=False
        )
        
        try:
            with open(temp_file.name, 'wb') as f:
                midi.writeFile(f)
        except Exception as e:
            logger.error(f"Error writing MIDI file: {e}")
            # If writeFile fails, try closing the file handle first
            temp_file.close()
            try:
                midi.writeFile(temp_file)
            except Exception as e2:
                logger.error(f"Second attempt to write MIDI file also failed: {e2}")
                raise e2
        else:
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
        # Convert 1-indexed string to 0-indexed if needed
        string_index = string - 1 if string > 0 else string
        
        # Bounds checking
        if string_index < 0 or string_index >= len(tuning):
            logger.warning(f"String index {string} (0-indexed: {string_index}) out of range for tuning array of length {len(tuning)}. Using string 0.")
            string_index = 0
            
        # Fret bounds checking
        if fret < 0:
            logger.warning(f"Negative fret value {fret}, using 0")
            fret = 0
        elif fret > 24:  # Reasonable upper limit
            logger.warning(f"High fret value {fret}, capping at 24")
            fret = 24
            
        return tuning[string_index] + fret
    
    def generate_gp5_bytes(self, tab_data: Optional[Dict] = None) -> bytes:
        """
        Generate Guitar Pro 5 file as bytes for direct HTTP response.
        """
        gp5_path = self.generate_gp5(tab_data)
        if not gp5_path:
            return b""
            
        try:
            with open(gp5_path, 'rb') as f:
                content = f.read()
            os.unlink(gp5_path)  # Clean up temp file
            return content
        except Exception as e:
            logger.error(f"Error reading GP5 file: {str(e)}")
            return b""
    
    def generate_ascii_tab(self, tab_data: Optional[Dict] = None) -> str:
        """
        Generate ASCII tab representation.
        Can use custom tab_data (e.g., from a variant) or default to transcription's data.
        """
        # Use provided tab_data or fall back to transcription's data
        if tab_data is None:
            tab_data = self.tab_data
            
        if not tab_data:
            return ""
            
        from .tab_generator import TabGenerator
        
        # Reconstruct notes from tab data
        notes = []
        for measure in tab_data.get('measures', []):
            for note in measure['notes']:
                notes.append({
                    'start_time': note['time'] + measure.get('start_time', 0),
                    'end_time': note['time'] + measure.get('start_time', 0) + note['duration'],
                    'midi_note': self._tab_to_midi(
                        note['string'],  # _tab_to_midi now handles indexing
                        note['fret'],
                        tab_data.get('tuning', [40, 45, 50, 55, 59, 64])
                    ),
                    'velocity': note.get('velocity', 80)
                })
        
        generator = TabGenerator(
            notes,
            tab_data.get('tempo', 120),
            tab_data.get('time_signature', '4/4')
        )
        
        return generator.to_ascii_tab()
    
    def _create_empty_gp5_file(self) -> Optional[str]:
        """Create a minimal empty GP5 file when no tab data is available."""
        if not gp:
            logger.warning("guitarpro library not available for empty GP5 creation")
            return None
            
        try:
            # Create basic GP5 structure
            song = gp.Song()
            song.title = self.transcription.filename or "Untitled"
            song.artist = "RiffScribe"
            song.tempo = 120
            
            # Create a single guitar track
            track = gp.Track(song=song)
            track.name = "Guitar"
            track.isPercussionTrack = False
            
            # Set MIDI channel if available
            if hasattr(track, 'channel'):
                track.channel = gp.MidiChannel()
                track.channel.instrument = 24  # Acoustic guitar
            
            # Add track to song
            song.tracks.append(track)
            
            # Create one empty measure with proper parameters
            if hasattr(track, 'measures'):
                # Create measure header first
                header = gp.MeasureHeader()
                
                # Create measure with required parameters
                measure = gp.Measure(track, header)
                
                # Add basic voice with one rest beat
                voice = gp.Voice()
                beat = gp.Beat()
                
                # Set beat duration to quarter note rest
                try:
                    if hasattr(gp, 'DurationType'):
                        beat.duration = gp.Duration(value=gp.DurationType.quarter)
                    else:
                        beat.duration = gp.Duration(value=4)
                except:
                    beat.duration = gp.Duration()
                
                voice.beats.append(beat)
                measure.voices.append(voice)
                track.measures.append(measure)
                
                # Add header to song
                song.measureHeaders.append(header)
            
            # Save to temporary file
            temp_file = tempfile.NamedTemporaryFile(suffix='.gp5', delete=False)
            temp_file.close()
            
            # Write the GP5 file
            gp.write_song(song, temp_file.name, format=gp.formats.GP5)
            
            logger.info(f"Created empty GP5 file at: {temp_file.name}")
            return temp_file.name
            
        except Exception as e:
            logger.error(f"Failed to create empty GP5 file: {str(e)}")
            return None
    
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
    
    # Multi-track export methods
    
    def generate_multitrack_musicxml(self, tracks) -> str:
        """
        Generate MusicXML with multiple tracks/parts.
        
        Args:
            tracks: List of Track model instances
            
        Returns:
            MusicXML string
        """
        try:
            # Lazy load music21
            music21, stream, note, tempo, meter, instrument = _get_music21()
            if not music21:
                logger.warning("music21 not available for multitrack export")
                return ""
                
            score = stream.Score()
            score.metadata = stream.Metadata()
            score.metadata.title = self.transcription.filename
            score.metadata.composer = 'RiffScribe Multi-track'
            
            # Add tempo marking
            if self.transcription.estimated_tempo:
                tempo_marking = tempo.MetronomeMark(number=self.transcription.estimated_tempo)
                score.insert(0, tempo_marking)
            
            # Process each track
            for track_idx, track in enumerate(tracks):
                if not track.guitar_notes or track.track_type == 'original':
                    continue
                    
                part = stream.Part()
                part.id = f'track_{track_idx}'
                
                # Set instrument based on track type
                if track.instrument_type == 'bass':
                    instr = instrument.ElectricBass()
                elif track.instrument_type == 'drums':
                    instr = instrument.Percussion()
                elif track.instrument_type == 'acoustic_guitar':
                    instr = instrument.AcousticGuitar()
                else:
                    instr = instrument.ElectricGuitar()
                    
                part.append(instr)
                part.partName = track.display_name
                
                # Add measures from track's tab data
                if isinstance(track.guitar_notes, dict):
                    for measure_data in track.guitar_notes.get('measures', []):
                        measure = stream.Measure(number=measure_data['number'])
                        
                        # Add time signature to first measure
                        if measure_data['number'] == 1:
                            ts = meter.TimeSignature('4/4')
                            measure.append(ts)
                        
                        # Add notes
                        for note_data in measure_data['notes']:
                            try:
                                midi_note = self._tab_to_midi(
                                    note_data['string'],
                                    note_data['fret'],
                                    track.guitar_notes.get('tuning', [40, 45, 50, 55, 59, 64])
                                )
                                
                                n = note.Note(midi_note)
                                n.duration.quarterLength = note_data.get('duration', 0.25)
                                measure.append(n)
                            except Exception as e:
                                logger.warning(f"Error adding note to track {track.display_name}: {str(e)}")
                                continue
                        
                        part.append(measure)
                
                score.append(part)
            
            # Convert to MusicXML
            with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as temp_file:
                score.write('musicxml', fp=temp_file.name)
                with open(temp_file.name, 'r') as f:
                    musicxml = f.read()
            
            return musicxml
            
        except Exception as e:
            logger.error(f"Error generating multi-track MusicXML: {str(e)}")
            return ""
    
    def generate_multitrack_midi(self, tracks) -> str:
        """
        Generate MIDI file with multiple tracks.
        
        Args:
            tracks: List of Track model instances
            
        Returns:
            Path to generated MIDI file
        """
        try:
            # Create MIDI file with multiple tracks
            midi = MIDIFile(numTracks=len(tracks))
            
            tempo_val = self.transcription.estimated_tempo or 120
            
            for track_idx, track_obj in enumerate(tracks):
                if not track_obj.guitar_notes or track_obj.track_type == 'original':
                    continue
                    
                # Set track name and instrument
                midi.addTrackName(track_idx, 0, track_obj.display_name)
                midi.addTempo(track_idx, 0, tempo_val)
                
                # Set program (instrument) based on track type
                if track_obj.instrument_type == 'bass':
                    program = 33  # Electric Bass
                elif track_obj.instrument_type == 'drums':
                    program = 0  # Standard drum kit (channel 10)
                elif track_obj.instrument_type == 'acoustic_guitar':
                    program = 25  # Acoustic Guitar
                else:
                    program = 30  # Electric Guitar (overdrive)
                
                channel = 9 if track_obj.instrument_type == 'drums' else track_idx % 16
                midi.addProgramChange(track_idx, channel, 0, program)
                
                # Add notes from track data
                if isinstance(track_obj.guitar_notes, dict):
                    current_time = 0
                    for measure_data in track_obj.guitar_notes.get('measures', []):
                        for note_data in measure_data['notes']:
                            try:
                                midi_note = self._tab_to_midi(
                                    note_data['string'],
                                    note_data['fret'],
                                    track_obj.guitar_notes.get('tuning', [40, 45, 50, 55, 59, 64])
                                )
                                
                                midi.addNote(
                                    track_idx,
                                    channel,
                                    midi_note,
                                    current_time,
                                    note_data.get('duration', 0.25),
                                    note_data.get('velocity', 100)
                                )
                                
                                current_time += note_data.get('duration', 0.25)
                            except Exception as e:
                                logger.warning(f"Error adding MIDI note: {str(e)}")
                                continue
            
            # Save MIDI file
            temp_file = tempfile.NamedTemporaryFile(
                suffix='.mid',
                prefix=f'{self.transcription.filename}_multitrack_',
                delete=False
            )
            
            with open(temp_file.name, 'wb') as f:
                midi.writeFile(f)
            
            return temp_file.name
            
        except Exception as e:
            logger.error(f"Error generating multi-track MIDI: {str(e)}")
            return ""
    
    def generate_stem_archive(self, tracks) -> str:
        """
        Generate ZIP archive with all audio stems.
        
        Args:
            tracks: List of Track model instances
            
        Returns:
            Path to generated ZIP file
        """
        import zipfile
        import shutil
        
        try:
            # Create temporary directory for stems
            temp_dir = tempfile.mkdtemp(prefix='stems_')
            
            # Copy each track's audio file
            for track in tracks:
                if track.separated_audio:
                    try:
                        filename = f"{track.display_name.replace(' ', '_')}.wav"
                        dest_path = os.path.join(temp_dir, filename)
                        shutil.copy2(track.separated_audio.path, dest_path)
                    except Exception as e:
                        logger.warning(f"Error copying track {track.display_name}: {str(e)}")
            
            # Create ZIP archive
            zip_path = tempfile.NamedTemporaryFile(
                suffix='.zip',
                prefix=f'{self.transcription.filename}_stems_',
                delete=False
            ).name
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, temp_dir)
                        zipf.write(file_path, arcname)
            
            # Clean up temp directory
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            return zip_path
            
        except Exception as e:
            logger.error(f"Error generating stems archive: {str(e)}")
            return ""
    
    def export_multitrack(self, format_type: str, tracks) -> Optional[str]:
        """
        Main method to export multi-track transcription.
        
        Args:
            format_type: Export format ('musicxml', 'midi', 'stems')
            tracks: List of Track model instances
            
        Returns:
            Path to exported file or None
        """
        if not tracks:
            logger.warning("No tracks provided for multi-track export")
            return None
        
        if format_type == 'musicxml':
            xml_content = self.generate_multitrack_musicxml(tracks)
            if xml_content:
                temp_file = tempfile.NamedTemporaryFile(
                    suffix='.xml',
                    prefix=f'{self.transcription.filename}_multitrack_',
                    delete=False,
                    mode='w'
                )
                temp_file.write(xml_content)
                temp_file.close()
                return temp_file.name
                
        elif format_type == 'midi':
            return self.generate_multitrack_midi(tracks)
            
        elif format_type == 'stems':
            return self.generate_stem_archive(tracks)
            
        else:
            logger.error(f"Unsupported multi-track export format: {format_type}")
            return None