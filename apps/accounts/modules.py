"""
Registre central des modules de la plateforme.

C'est la **source de vérité unique** des modules disponibles. Pour ajouter un
nouveau module à la plateforme :

1. Ajoutez une constante dans :class:`Modules`.
2. Ajoutez une entrée dans :data:`MODULE_REGISTRY`.
3. Lancez ``python manage.py sync_modules`` (ou appliquez la migration de
   synchronisation) pour propager le module en base.
4. Côté ViewSet/endpoint, déclarez ``required_module = Modules.<CODE>`` (ou
   utilisez ``RequireModule(Modules.<CODE>)`` pour les vues fonctionnelles).
5. Côté frontend, ajoutez l'entrée correspondante dans ``src/config/modules.ts``.

Aucune autre partie du code ne doit "hardcoder" la liste des modules : tout
passe par ce registre.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleDefinition:
    """Définition immuable d'un module fonctionnel."""

    code: str
    name: str
    description: str = ""
    #: Ordre d'affichage (sidebar, listes admin...). Plus petit = plus haut.
    order: int = 100


class Modules:
    """Codes canoniques des modules (à utiliser partout dans le code)."""

    DASHBOARD = "dashboard"
    INCIDENTS = "incidents"
    VEHICLES = "vehicles"
    DRIVERS = "drivers"
    MISSIONS = "missions"
    TRACKING = "tracking"
    MAINTENANCE = "maintenance"
    FUEL = "fuel"
    ANALYTICS = "analytics"
    REPORTS = "reports"


MODULE_REGISTRY: "dict[str, ModuleDefinition]" = {
    m.code: m
    for m in [
        ModuleDefinition(Modules.DASHBOARD, "Tableau de bord", "Vue d'ensemble et statistiques", order=10),
        ModuleDefinition(Modules.INCIDENTS, "Incidents", "Déclaration et suivi des incidents", order=20),
        ModuleDefinition(Modules.VEHICLES, "Véhicules", "Gestion du parc de véhicules", order=30),
        ModuleDefinition(Modules.DRIVERS, "Chauffeurs", "Gestion des chauffeurs", order=40),
        ModuleDefinition(Modules.MISSIONS, "Missions", "Planification et suivi des missions", order=50),
        ModuleDefinition(Modules.TRACKING, "Suivi GPS", "Suivi des véhicules en temps réel", order=60),
        ModuleDefinition(Modules.MAINTENANCE, "Maintenance", "Entretien et réparations", order=70),
        ModuleDefinition(Modules.FUEL, "Carburant", "Suivi des ravitaillements", order=80),
        ModuleDefinition(Modules.ANALYTICS, "Analyses", "Analyses de performance", order=90),
        ModuleDefinition(Modules.REPORTS, "Rapports", "Génération de rapports", order=100),
    ]
}

#: Tous les codes de modules connus.
ALL_MODULE_CODES = list(MODULE_REGISTRY.keys())

#: Modules activés par défaut à la création d'une organisation.
#: Par défaut on active **tout** (rétro-compatibilité : aujourd'hui toutes les
#: organisations ont accès à tous les modules). Un admin peut ensuite restreindre
#: une organisation au seul module ``incidents`` par exemple.
DEFAULT_ENABLED_MODULES = list(ALL_MODULE_CODES)


def sync_modules(module_model) -> int:
    """Synchronise la table ``Module`` avec :data:`MODULE_REGISTRY`.

    Utilisable aussi bien avec le modèle réel (commande de management) qu'avec
    un modèle historique (migration de données). Idempotent.

    :param module_model: la classe du modèle ``Module``.
    :returns: le nombre de modules synchronisés.
    """
    for definition in MODULE_REGISTRY.values():
        module_model.objects.update_or_create(
            code=definition.code,
            defaults={
                "name": definition.name,
                "description": definition.description,
                "order": definition.order,
                "is_active": True,
            },
        )
    return len(MODULE_REGISTRY)
