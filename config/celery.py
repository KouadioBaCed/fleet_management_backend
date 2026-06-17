"""Application Celery du projet.

Permet l'execution asynchrone des taches (@shared_task) et la planification
periodique via Celery Beat (voir CELERY_BEAT_SCHEDULE dans les settings).

Lancement en production :
    celery -A config worker -l info
    celery -A config beat -l info
"""
import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

app = Celery('config')

# Lit toutes les variables prefixees CELERY_ depuis les settings Django.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Decouvre automatiquement les modules tasks.py de chaque app installee.
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
