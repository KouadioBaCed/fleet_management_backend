from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class Trip(models.Model):
    """Modèle représentant un trajet effectué"""

    organization = models.ForeignKey(
        'accounts.Organization',
        on_delete=models.CASCADE,
        related_name='trips',
        verbose_name='Organisation',
        null=True,
        blank=True
    )

    STATUS_CHOICES = [
        ('active', 'Actif'),
        ('paused', 'En pause'),
        ('completed', 'Terminé'),
        ('cancelled', 'Annulé'),
    ]

    # Relations
    mission = models.OneToOneField(
        'fleet.Mission',
        on_delete=models.CASCADE,
        related_name='trip',
        verbose_name='Mission'
    )
    vehicle = models.ForeignKey(
        'fleet.Vehicle',
        on_delete=models.PROTECT,
        related_name='trips',
        verbose_name='Véhicule'
    )
    driver = models.ForeignKey(
        'fleet.Driver',
        on_delete=models.PROTECT,
        related_name='trips',
        verbose_name='Chauffeur'
    )

    # Timing
    start_time = models.DateTimeField(verbose_name='Heure de départ')
    end_time = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Heure d\'arrivée'
    )
    total_duration_minutes = models.IntegerField(
        default=0,
        verbose_name='Durée totale (minutes)'
    )
    pause_duration_minutes = models.IntegerField(
        default=0,
        verbose_name='Durée de pause (minutes)'
    )

    # Métriques - Kilométrage
    start_mileage = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Kilométrage de départ'
    )
    end_mileage = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Kilométrage d\'arrivée'
    )
    total_distance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text='Kilomètres',
        verbose_name='Distance totale'
    )

    # Carburant
    start_fuel_level = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Pourcentage',
        verbose_name='Niveau carburant départ'
    )
    end_fuel_level = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Pourcentage',
        verbose_name='Niveau carburant arrivée'
    )
    fuel_consumed = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        help_text='Litres',
        verbose_name='Carburant consommé'
    )

    # Performance
    average_speed = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text='km/h',
        verbose_name='Vitesse moyenne'
    )
    max_speed = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text='km/h',
        verbose_name='Vitesse maximale'
    )

    # État
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        verbose_name='Statut'
    )
    has_incidents = models.BooleanField(
        default=False,
        verbose_name='A des incidents'
    )
    has_alerts = models.BooleanField(
        default=False,
        verbose_name='A des alertes'
    )

    # Metadata
    notes = models.TextField(blank=True, verbose_name='Notes')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Date de création')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Date de mise à jour')

    class Meta:
        db_table = 'trips'
        verbose_name = 'Trajet'
        verbose_name_plural = 'Trajets'
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['status', 'start_time']),
            models.Index(fields=['driver', 'start_time']),
        ]

    def __str__(self):
        return f"Trajet {self.id} - {self.mission.mission_code}"

    @property
    def is_active(self):
        return self.status == 'active'

    @property
    def is_completed(self):
        return self.status == 'completed'

    @property
    def duration(self):
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return None
