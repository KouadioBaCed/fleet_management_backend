from django.db import models
from django.utils import timezone


class TripStop(models.Model):
    """Modele representant un arret detecte automatiquement pendant un trajet"""

    trip = models.ForeignKey(
        'fleet.Trip',
        on_delete=models.CASCADE,
        related_name='stops',
        verbose_name='Trajet'
    )

    REASON_CHOICES = [
        ('delivery', 'Livraison'),
        ('client', 'Client'),
        ('mechanical', 'Panne'),
        ('checkpoint', 'Controle'),
        ('other', 'Autre'),
    ]

    reason = models.CharField(
        max_length=20,
        choices=REASON_CHOICES,
        verbose_name='Raison'
    )
    notes = models.TextField(
        blank=True,
        verbose_name='Notes'
    )

    # Timing
    stopped_at = models.DateTimeField(
        verbose_name='Heure de l\'arret'
    )
    duration_seconds = models.IntegerField(
        default=0,
        verbose_name='Duree de l\'arret (secondes)'
    )

    # Localisation
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

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'trip_stops'
        verbose_name = 'Arret de trajet'
        verbose_name_plural = 'Arrets de trajet'
        ordering = ['-stopped_at']

    def __str__(self):
        return f"Arret {self.get_reason_display()} - Trajet {self.trip_id}"
