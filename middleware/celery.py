import os
from pathlib import Path

from celery import Celery
from dotenv import load_dotenv

# The worker and beat processes don't go through manage.py/wsgi.py, so load .env here too.
load_dotenv(Path(__file__).resolve().parent.parent / '.env')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'middleware.settings')

app = Celery('middleware')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
