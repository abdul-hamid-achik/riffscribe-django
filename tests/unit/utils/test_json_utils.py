import pytest
from transcriber.utils.json_utils import ensure_json_serializable, clean_analysis_result
import numpy as np

@pytest.mark.unit
def test_ensure_json_serializable_numpy():
    data = {
        'arr': np.array([1, 2, 3]),
        'nested': {
            'x': np.float32(1.5),
            'y': np.int64(7)
        }
    }
    result = ensure_json_serializable(data)
    assert result['arr'] == [1, 2, 3]
    assert result['nested']['x'] == pytest.approx(1.5)
    assert result['nested']['y'] == 7

@pytest.mark.unit
def test_clean_analysis_result_removes_none_and_converts_types():
    analysis = {
        'duration': np.float64(12.3),
        'segments': None,
        'instruments': np.array(['guitar', 'drums'])
    }
    result = clean_analysis_result(analysis)
    assert 'segments' not in result
    assert result['duration'] == pytest.approx(12.3)
    assert result['instruments'] == ['guitar', 'drums']
