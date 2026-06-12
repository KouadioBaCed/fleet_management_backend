"""Signaux de l'app accounts."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Organization, Module
from .modules import DEFAULT_ENABLED_MODULES


@receiver(post_save, sender=Organization)
def assign_default_modules(sender, instance, created, **kwargs):
    """Active les modules par défaut à la création d'une nouvelle organisation.

    Cela préserve le comportement historique (toutes les organisations ont
    accès à tous les modules). Un administrateur peut ensuite restreindre
    l'organisation depuis l'admin Django.

    Les modèles historiques utilisés par les migrations n'étant pas reliés à ce
    signal, le backfill des organisations existantes reste géré par la migration
    de données dédiée.
    """
    if not created:
        return

    modules = Module.objects.filter(
        code__in=DEFAULT_ENABLED_MODULES,
        is_active=True,
    )
    if modules.exists():
        instance.modules.set(modules)
