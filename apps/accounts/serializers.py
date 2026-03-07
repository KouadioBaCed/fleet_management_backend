from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.text import slugify

from .models import Organization, UserPreferences, EmailVerificationToken

User = get_user_model()


class OrganizationSerializer(serializers.ModelSerializer):
    """Serializer pour le modèle Organization"""
    vehicle_count = serializers.ReadOnlyField()
    driver_count = serializers.ReadOnlyField()
    active_mission_count = serializers.ReadOnlyField()

    class Meta:
        model = Organization
        fields = [
            'id', 'name', 'slug', 'logo', 'address', 'city', 'country',
            'phone', 'email', 'website', 'is_active', 'subscription_type',
            'max_vehicles', 'max_drivers', 'vehicle_count', 'driver_count',
            'active_mission_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'slug', 'created_at', 'updated_at']


class OrganizationCreateSerializer(serializers.ModelSerializer):
    """Serializer pour la création d'une organisation"""

    class Meta:
        model = Organization
        fields = ['name', 'address', 'city', 'country', 'phone', 'email', 'website']

    def create(self, validated_data):
        # Générer un slug unique
        base_slug = slugify(validated_data['name'])
        slug = base_slug
        counter = 1
        while Organization.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        validated_data['slug'] = slug
        return super().create(validated_data)


class OrganizationMinimalSerializer(serializers.ModelSerializer):
    """Serializer minimal pour l'organisation (utilisé dans les réponses)"""

    class Meta:
        model = Organization
        fields = ['id', 'name', 'slug', 'logo']


class UserSerializer(serializers.ModelSerializer):
    """Serializer pour le modèle User"""
    organization = OrganizationMinimalSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'phone_number', 'profile_picture', 'is_active_duty',
            'is_active', 'organization', 'date_joined', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'date_joined', 'created_at', 'updated_at']


class UserCreateSerializer(serializers.ModelSerializer):
    """Serializer pour la création d'utilisateur"""

    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password]
    )
    password_confirm = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'password', 'password_confirm',
            'first_name', 'last_name', 'role', 'phone_number'
        ]

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({
                "password": "Les mots de passe ne correspondent pas."
            })
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        user = User.objects.create_user(**validated_data)
        return user


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer pour changer le mot de passe"""

    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(
        required=True,
        validators=[validate_password]
    )
    new_password_confirm = serializers.CharField(required=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({
                "new_password": "Les nouveaux mots de passe ne correspondent pas."
            })
        return attrs


class DriverLicenseSerializer(serializers.Serializer):
    """Serializer pour les informations du permis de conduire"""
    driver_license_number = serializers.CharField()
    driver_license_expiry = serializers.DateField()
    driver_license_category = serializers.CharField()
    employee_id = serializers.CharField()
    status = serializers.CharField()
    status_display = serializers.CharField()


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer pour le profil utilisateur"""

    full_name = serializers.SerializerMethodField()
    organization = OrganizationMinimalSerializer(read_only=True)
    driver_license = serializers.SerializerMethodField()
    assigned_vehicle = serializers.SerializerMethodField()
    active_missions = serializers.SerializerMethodField()
    statistics = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'full_name', 'role', 'phone_number', 'profile_picture',
            'is_active_duty', 'organization', 'driver_license', 'assigned_vehicle',
            'active_missions', 'statistics'
        ]
        read_only_fields = [
            'id', 'username', 'role', 'organization', 'driver_license',
            'assigned_vehicle', 'active_missions', 'statistics', 'full_name',
            'is_active_duty'
        ]

    def to_representation(self, instance):
        """Convertit l'URL de la photo de profil en URL absolue"""
        data = super().to_representation(instance)
        if instance.profile_picture:
            request = self.context.get('request')
            if request:
                data['profile_picture'] = request.build_absolute_uri(instance.profile_picture.url)
            else:
                data['profile_picture'] = instance.profile_picture.url
        else:
            data['profile_picture'] = None
        return data

    def validate_profile_picture(self, value):
        """Valide le fichier image pour la photo de profil"""
        if value:
            # Verifier la taille du fichier (max 5MB)
            max_size = 5 * 1024 * 1024  # 5MB
            if value.size > max_size:
                raise serializers.ValidationError(
                    "La taille de l'image ne doit pas depasser 5MB."
                )

            # Verifier le type de fichier
            allowed_types = ['image/jpeg', 'image/png', 'image/jpg', 'image/webp']
            if value.content_type not in allowed_types:
                raise serializers.ValidationError(
                    "Format d'image non supporte. Utilisez JPEG, PNG ou WebP."
                )
        return value

    def get_full_name(self, obj):
        return obj.get_full_name()

    def get_driver_license(self, obj):
        """Retourne les informations du permis si l'utilisateur est un chauffeur"""
        if obj.role != 'driver':
            return None

        try:
            driver = obj.driver_profile
            return {
                'driver_license_number': driver.driver_license_number,
                'driver_license_expiry': driver.driver_license_expiry,
                'driver_license_category': driver.driver_license_category,
                'employee_id': driver.employee_id,
                'status': driver.status,
                'status_display': driver.get_status_display(),
            }
        except Exception:
            return None

    def get_assigned_vehicle(self, obj):
        """Retourne les informations du vehicule assigne si l'utilisateur est un chauffeur"""
        if obj.role != 'driver':
            return None

        try:
            driver = obj.driver_profile
            vehicle = driver.current_vehicle

            if not vehicle:
                return None

            return {
                'id': vehicle.id,
                'license_plate': vehicle.license_plate,
                'brand': vehicle.brand,
                'model': vehicle.model,
                'year': vehicle.year,
                'vehicle_type': vehicle.vehicle_type,
                'vehicle_type_display': vehicle.get_vehicle_type_display(),
                'color': vehicle.color,
                'fuel_type': vehicle.fuel_type,
                'fuel_type_display': vehicle.get_fuel_type_display(),
                'status': vehicle.status,
                'status_display': vehicle.get_status_display(),
                'current_mileage': float(vehicle.current_mileage),
                'photo': vehicle.photo.url if vehicle.photo else None,
            }
        except Exception:
            return None

    def get_active_missions(self, obj):
        """Retourne les missions actives du chauffeur"""
        if obj.role != 'driver':
            return []

        try:
            from apps.fleet.models import Mission
            driver = obj.driver_profile

            # Missions en cours ou assignees
            missions = Mission.objects.filter(
                driver=driver,
                status__in=['assigned', 'in_progress']
            ).order_by('scheduled_start')[:5]

            return [
                {
                    'id': mission.id,
                    'mission_code': mission.mission_code,
                    'title': mission.title,
                    'status': mission.status,
                    'status_display': mission.get_status_display(),
                    'priority': mission.priority,
                    'priority_display': mission.get_priority_display(),
                    'origin_address': mission.origin_address,
                    'destination_address': mission.destination_address,
                    'scheduled_start': mission.scheduled_start.isoformat() if mission.scheduled_start else None,
                    'scheduled_end': mission.scheduled_end.isoformat() if mission.scheduled_end else None,
                    'estimated_distance': float(mission.estimated_distance),
                }
                for mission in missions
            ]
        except Exception:
            return []

    def get_statistics(self, obj):
        """Retourne les statistiques personnelles du chauffeur"""
        if obj.role != 'driver':
            return None

        try:
            from apps.fleet.models import Mission, Trip
            from django.db.models import Sum, Avg, Count
            from django.utils import timezone
            from datetime import timedelta

            driver = obj.driver_profile

            # Statistiques de base du chauffeur
            total_trips = driver.total_trips
            total_distance = float(driver.total_distance)
            rating = float(driver.rating)

            # Statistiques des missions
            missions_stats = Mission.objects.filter(driver=driver).aggregate(
                total_missions=Count('id'),
                completed_missions=Count('id', filter=models.Q(status='completed')),
                cancelled_missions=Count('id', filter=models.Q(status='cancelled')),
            )

            # Missions ce mois-ci
            start_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            missions_this_month = Mission.objects.filter(
                driver=driver,
                status='completed',
                actual_end__gte=start_of_month
            ).count()

            # Statistiques des trajets
            trips_stats = Trip.objects.filter(driver=driver).aggregate(
                total_fuel_consumed=Sum('fuel_consumed'),
                avg_speed=Avg('average_speed'),
                max_speed_ever=models.Max('max_speed'),
                trips_with_incidents=Count('id', filter=models.Q(has_incidents=True)),
            )

            # Distance ce mois-ci
            distance_this_month = Trip.objects.filter(
                driver=driver,
                status='completed',
                end_time__gte=start_of_month
            ).aggregate(total=Sum('total_distance'))['total'] or 0

            return {
                'total_trips': total_trips,
                'total_distance': total_distance,
                'rating': rating,
                'total_missions': missions_stats['total_missions'] or 0,
                'completed_missions': missions_stats['completed_missions'] or 0,
                'cancelled_missions': missions_stats['cancelled_missions'] or 0,
                'missions_this_month': missions_this_month,
                'distance_this_month': float(distance_this_month),
                'total_fuel_consumed': float(trips_stats['total_fuel_consumed'] or 0),
                'average_speed': float(trips_stats['avg_speed'] or 0),
                'max_speed_ever': float(trips_stats['max_speed_ever'] or 0),
                'trips_with_incidents': trips_stats['trips_with_incidents'] or 0,
                'success_rate': round(
                    (missions_stats['completed_missions'] / missions_stats['total_missions'] * 100)
                    if missions_stats['total_missions'] > 0 else 100, 1
                ),
            }
        except Exception:
            return None


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Serializer personnalisé pour l'obtention du token JWT
    Retourne les informations de l'utilisateur avec le token
    """

    def validate(self, attrs):
        data = super().validate(attrs)

        # Vérifier si l'utilisateur a une organisation
        if not self.user.organization:
            raise serializers.ValidationError({
                "detail": "Aucune organisation associée à ce compte."
            })

        # Vérifier si l'organisation est active
        if not self.user.organization.is_active:
            raise serializers.ValidationError({
                "detail": "Votre organisation a été désactivée. Contactez l'administrateur."
            })

        # Ajouter les informations utilisateur à la réponse
        data['user'] = {
            'id': self.user.id,
            'username': self.user.username,
            'email': self.user.email,
            'first_name': self.user.first_name,
            'last_name': self.user.last_name,
            'full_name': self.user.get_full_name(),
            'role': self.user.role,
            'phone_number': self.user.phone_number,
            'profile_picture': self.user.profile_picture.url if self.user.profile_picture else None,
            'is_active_duty': self.user.is_active_duty,
        }

        # Ajouter les informations de l'organisation
        data['organization'] = {
            'id': str(self.user.organization.id),
            'name': self.user.organization.name,
            'slug': self.user.organization.slug,
            'logo': self.user.organization.logo.url if self.user.organization.logo else None,
        }

        return data


class RegisterOrganizationSerializer(serializers.Serializer):
    """
    Serializer pour l'inscription d'une nouvelle organisation avec son admin
    """
    # Informations organisation
    organization_name = serializers.CharField(max_length=255)
    organization_email = serializers.EmailField()
    organization_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    organization_address = serializers.CharField(required=False, allow_blank=True)
    organization_city = serializers.CharField(max_length=100, required=False, allow_blank=True)

    # Informations admin
    admin_email = serializers.EmailField()
    admin_username = serializers.CharField(max_length=150)
    admin_first_name = serializers.CharField(max_length=150)
    admin_last_name = serializers.CharField(max_length=150)
    admin_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    def validate_admin_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Un utilisateur avec cet email existe déjà.")
        return value

    def validate_admin_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Ce nom d'utilisateur est déjà pris.")
        return value

    def validate_organization_name(self, value):
        if Organization.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError("Une organisation avec ce nom existe déjà.")
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({
                "password": "Les mots de passe ne correspondent pas."
            })
        return attrs

    def create(self, validated_data):
        # Créer l'organisation
        base_slug = slugify(validated_data['organization_name'])
        slug = base_slug
        counter = 1
        while Organization.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        organization = Organization.objects.create(
            name=validated_data['organization_name'],
            slug=slug,
            email=validated_data['organization_email'],
            phone=validated_data.get('organization_phone', ''),
            address=validated_data.get('organization_address', ''),
            city=validated_data.get('organization_city', ''),
            subscription_type='trial',
        )

        # Créer l'utilisateur admin
        user = User.objects.create_user(
            username=validated_data['admin_username'],
            email=validated_data['admin_email'],
            password=validated_data['password'],
            first_name=validated_data['admin_first_name'],
            last_name=validated_data['admin_last_name'],
            phone_number=validated_data.get('admin_phone', ''),
            role='admin',
            organization=organization,
        )

        return {
            'organization': organization,
            'user': user,
        }


class UserPreferencesSerializer(serializers.ModelSerializer):
    """Serializer pour les préférences utilisateur"""

    class Meta:
        model = UserPreferences
        fields = [
            'distance_unit', 'fuel_unit', 'currency',
            'language', 'timezone', 'date_format',
            'email_notifications', 'sms_notifications', 'push_notifications',
            'maintenance_alerts', 'incident_alerts', 'fuel_alerts',
            'report_reminders', 'daily_summary', 'weekly_summary',
            'theme', 'primary_color', 'secondary_color',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate_primary_color(self, value):
        """Valide le format de la couleur hexadécimale"""
        import re
        if not re.match(r'^#[0-9A-Fa-f]{6}$', value):
            raise serializers.ValidationError("La couleur doit être au format hexadécimal (#RRGGBB)")
        return value

    def validate_secondary_color(self, value):
        """Valide le format de la couleur hexadécimale"""
        import re
        if not re.match(r'^#[0-9A-Fa-f]{6}$', value):
            raise serializers.ValidationError("La couleur doit être au format hexadécimal (#RRGGBB)")
        return value


# ============================================
# Serializers pour la gestion des utilisateurs (Admin)
# ============================================

class UserListSerializer(serializers.ModelSerializer):
    """Serializer pour la liste des utilisateurs (lecture seule)"""
    full_name = serializers.SerializerMethodField()
    role_display = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'role', 'role_display', 'phone_number', 'profile_picture',
            'is_active', 'is_active_duty', 'date_joined', 'last_login'
        ]
        read_only_fields = fields

    def get_full_name(self, obj):
        return obj.get_full_name()

    def get_role_display(self, obj):
        role_labels = {
            'admin': 'Administrateur',
            'supervisor': 'Superviseur',
            'driver': 'Chauffeur'
        }
        return role_labels.get(obj.role, obj.role)


class AdminUserCreateSerializer(serializers.ModelSerializer):
    """
    Serializer pour la création d'utilisateurs par un admin.
    Permet de créer des comptes admin, superviseur ou driver.
    """
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={'input_type': 'password'}
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )
    role = serializers.ChoiceField(
        choices=[('admin', 'Administrateur'), ('supervisor', 'Superviseur'), ('driver', 'Chauffeur')],
        required=True
    )

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'password', 'password_confirm',
            'first_name', 'last_name', 'role', 'phone_number', 'is_active'
        ]
        read_only_fields = ['id']

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Un utilisateur avec cet email existe déjà.")
        return value

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Ce nom d'utilisateur est déjà pris.")
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({
                "password_confirm": "Les mots de passe ne correspondent pas."
            })
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        # L'organisation sera ajoutée dans la vue
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer pour la mise à jour d'utilisateurs par un admin.
    Permet de modifier le rôle, activer/désactiver un compte.
    """
    role = serializers.ChoiceField(
        choices=[('admin', 'Administrateur'), ('supervisor', 'Superviseur'), ('driver', 'Chauffeur')],
        required=False
    )
    new_password = serializers.CharField(
        write_only=True,
        required=False,
        validators=[validate_password],
        style={'input_type': 'password'},
        allow_blank=True
    )

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'phone_number', 'is_active', 'is_active_duty', 'new_password'
        ]
        read_only_fields = ['id']

    def validate_email(self, value):
        user = self.instance
        if User.objects.filter(email=value).exclude(id=user.id).exists():
            raise serializers.ValidationError("Un utilisateur avec cet email existe déjà.")
        return value

    def validate_username(self, value):
        user = self.instance
        if User.objects.filter(username=value).exclude(id=user.id).exists():
            raise serializers.ValidationError("Ce nom d'utilisateur est déjà pris.")
        return value

    def update(self, instance, validated_data):
        new_password = validated_data.pop('new_password', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if new_password:
            instance.set_password(new_password)

        instance.save()
        return instance


class UserRoleUpdateSerializer(serializers.Serializer):
    """Serializer pour changer uniquement le rôle d'un utilisateur"""
    role = serializers.ChoiceField(
        choices=[('admin', 'Administrateur'), ('supervisor', 'Superviseur'), ('driver', 'Chauffeur')],
        required=True
    )

    def update(self, instance, validated_data):
        instance.role = validated_data['role']
        instance.save()
        return instance


class UserStatusUpdateSerializer(serializers.Serializer):
    """Serializer pour activer/désactiver un compte utilisateur"""
    is_active = serializers.BooleanField(required=True)

    def update(self, instance, validated_data):
        instance.is_active = validated_data['is_active']
        instance.save()
        return instance


# ============================================
# Serializers pour l'inscription par email
# ============================================

class SignupInitiateSerializer(serializers.Serializer):
    """
    Serializer pour initier l'inscription - envoie un email de vérification
    """
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    organization_name = serializers.CharField(max_length=255)

    def validate_email(self, value):
        # Vérifier si l'email existe déjà
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Un compte avec cet email existe déjà.")
        return value.lower()

    def validate_organization_name(self, value):
        # Vérifier si l'organisation existe déjà
        if Organization.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError("Une organisation avec ce nom existe déjà.")
        return value


class SignupCompleteSerializer(serializers.Serializer):
    """
    Serializer pour compléter l'inscription après vérification email
    """
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    username = serializers.CharField(max_length=150)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)

    def validate_token(self, value):
        try:
            token_obj = EmailVerificationToken.objects.get(token=value)
        except EmailVerificationToken.DoesNotExist:
            raise serializers.ValidationError("Token invalide.")

        if not token_obj.is_valid:
            if token_obj.is_used:
                raise serializers.ValidationError("Ce lien a déjà été utilisé.")
            if token_obj.is_expired:
                raise serializers.ValidationError("Ce lien a expiré. Veuillez recommencer l'inscription.")

        self.token_obj = token_obj
        return value

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Ce nom d'utilisateur est déjà pris.")
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({
                "password_confirm": "Les mots de passe ne correspondent pas."
            })
        return attrs

    def create(self, validated_data):
        token_obj = self.token_obj

        # Créer l'organisation
        base_slug = slugify(token_obj.organization_name)
        slug = base_slug
        counter = 1
        while Organization.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        organization = Organization.objects.create(
            name=token_obj.organization_name,
            slug=slug,
            email=token_obj.email,
            subscription_type='trial',
        )

        # Créer l'utilisateur admin
        user = User.objects.create_user(
            username=validated_data['username'],
            email=token_obj.email,
            password=validated_data['password'],
            first_name=token_obj.first_name,
            last_name=token_obj.last_name,
            phone_number=validated_data.get('phone_number', ''),
            role='admin',
            organization=organization,
        )

        # Marquer le token comme utilisé
        token_obj.is_used = True
        token_obj.save()

        return {
            'organization': organization,
            'user': user,
        }


class VerifyTokenSerializer(serializers.Serializer):
    """Serializer pour vérifier si un token est valide"""
    token = serializers.CharField()

    def validate_token(self, value):
        try:
            token_obj = EmailVerificationToken.objects.get(token=value)
        except EmailVerificationToken.DoesNotExist:
            raise serializers.ValidationError("Token invalide.")

        if not token_obj.is_valid:
            if token_obj.is_used:
                raise serializers.ValidationError("Ce lien a déjà été utilisé.")
            if token_obj.is_expired:
                raise serializers.ValidationError("Ce lien a expiré.")

        self.token_obj = token_obj
        return value
