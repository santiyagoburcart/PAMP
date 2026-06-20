import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pamp.settings')

app = Celery('pamp')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
