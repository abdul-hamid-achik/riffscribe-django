import json
import pytest
from django.test import Client
from unittest.mock import patch, MagicMock

@pytest.mark.unit
def test_task_status_success_json():
    client = Client()
    with patch('transcriber.views.AsyncResult') as mock_async_result_class:
        # Configure the mock instance that gets returned when AsyncResult('test-task-id') is called
        mock_result_instance = MagicMock()
        # Explicitly set state to SUCCESS (not PENDING which is default)
        mock_result_instance.state = 'SUCCESS'
        mock_result_instance.info = {'status': 'Done'}
        mock_async_result_class.return_value = mock_result_instance
        
        resp = client.get('/task/test-task-id/status/')
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['state'] == 'SUCCESS'
        assert data['task_id'] == 'test-task-id'
        assert 'status' in data
