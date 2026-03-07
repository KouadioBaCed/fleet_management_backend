from django.db import models
from django.core.validators import MinValueValidator


class FuelRecord(models.Model):
    """Modèle représentant un enregistrement de ravitaillement en carburant"""

    organization = models.ForeignKey(
        'accounts.Organization',
        on_delete=models.CASCADE,
        related_name='fuel_records',
        verbose_name='Organisation',
        null=True,
        blank=True
    )

    FUEL_TYPE_CHOICES = [
        ('gasoline', 'Essence'),
        ('diesel', 'Diesel'),
        ('electric', 'Électrique'),
    ]

    # Relations
    vehicle = models.ForeignKey(
        'fleet.Vehicle',
        on_delete=models.CASCADE,
        related_name='fuel_records',
        verbose_name='Véhicule'
    )
    driver = models.ForeignKey(
        'fleet.Driver',
        on_delete=models.SET_NULL,
        null=True,
        related_name='fuel_records',
        verbose_name='Chauffeur'
    )
    trip = models.ForeignKey(
        'fleet.Trip',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fuel_records',
        verbose_name='Trajet'
    )

    # Date et localisation
    refuel_date = models.DateTimeField(verbose_name='Date de ravitaillement')
    station_name = models.CharField(max_length=100, verbose_name='Nom de la station')
    station_address = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Adresse de la station'
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

    # Carburant
    fuel_type = models.CharField(
        max_length=20,
        choices=FUEL_TYPE_CHOICES,
        verbose_name='Type de carburant'
    )
    quantity = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text='Litres ou kWh',
        verbose_name='Quantité'
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        verbose_name='Prix unitaire'
    )
    total_cost = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name='Coût total'
    )

    # Kilométrage
    mileage_at_refuel = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Kilométrage au ravitaillement'
    )

    # Consommation calculée
    distance_since_last_refuel = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Distance depuis dernier plein'
    )
    calculated_consumption = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='L/100km',
        verbose_name='Consommation calculée'
    )

    # Plein ou partiel
    is_full_tank = models.BooleanField(
        default=True,
        verbose_name='Plein complet'
    )

    # Documentation
    receipt_photo = models.ImageField(
        upload_to='fuel/receipts/',
        null=True,
        blank=True,
        verbose_name='Photo du reçu'
    )
    receipt_number = models.CharField(
        max_length=50,
        blank=True,
        verbose_name='Numéro de reçu'
    )

    # Metadata
    notes = models.TextField(blank=True, verbose_name='Notes')
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Date de création'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Date de mise à jour'
    )

    class Meta:
        db_table = 'fuel_records'
        verbose_name = 'Ravitaillement'
        verbose_name_plural = 'Ravitaillements'
        ordering = ['-refuel_date']
        indexes = [
            models.Index(fields=['vehicle', 'refuel_date']),
            models.Index(fields=['driver', 'refuel_date']),
        ]

    def __str__(self):
        return f"{self.vehicle.license_plate} - {self.refuel_date.strftime('%Y-%m-%d')}"

    def save(self, *args, **kwargs):
        # Calculer la consommation si plein complet
        if self.is_full_tank and self.distance_since_last_refuel and self.quantity:
            if self.distance_since_last_refuel > 0:
                self.calculated_consumption = (self.quantity / self.distance_since_last_refuel) * 100
        super().save(*args, **kwargs)
