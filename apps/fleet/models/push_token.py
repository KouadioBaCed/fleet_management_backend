from django.db import models
from django.utils import timezone


class DriverPushToken(models.Model):
    """Jeton de notification push (Expo) enregistre par l'app mobile d'un chauffeur.

    Un meme chauffeur peut avoir plusieurs jetons (plusieurs appareils).
    Le jeton est unique : s'il change d'appareil/de compte, on le reattribue.
    """

    PLATFORM_CHOICES = [
        ('ios', 'iOS'),
        ('android', 'Android'),
        ('web', 'Web'),
        ('unknown', 'Inconnu'),
    ]

    driver = models.ForeignKey(
        'fleet.Driver',
        on_delete=models.CASCADE,
        related_name='push_tokens',
        verbose_name='Conducteur'
    )

    token = models.CharField(
        max_length=255,
        unique=True,
        verbose_name='Jeton Expo',
        help_text="ExponentPushToken[...]"
    )

    platform = models.CharField(
        max_length=20,
        choices=PLATFORM_CHOICES,
        default='unknown',
        verbose_name='Plateforme'
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name='Actif'
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Date de creation')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Date de mise a jour')
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Derniere utilisation'
    )

    class Meta:
        db_table = 'driver_push_tokens'
        verbose_name = 'Jeton push conducteur'
        verbose_name_plural = 'Jetons push conducteur'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['driver', 'is_active']),
        ]

    def __str__(self):
        return f"{self.driver} - {self.token[:30]}"

    def mark_used(self):
        self.last_used_at = timezone.now()
        self.save(update_fields=['last_used_at'])
