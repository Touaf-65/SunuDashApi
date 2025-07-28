import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sunu_dash.settings')

app = Celery('sunu_dash')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
