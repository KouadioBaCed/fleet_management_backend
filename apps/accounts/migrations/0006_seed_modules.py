"""Seed des modules + activation pour les organisations existantes.

- Crée les lignes ``Module`` à partir du registre de code.
- Active TOUS les modules pour chaque organisation existante afin de préserver
  le comportement historique (toutes les organisations avaient accès à tout).
"""

from django.db import migrations


def seed_modules(apps, schema_editor):
    Module = apps.get_model('accounts', 'Module')
    Organization = apps.get_model('accounts', 'Organization')

    # Import du registre (sûr : ce sont des données pures, pas de modèle).
    from apps.accounts.modules import sync_modules

    sync_modules(Module)

    all_modules = list(Module.objects.filter(is_active=True))
    for organization in Organization.objects.all():
        organization.modules.set(all_modules)


def unseed_modules(apps, schema_editor):
    Module = apps.get_model('accounts', 'Module')
    Module.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_module_organization_modules'),
    ]

    operations = [
        migrations.RunPython(seed_modules, unseed_modules),
    ]
