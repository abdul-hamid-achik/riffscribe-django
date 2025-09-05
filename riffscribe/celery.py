import os
from celery import Celery
from django.conf import settings

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'riffscribe.settings')

app = Celery('riffscribe')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Celery beat schedule for periodic tasks
app.conf.beat_schedule = {
    'cleanup-old-transcriptions': {
        'task': 'transcriber.tasks.cleanup_old_transcriptions',
        'schedule': 86400.0,  # Run daily
    },
}

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')