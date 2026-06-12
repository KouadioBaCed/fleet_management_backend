from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'
    verbose_name = 'Comptes utilisateurs'

    def ready(self):
        # Enregistre les signaux (attribution des modules par défaut, etc.)
        from . import signals  # noqa: F401
 