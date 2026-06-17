# Charger l'app Celery au demarrage de Django pour que le decorateur
# @shared_task utilise cette instance (et que .delay() fonctionne cote web).
from .celery import app as celery_app

__all__ = ('celery_app',)
