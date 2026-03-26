from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class GPSLocationPoint(models.Model):
    """Modèle représentant un point GPS enregistré"""

    trip = models.ForeignKey(
        'fleet.Trip',
        on_delete=models.CASCADE,
        related_name='location_points',
        verbose_name='Trajet'
    )

    # Coordonnées
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
    altitude = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Altitude'
    )

    # Précision
    accuracy = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        help_text='Précision en mètres',
        verbose_name='Précision'
    )

    # Vitesse et direction
    speed = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text='km/h',
        verbose_name='Vitesse'
    )
    heading = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(360)],
        help_text='Direction en degrés',
        verbose_name='Cap'
    )

    # Timestamp
    recorded_at = models.DateTimeField(verbose_name='Enregistré à')

    # Données supplémentaires
    battery_level = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name='Niveau batterie'
    )
    is_moving = models.BooleanField(default=True, verbose_name='Mission')

    class Meta:
        db_table = 'gps_location_points'
        verbose_name = 'Point GPS'
        verbose_name_plural = 'Points GPS'
        ordering = ['recorded_at']
        indexes = [
            models.Index(fields=['trip', 'recorded_at']),
            models.Index(fields=['recorded_at']),
        ]

    def __str__(self):
        return f"Point GPS - {self.recorded_at}"
