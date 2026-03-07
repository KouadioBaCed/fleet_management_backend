"""
Configuration locale pour le développement (utilise SQLite)
Usage: python manage.py makemigrations --settings=config.settings.local
"""

from .base import *

# Utiliser SQLite pour le développement local
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Désactiver Redis pour Channels en local
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

# Debug activé
DEBUG = True
