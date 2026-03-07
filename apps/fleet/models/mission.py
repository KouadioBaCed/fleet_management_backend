from django.db import models
from django.core.validators import MinValueValidator
from django.conf import settings


class Mission(models.Model):
    """Modèle représentant une mission assignée"""

    organization = models.ForeignKey(
        'accounts.Organization',
        on_delete=models.CASCADE,
        related_name='missions',
        verbose_name='Organisation',
        null=True,
        blank=True
    )

    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('assigned', 'Assignée'),
        ('in_progress', 'En cours'),
        ('completed', 'Terminée'),
        ('cancelled', 'Annulée'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Faible'),
        ('medium', 'Moyenne'),
        ('high', 'Haute'),
        ('urgent', 'Urgente'),
    ]

    # Identification
    mission_code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='Code mission'
    )
    title = models.CharField(max_length=200, verbose_name='Titre')
    description = models.TextField(verbose_name='Description')

    # Assignation
    vehicle = models.ForeignKey(
        'fleet.Vehicle',
        on_delete=models.PROTECT,
        related_name='missions',
        verbose_name='Véhicule'
    )
    driver = models.ForeignKey(
        'fleet.Driver',
        on_delete=models.PROTECT,
        related_name='missions',
        verbose_name='Chauffeur'
    )

    # Planning
    scheduled_start = models.DateTimeField(verbose_name='Début prévu')
    scheduled_end = models.DateTimeField(verbose_name='Fin prévue')
    actual_start = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Début réel'
    )
    actual_end = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fin réelle'
    )

    # Localisation - Origine
    origin_address = models.CharField(max_length=255, verbose_name='Adresse origine')
    origin_latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        verbose_name='Latitude origine'
    )
    origin_longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        verbose_name='Longitude origine'
    )

    # Localisation - Destination
    destination_address = models.CharField(max_length=255, verbose_name='Adresse destination')
    destination_latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        verbose_name='Latitude destination'
    )
    destination_longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        verbose_name='Longitude destination'
    )

    # Détails
    estimated_distance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text='Kilomètres',
        verbose_name='Distance estimée'
    )
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default='medium',
        verbose_name='Priorité'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Statut'
    )

    # Responsable à destination
    responsible_person_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Nom du responsable'
    )
    responsible_person_phone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name='Téléphone du responsable'
    )
    signature = models.ImageField(
        upload_to='signatures/',
        null=True,
        blank=True,
        verbose_name='Signature'
    )

    # Annulation
    cancellation_reason = models.TextField(
        blank=True,
        verbose_name='Motif d\'annulation'
    )
    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Date d\'annulation'
    )
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cancelled_missions',
        verbose_name='Annule par'
    )

    # Metadata
    notes = models.TextField(blank=True, verbose_name='Notes')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_missions',
        verbose_name='Créé par'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Date de création')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Date de mise à jour')

    class Meta:
        db_table = 'missions'
        verbose_name = 'Mission'
        verbose_name_plural = 'Missions'
        ordering = ['-scheduled_start']
        indexes = [
            models.Index(fields=['status', 'scheduled_start']),
            models.Index(fields=['driver', 'status']),
        ]

    def __str__(self):
        return f"{self.mission_code} - {self.title}"

    @property
    def is_active(self):
        return self.status == 'in_progress'

    @property
    def is_completed(self):
        return self.status == 'completed'

    @property
    def duration(self):
        if self.actual_start and self.actual_end:
            return self.actual_end - self.actual_start
        return None
