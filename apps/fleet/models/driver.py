from django.db import models
from django.conf import settings


class Driver(models.Model):
    """Modèle représentant un chauffeur"""

    organization = models.ForeignKey(
        'accounts.Organization',
        on_delete=models.CASCADE,
        related_name='drivers',
        verbose_name='Organisation',
        null=True,
        blank=True
    )

    STATUS_CHOICES = [
        ('available', 'Disponible'),
        ('on_mission', 'En mission'),
        ('on_break', 'En pause'),
        ('off_duty', 'Hors service'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='driver_profile',
        verbose_name='Utilisateur'
    )

    # Identification
    employee_id = models.CharField(
        max_length=20,
        unique=True,
        verbose_name='ID employé'
    )
    driver_license_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='Numéro de permis'
    )
    driver_license_expiry = models.DateField(verbose_name='Expiration permis')
    driver_license_category = models.CharField(
        max_length=10,
        verbose_name='Catégorie permis',
        help_text='B, C, D, etc.'
    )

    # Contact d'urgence
    emergency_contact_name = models.CharField(
        max_length=100,
        verbose_name='Contact d\'urgence (nom)'
    )
    emergency_contact_phone = models.CharField(
        max_length=20,
        verbose_name='Contact d\'urgence (téléphone)'
    )

    # État
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='available',
        verbose_name='Statut'
    )
    current_vehicle = models.ForeignKey(
        'fleet.Vehicle',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='current_driver',
        verbose_name='Véhicule actuel'
    )

    # Statistiques
    total_trips = models.IntegerField(default=0, verbose_name='Total trajets')
    total_distance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Distance totale (km)'
    )
    rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0,
        verbose_name='Note'
    )

    # Metadata
    hire_date = models.DateField(verbose_name='Date d\'embauche')
    notes = models.TextField(blank=True, verbose_name='Notes')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Date de création')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Date de mise à jour')

    class Meta:
        db_table = 'drivers'
        verbose_name = 'Chauffeur'
        verbose_name_plural = 'Chauffeurs'
        ordering = ['user__last_name', 'user__first_name']

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.employee_id})"

    @property
    def full_name(self):
        return self.user.get_full_name()

    @property
    def is_available(self):
        return self.status == 'available'

    @property
    def is_on_mission(self):
        return self.status == 'on_mission'
