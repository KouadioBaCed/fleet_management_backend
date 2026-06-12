"""
Configuration de PRODUCTION.

Sert le backend sur https://fleet.dfleetci.com derriere le reverse proxy nginx
(qui gere le TLS). Activer via la variable d'environnement :

    DJANGO_SETTINGS_MODULE=config.settings.production

Toutes les valeurs sensibles (SECRET_KEY, hosts, CORS, email, Redis...) sont
lues depuis le fichier .env du serveur (voir .env.production comme modele).
"""

from .base import *  # noqa: F401,F403

# DEBUG est toujours desactive en production, quelle que soit la valeur du .env.
DEBUG = False

# Garde-fou : refuser de demarrer en prod avec la cle par defaut.
if SECRET_KEY in ('django-insecure-change-this-in-production',
                  'CHANGE-THIS-TO-A-REAL-SECRET-KEY'):
    raise RuntimeError(
        "SECRET_KEY n'est pas configuree pour la production. "
        "Definissez SECRET_KEY dans le fichier .env du serveur."
    )

# Email : en prod on envoie reellement les mails (SMTP) au lieu de la console.
EMAIL_BACKEND = config(
    'EMAIL_BACKEND',
    default='django.core.mail.backends.smtp.EmailBackend'
)

# Channels : on garde le backend Redis defini dans base.py (pas d'override
# InMemory comme en dev) — necessaire pour la live-map en multi-process.

# Renforcement HTTPS supplementaire (le TLS est termine par nginx).
# SECURE_SSL_REDIRECT / *_COOKIE_SECURE / SECURE_PROXY_SSL_HEADER viennent
# deja de base.py (pilotes par .env). On ajoute HSTS ici.
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config(
    'SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True, cast=bool
)
SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=True, cast=bool)

# Logging : tout vers la console (capte par daphne / systemd / journalctl).
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}
