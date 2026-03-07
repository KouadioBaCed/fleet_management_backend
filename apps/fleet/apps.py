from django.apps import AppConfig


class FleetConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.fleet'
    verbose_name = 'Gestion de flotte'

    def ready(self):
        # Importer les signaux pour les enregistrer
        import apps.fleet.signals  # noqa: F401
