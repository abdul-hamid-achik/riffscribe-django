import json
import pytest
from django.test import Client
from unittest.mock import patch, MagicMock, PropertyMock

@pytest.mark.unit
def test_task_status_success_json():
    client = Client()
    with patch('transcriber.views.transcription.AsyncResult') as mock_async_result_class:
        # Create a mock result instance
        mock_result_instance = MagicMock()
        
        # Mock the state property correctly
        mock_result_instance.configure_mock(state='SUCCESS')
        mock_result_instance.info = {'status': 'Done', 'result': 'Task completed'}
        
        # Ensure AsyncResult returns our mock when called
        mock_async_result_class.return_value = mock_result_instance
        
        resp = client.get('/task/test-task-id/status/')
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['state'] == 'SUCCESS'
        assert data['task_id'] == 'test-task-id'
        assert 'status' in data
