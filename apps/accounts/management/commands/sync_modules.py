"""Synchronise la table ``Module`` avec le registre de code.

Usage::

    python manage.py sync_modules
    python manage.py sync_modules --enable-all   # (ré)active tous les modules
                                                  # pour toutes les organisations
"""

from django.core.management.base import BaseCommand

from apps.accounts.models import Module, Organization
from apps.accounts.modules import sync_modules, DEFAULT_ENABLED_MODULES


class Command(BaseCommand):
    help = "Synchronise les modules du registre de code vers la base de données."

    def add_arguments(self, parser):
        parser.add_argument(
            '--enable-all',
            action='store_true',
            help="Active tous les modules par défaut pour toutes les organisations.",
        )

    def handle(self, *args, **options):
        count = sync_modules(Module)
        self.stdout.write(self.style.SUCCESS(f"{count} module(s) synchronisé(s)."))

        if options['enable_all']:
            modules = Module.objects.filter(code__in=DEFAULT_ENABLED_MODULES, is_active=True)
            orgs = Organization.objects.all()
            for org in orgs:
                org.modules.set(modules)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Tous les modules activés pour {orgs.count()} organisation(s)."
                )
            )
