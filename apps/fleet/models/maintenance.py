from django.db import models
from django.conf import settings


class MaintenanceRecord(models.Model):
    """Modèle représentant un enregistrement de maintenance"""

    organization = models.ForeignKey(
        'accounts.Organization',
        on_delete=models.CASCADE,
        related_name='maintenance_records',
        verbose_name='Organisation',
        null=True,
        blank=True
    )

    TYPE_CHOICES = [
        ('oil_change', 'Vidange'),
        ('tire_change', 'Changement pneus'),
        ('brake_service', 'Freins'),
        ('inspection', 'Contrôle technique'),
        ('repair', 'Réparation'),
        ('preventive', 'Maintenance préventive'),
        ('other', 'Autre'),
    ]

    STATUS_CHOICES = [
        ('scheduled', 'Programmé'),
        ('in_progress', 'En cours'),
        ('completed', 'Terminé'),
        ('cancelled', 'Annulé'),
    ]

    # Relations
    vehicle = models.ForeignKey(
        'fleet.Vehicle',
        on_delete=models.CASCADE,
        related_name='maintenance_records',
        verbose_name='Véhicule'
    )

    # Type et statut
    maintenance_type = models.CharField(
        max_length=30,
        choices=TYPE_CHOICES,
        verbose_name='Type de maintenance'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='scheduled',
        verbose_name='Statut'
    )

    # Planning
    scheduled_date = models.DateField(verbose_name='Date programmée')
    completed_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='Date de réalisation'
    )

    # Kilométrage
    mileage_at_service = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Kilométrage au service'
    )
    next_service_mileage = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Prochain service (km)'
    )

    # Détails
    description = models.TextField(verbose_name='Description')
    work_performed = models.TextField(
        blank=True,
        verbose_name='Travaux effectués'
    )
    parts_replaced = models.TextField(
        blank=True,
        verbose_name='Pièces remplacées'
    )

    # Prestataire
    service_provider = models.CharField(
        max_length=100,
        verbose_name='Prestataire'
    )
    technician_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Nom du technicien'
    )

    # Coûts
    labor_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Coût main d\'œuvre'
    )
    parts_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Coût pièces'
    )
    total_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Coût total'
    )

    # Documents
    invoice = models.FileField(
        upload_to='maintenance/invoices/',
        null=True,
        blank=True,
        verbose_name='Facture'
    )
    receipt = models.FileField(
        upload_to='maintenance/receipts/',
        null=True,
        blank=True,
        verbose_name='Reçu'
    )

    # Metadata
    notes = models.TextField(blank=True, verbose_name='Notes')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_maintenance_records',
        verbose_name='Créé par'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Date de création'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Date de mise à jour'
    )

    class Meta:
        db_table = 'maintenance_records'
        verbose_name = 'Maintenance'
        verbose_name_plural = 'Maintenances'
        ordering = ['-scheduled_date']
        indexes = [
            models.Index(fields=['vehicle', 'scheduled_date']),
            models.Index(fields=['status', 'scheduled_date']),
        ]

    def __str__(self):
        return f"{self.vehicle.license_plate} - {self.get_maintenance_type_display()}"
