from django.db import models


class MissionAlert(models.Model):
    """Modele representant une alerte de mission (retard, deviation, etc.)"""

    ALERT_TYPE_CHOICES = [
        ('delay_start', 'Retard au demarrage'),
        ('delay_progress', 'Retard en cours'),
        ('delay_arrival', 'Retard a l\'arrivee'),
        ('route_deviation', 'Deviation de route'),
        ('long_stop', 'Arret prolonge'),
        ('speed_violation', 'Exces de vitesse'),
        ('geofence_exit', 'Sortie de zone'),
    ]

    SEVERITY_CHOICES = [
        ('info', 'Information'),
        ('warning', 'Avertissement'),
        ('critical', 'Critique'),
    ]

    mission = models.ForeignKey(
        'fleet.Mission',
        on_delete=models.CASCADE,
        related_name='alerts',
        verbose_name='Mission'
    )

    alert_type = models.CharField(
        max_length=30,
        choices=ALERT_TYPE_CHOICES,
        verbose_name='Type d\'alerte'
    )

    severity = models.CharField(
        max_length=20,
        choices=SEVERITY_CHOICES,
        default='warning',
        verbose_name='Severite'
    )

    title = models.CharField(max_length=200, verbose_name='Titre')
    message = models.TextField(verbose_name='Message')

    # Donnees supplementaires
    delay_minutes = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Retard en minutes'
    )

    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        verbose_name='Latitude'
    )
    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        verbose_name='Longitude'
    )

    # Statut
    is_acknowledged = models.BooleanField(
        default=False,
        verbose_name='Acquittee'
    )
    acknowledged_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Acquittee a'
    )
    acknowledged_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='acknowledged_alerts',
        verbose_name='Acquittee par'
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Date de creation')

    class Meta:
        db_table = 'mission_alerts'
        verbose_name = 'Alerte mission'
        verbose_name_plural = 'Alertes mission'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['mission', 'alert_type']),
            models.Index(fields=['is_acknowledged', 'created_at']),
        ]

    def __str__(self):
        return f"{self.get_alert_type_display()} - {self.mission.mission_code}"
