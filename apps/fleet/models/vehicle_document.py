from django.db import models


class VehicleDocument(models.Model):
    """Document associé à un véhicule (carte grise, assurance, etc.)"""

    DOCUMENT_TYPE_CHOICES = [
        ('carte_grise', 'Carte grise'),
        ('assurance', 'Assurance'),
        ('visite_technique', 'Visite technique'),
        ('vignette', 'Vignette'),
    ]

    vehicle = models.ForeignKey(
        'fleet.Vehicle',
        on_delete=models.CASCADE,
        related_name='documents',
        verbose_name='Véhicule'
    )
    document_type = models.CharField(
        max_length=30,
        choices=DOCUMENT_TYPE_CHOICES,
        verbose_name='Type de document'
    )
    document_number = models.CharField(
        max_length=100,
        verbose_name='Numéro du document'
    )
    issue_date = models.DateField(verbose_name='Date d\'émission')
    expiry_date = models.DateField(verbose_name='Date d\'expiration')
    file = models.FileField(
        upload_to='vehicle_documents/',
        null=True,
        blank=True,
        verbose_name='Fichier'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'vehicle_documents'
        verbose_name = 'Document véhicule'
        verbose_name_plural = 'Documents véhicules'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.vehicle.license_plate}"

    @property
    def file_name(self):
        if self.file:
            return self.file.name.split('/')[-1]
        return None

    @property
    def status(self):
        from django.utils import timezone
        today = timezone.now().date()
        diff = (self.expiry_date - today).days
        if diff < 0:
            return 'expired'
        if diff <= 30:
            return 'expiring_soon'
        return 'valid'

    @property
    def days_until_expiry(self):
        from django.utils import timezone
        today = timezone.now().date()
        return (self.expiry_date - today).days
