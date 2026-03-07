from django.db import models
from django.core.validators import MinValueValidator


class Vehicle(models.Model):
    """Modèle représentant un véhicule de la flotte"""

    organization = models.ForeignKey(
        'accounts.Organization',
        on_delete=models.CASCADE,
        related_name='vehicles',
        verbose_name='Organisation',
        null=True,
        blank=True
    )

    STATUS_CHOICES = [
        ('available', 'Disponible'),
        ('in_use', 'En mission'),
        ('maintenance', 'En maintenance'),
        ('out_of_service', 'Hors service'),
    ]

    VEHICLE_TYPE_CHOICES = [
        ('sedan', 'Berline'),
        ('suv', 'SUV'),
        ('van', 'Camionnette'),
        ('truck', 'Camion'),
    ]

    FUEL_TYPE_CHOICES = [
        ('gasoline', 'Essence'),
        ('diesel', 'Diesel'),
        ('electric', 'Électrique'),
        ('hybrid', 'Hybride'),
    ]

    # Identification
    license_plate = models.CharField(
        max_length=20,
        unique=True,
        verbose_name='Plaque d\'immatriculation'
    )
    vin_number = models.CharField(
        max_length=17,
        unique=True,
        verbose_name='Numéro VIN'
    )

    # Caractéristiques
    brand = models.CharField(max_length=50, verbose_name='Marque')
    model = models.CharField(max_length=50, verbose_name='Modèle')
    year = models.IntegerField(validators=[MinValueValidator(1900)], verbose_name='Année')
    vehicle_type = models.CharField(
        max_length=20,
        choices=VEHICLE_TYPE_CHOICES,
        verbose_name='Type de véhicule'
    )
    color = models.CharField(max_length=30, verbose_name='Couleur')

    # Technique
    fuel_type = models.CharField(
        max_length=20,
        choices=FUEL_TYPE_CHOICES,
        verbose_name='Type de carburant'
    )
    fuel_capacity = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        help_text='Litres',
        verbose_name='Capacité du réservoir'
    )
    fuel_consumption = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text='L/100km',
        validators=[MinValueValidator(0)],
        verbose_name='Consommation'
    )

    # État
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='available',
        verbose_name='Statut'
    )
    current_mileage = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Kilométrage actuel'
    )
    last_maintenance_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='Date dernière maintenance'
    )
    next_maintenance_mileage = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Kilométrage prochaine maintenance'
    )

    # Assurance
    insurance_number = models.CharField(
        max_length=50,
        verbose_name='Numéro d\'assurance'
    )
    insurance_expiry = models.DateField(verbose_name='Expiration assurance')

    # Tracking
    gps_device_id = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        verbose_name='ID dispositif GPS'
    )

    # Metadata
    photo = models.ImageField(
        upload_to='vehicles/',
        null=True,
        blank=True,
        verbose_name='Photo'
    )
    notes = models.TextField(blank=True, verbose_name='Notes')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Date de création')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Date de mise à jour')

    class Meta:
        db_table = 'vehicles'
        verbose_name = 'Véhicule'
        verbose_name_plural = 'Véhicules'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'license_plate']),
        ]

    def __str__(self):
        return f"{self.license_plate} - {self.brand} {self.model}"

    @property
    def is_available(self):
        return self.status == 'available'

    @property
    def needs_maintenance(self):
        if self.next_maintenance_mileage:
            return self.current_mileage >= self.next_maintenance_mileage
        return False
