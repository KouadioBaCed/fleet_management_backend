from django.db import models
from django.conf import settings


class Activity(models.Model):
    """Modèle pour le suivi des activités de la flotte"""

    ACTIVITY_TYPES = [
        # Missions
        ('mission_created', 'Mission créée'),
        ('mission_started', 'Mission démarrée'),
        ('mission_completed', 'Mission terminée'),
        ('mission_cancelled', 'Mission annulée'),
        # Incidents
        ('incident_reported', 'Incident signalé'),
        ('incident_resolved', 'Incident résolu'),
        # Véhicules
        ('vehicle_status_changed', 'Statut véhicule changé'),
        ('vehicle_created', 'Véhicule ajouté'),
        ('vehicle_maintenance', 'Maintenance véhicule'),
        # Chauffeurs
        ('driver_status_changed', 'Statut chauffeur changé'),
        ('driver_created', 'Chauffeur ajouté'),
        # Trajets
        ('trip_started', 'Trajet démarré'),
        ('trip_paused', 'Trajet en pause'),
        ('trip_resumed', 'Trajet repris'),
        ('trip_completed', 'Trajet terminé'),
    ]

    SEVERITY_CHOICES = [
        ('info', 'Information'),
        ('warning', 'Avertissement'),
        ('success', 'Succès'),
        ('error', 'Erreur'),
    ]

    organization = models.ForeignKey(
        'accounts.Organization',
        on_delete=models.CASCADE,
        related_name='activities',
        verbose_name='Organisation',
        null=True,
        blank=True
    )

    activity_type = models.CharField(
        max_length=50,
        choices=ACTIVITY_TYPES,
        verbose_name='Type d\'activité'
    )
    severity = models.CharField(
        max_length=20,
        choices=SEVERITY_CHOICES,
        default='info',
        verbose_name='Sévérité'
    )
    title = models.CharField(max_length=200, verbose_name='Titre')
    description = models.TextField(blank=True, verbose_name='Description')

    # Relations optionnelles
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activities',
        verbose_name='Utilisateur'
    )
    vehicle = models.ForeignKey(
        'fleet.Vehicle',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activities',
        verbose_name='Véhicule'
    )
    driver = models.ForeignKey(
        'fleet.Driver',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activities',
        verbose_name='Chauffeur'
    )
    mission = models.ForeignKey(
        'fleet.Mission',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activities',
        verbose_name='Mission'
    )
    incident = models.ForeignKey(
        'fleet.Incident',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activities',
        verbose_name='Incident'
    )

    # Métadonnées additionnelles (JSON)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Métadonnées'
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Date de création'
    )

    class Meta:
        db_table = 'activities'
        verbose_name = 'Activité'
        verbose_name_plural = 'Activités'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', '-created_at']),
            models.Index(fields=['activity_type', '-created_at']),
        ]

    def __str__(self):
        return f"{self.get_activity_type_display()} - {self.title}"

    @classmethod
    def log(cls, activity_type, title, organization=None, severity='info', **kwargs):
        """Méthode utilitaire pour créer une activité"""
        return cls.objects.create(
            activity_type=activity_type,
            title=title,
            organization=organization,
            severity=severity,
            **kwargs
        )
