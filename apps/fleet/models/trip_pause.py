from django.db import models
from django.utils import timezone


class TripPause(models.Model):
    """Modele representant une periode de pause pendant un trajet"""

    trip = models.ForeignKey(
        'fleet.Trip',
        on_delete=models.CASCADE,
        related_name='pauses',
        verbose_name='Trajet'
    )

    # Timing
    started_at = models.DateTimeField(
        verbose_name='Debut de la pause'
    )
    ended_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fin de la pause'
    )
    duration_minutes = models.IntegerField(
        default=0,
        verbose_name='Duree (minutes)'
    )

    # Raison optionnelle
    REASON_CHOICES = [
        ('break', 'Pause'),
        ('meal', 'Repas'),
        ('fuel', 'Ravitaillement'),
        ('traffic', 'Trafic'),
        ('other', 'Autre'),
    ]
    reason = models.CharField(
        max_length=20,
        choices=REASON_CHOICES,
        default='break',
        verbose_name='Raison'
    )
    notes = models.TextField(
        blank=True,
        verbose_name='Notes'
    )

    # Localisation au moment de la pause
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
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'trip_pauses'
        verbose_name = 'Pause de trajet'
        verbose_name_plural = 'Pauses de trajet'
        ordering = ['-started_at']

    def __str__(self):
        return f"Pause {self.id} - Trajet {self.trip_id}"

    @property
    def is_active(self):
        return self.ended_at is None

    def end_pause(self):
        """Termine la pause et calcule la duree"""
        if self.ended_at is None:
            self.ended_at = timezone.now()
            delta = self.ended_at - self.started_at
            self.duration_minutes = int(delta.total_seconds() / 60)
            self.save()

            # Mettre a jour le total des pauses sur le trajet
            self.trip.pause_duration_minutes = sum(
                p.duration_minutes for p in self.trip.pauses.all()
            )
            self.trip.save(update_fields=['pause_duration_minutes'])
