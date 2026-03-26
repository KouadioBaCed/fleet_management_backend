from django.db import models
from django.conf import settings


class Incident(models.Model):
    """Modèle représentant un incident durant un trajet"""

    organization = models.ForeignKey(
        'accounts.Organization',
        on_delete=models.CASCADE,
        related_name='incidents',
        verbose_name='Organisation',
        null=True,
        blank=True
    )

    SEVERITY_CHOICES = [
        ('minor', 'Mineur'),
        ('moderate', 'Modéré'),
        ('major', 'Majeur'),
        ('critical', 'Critique'),
    ]

    TYPE_CHOICES = [
        ('flat_tire', 'Pneu crevé'),
        ('breakdown', 'Panne'),
        ('accident', 'Accident'),
        ('fuel_issue', 'Problème carburant'),
        ('traffic_violation', 'Infraction'),
        ('other', 'Autre'),
    ]

    # Relations
    trip = models.ForeignKey(
        'fleet.Trip',
        on_delete=models.CASCADE,
        related_name='incidents',
        verbose_name='Trajet',
        null=True,
        blank=True
    )
    driver = models.ForeignKey(
        'fleet.Driver',
        on_delete=models.PROTECT,
        related_name='incidents',
        verbose_name='Chauffeur',
        null=True,
        blank=True
    )
    vehicle = models.ForeignKey(
        'fleet.Vehicle',
        on_delete=models.PROTECT,
        related_name='incidents',
        verbose_name='Véhicule',
        null=True,
        blank=True
    )

    # Détails
    incident_type = models.CharField(
        max_length=30,
        choices=TYPE_CHOICES,
        verbose_name='Type d\'incident'
    )
    severity = models.CharField(
        max_length=20,
        choices=SEVERITY_CHOICES,
        verbose_name='Gravité'
    )
    title = models.CharField(max_length=200, verbose_name='Titre')
    description = models.TextField(verbose_name='Description')

    # Localisation
    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        verbose_name='Latitude'
    )
    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        verbose_name='Longitude'
    )
    address = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Adresse'
    )

    # Documentation
    photo1 = models.ImageField(
        upload_to='incidents/',
        null=True,
        blank=True,
        verbose_name='Photo 1'
    )
    photo2 = models.ImageField(
        upload_to='incidents/',
        null=True,
        blank=True,
        verbose_name='Photo 2'
    )
    photo3 = models.ImageField(
        upload_to='incidents/',
        null=True,
        blank=True,
        verbose_name='Photo 3'
    )

    # Facture / preuve de réparation
    repair_invoice = models.FileField(
        upload_to='incidents/invoices/',
        null=True,
        blank=True,
        verbose_name='Facture de réparation'
    )
    repair_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Coût de réparation'
    )

    # Résolution
    is_resolved = models.BooleanField(
        default=False,
        verbose_name='Résolu'
    )
    resolution_notes = models.TextField(
        blank=True,
        verbose_name='Notes de résolution'
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Résolu à'
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_incidents',
        verbose_name='Résolu par'
    )

    # Coûts
    estimated_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Coût estimé'
    )

    # Metadata
    reported_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Signalé à'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Mis à jour à'
    )

    class Meta:
        db_table = 'incidents'
        verbose_name = 'Incident'
        verbose_name_plural = 'Incidents'
        ordering = ['-reported_at']
        indexes = [
            models.Index(fields=['is_resolved', 'severity']),
            models.Index(fields=['vehicle', 'reported_at']),
        ]

    def __str__(self):
        return f"{self.get_incident_type_display()} - {self.title}"
