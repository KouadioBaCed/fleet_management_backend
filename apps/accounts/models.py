from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid


class Organization(models.Model):
    """Modèle représentant une organisation/entreprise utilisant le système"""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    name = models.CharField(
        max_length=255,
        verbose_name='Nom de l\'organisation'
    )
    slug = models.SlugField(
        max_length=100,
        unique=True, 
        verbose_name='Identifiant unique'
    )
    logo = models.ImageField(
        upload_to='organizations/logos/',
        null=True,
        blank=True,
        verbose_name='Logo'
    )
    address = models.TextField(
        blank=True,
        verbose_name='Adresse'
    )
    city = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Ville'
    )
    country = models.CharField(
        max_length=100,
        default='France',
        verbose_name='Pays'
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name='Téléphone'
    )
    email = models.EmailField(
        blank=True,
        verbose_name='Email de contact'
    )
    website = models.URLField(
        blank=True,
        verbose_name='Site web'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Active'
    )
    subscription_type = models.CharField(
        max_length=50,
        choices=[
            ('trial', 'Essai'),
            ('basic', 'Basique'),
            ('professional', 'Professionnel'),
            ('enterprise', 'Entreprise'),
        ],
        default='trial',
        verbose_name='Type d\'abonnement'
    )
    max_vehicles = models.PositiveIntegerField(
        default=10,
        verbose_name='Nombre max de véhicules'
    )
    max_drivers = models.PositiveIntegerField(
        default=10,
        verbose_name='Nombre max de conducteurs'
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
        db_table = 'organizations'
        verbose_name = 'Organisation'
        verbose_name_plural = 'Organisations'
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def vehicle_count(self):
        return self.vehicles.count()

    @property
    def driver_count(self):
        return self.drivers.count()

    @property
    def active_mission_count(self):
        return self.missions.filter(status='in_progress').count()


class User(AbstractUser):
    """Modèle utilisateur personnalisé pour le système de gestion de flotte"""

    ROLE_CHOICES = [
        ('admin', 'Administrateur'),
        ('supervisor', 'Superviseur'),
        ('driver', 'Chauffeur'),
    ]

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='users',
        verbose_name='Organisation',
        null=True,
        blank=True
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='driver',
        verbose_name='Rôle'
    )
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        verbose_name='Numéro de téléphone'
    )
    profile_picture = models.ImageField(
        upload_to='profiles/',
        null=True,
        blank=True,
        verbose_name='Photo de profil'
    )
    is_active_duty = models.BooleanField(
        default=True,
        verbose_name='En service'
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
        db_table = 'users'
        verbose_name = 'Utilisateur'
        verbose_name_plural = 'Utilisateurs'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_supervisor(self):
        return self.role == 'supervisor'

    @property
    def is_driver(self):
        return self.role == 'driver'


class UserPreferences(models.Model):
    """Préférences utilisateur pour la personnalisation de l'application"""

    UNIT_CHOICES = [
        ('km', 'Kilomètres'),
        ('miles', 'Miles'),
    ]

    LANGUAGE_CHOICES = [
        ('fr', 'Français'),
        ('en', 'English'),
    ]

    TIMEZONE_CHOICES = [
        ('Africa/Kinshasa', 'Kinshasa (WAT)'),
        ('Africa/Lubumbashi', 'Lubumbashi (CAT)'),
        ('Europe/Paris', 'Paris (CET)'),
        ('UTC', 'UTC'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='preferences',
        verbose_name='Utilisateur'
    )

    CURRENCY_CHOICES = [
        ('XOF', 'Franc CFA (FCFA)'),
    ]

    # Unités
    distance_unit = models.CharField(
        max_length=10,
        choices=UNIT_CHOICES,
        default='km',
        verbose_name='Unité de distance'
    )
    fuel_unit = models.CharField(
        max_length=10,
        choices=[('liters', 'Litres'), ('gallons', 'Gallons')],
        default='liters',
        verbose_name='Unité de carburant'
    )
    currency = models.CharField(
        max_length=10,
        choices=CURRENCY_CHOICES,
        default='XOF',
        verbose_name='Devise'
    )

    # Langue et région
    language = models.CharField(
        max_length=10,
        choices=LANGUAGE_CHOICES,
        default='fr',
        verbose_name='Langue'
    )
    timezone = models.CharField(
        max_length=50,
        choices=TIMEZONE_CHOICES,
        default='Africa/Kinshasa',
        verbose_name='Fuseau horaire'
    )
    date_format = models.CharField(
        max_length=20,
        choices=[
            ('DD/MM/YYYY', 'DD/MM/YYYY'),
            ('MM/DD/YYYY', 'MM/DD/YYYY'),
            ('YYYY-MM-DD', 'YYYY-MM-DD'),
        ],
        default='DD/MM/YYYY',
        verbose_name='Format de date'
    )

    # Notifications
    email_notifications = models.BooleanField(
        default=True,
        verbose_name='Notifications par email'
    )
    sms_notifications = models.BooleanField(
        default=False,
        verbose_name='Notifications par SMS'
    )
    push_notifications = models.BooleanField(
        default=True,
        verbose_name='Notifications push'
    )
    maintenance_alerts = models.BooleanField(
        default=True,
        verbose_name='Alertes de maintenance'
    )
    incident_alerts = models.BooleanField(
        default=True,
        verbose_name='Alertes d\'incidents'
    )
    fuel_alerts = models.BooleanField(
        default=True,
        verbose_name='Alertes carburant'
    )
    report_reminders = models.BooleanField(
        default=True,
        verbose_name='Rappels de rapports'
    )
    daily_summary = models.BooleanField(
        default=False,
        verbose_name='Résumé quotidien'
    )
    weekly_summary = models.BooleanField(
        default=True,
        verbose_name='Résumé hebdomadaire'
    )

    # Apparence
    theme = models.CharField(
        max_length=20,
        choices=[
            ('light', 'Clair'),
            ('dark', 'Sombre'),
            ('auto', 'Automatique'),
        ],
        default='light',
        verbose_name='Thème'
    )
    primary_color = models.CharField(
        max_length=7,
        default='#6A8A82',
        verbose_name='Couleur principale'
    )
    secondary_color = models.CharField(
        max_length=7,
        default='#B87333',
        verbose_name='Couleur secondaire'
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
        db_table = 'user_preferences'
        verbose_name = 'Préférences utilisateur'
        verbose_name_plural = 'Préférences utilisateurs'

    def __str__(self):
        return f"Préférences de {self.user.get_full_name()}"


class EmailVerificationToken(models.Model):
    """Token de vérification d'email pour l'inscription"""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    email = models.EmailField(
        verbose_name='Email'
    )
    token = models.CharField(
        max_length=64,
        unique=True,
        verbose_name='Token'
    )
    # Données d'inscription temporaires
    organization_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Nom de l\'organisation'
    )
    first_name = models.CharField(
        max_length=150,
        blank=True,
        verbose_name='Prénom'
    )
    last_name = models.CharField(
        max_length=150,
        blank=True,
        verbose_name='Nom'
    )
    is_used = models.BooleanField(
        default=False,
        verbose_name='Utilisé'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Date de création'
    )
    expires_at = models.DateTimeField(
        verbose_name='Date d\'expiration'
    )

    class Meta:
        db_table = 'email_verification_tokens'
        verbose_name = 'Token de vérification'
        verbose_name_plural = 'Tokens de vérification'
        ordering = ['-created_at']

    def __str__(self):
        return f"Token pour {self.email}"

    @property
    def is_expired(self):
        from django.utils import timezone
        return timezone.now() > self.expires_at

    @property
    def is_valid(self):
        return not self.is_used and not self.is_expired

    @classmethod
    def generate_token(cls):
        import secrets
        return secrets.token_urlsafe(48)
