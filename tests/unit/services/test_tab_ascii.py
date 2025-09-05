import pytest
from transcriber.services.tab_generator import TabGenerator

@pytest.mark.unit
def test_to_ascii_tab_with_techniques():
    notes = [
        {'start_time': 0.0, 'end_time': 0.25, 'midi_note': 64, 'velocity': 90},
        {'start_time': 0.3, 'end_time': 0.5, 'midi_note': 66, 'velocity': 90},
        {'start_time': 0.6, 'end_time': 0.8, 'midi_note': 64, 'velocity': 90},
    ]
    gen = TabGenerator(notes, tempo=120, time_signature='4/4')
    ascii_tab = gen.to_ascii_tab(measures_per_line=2)
    assert '|' in ascii_tab
    assert len(ascii_tab.strip()) > 0
