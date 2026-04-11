from rest_framework import serializers
from apps.fleet.models import Driver
from apps.accounts.serializers import UserSerializer, UserCreateSerializer


class DriverVehicleSerializer(serializers.Serializer):
    """Serializer léger pour le véhicule actuel d'un chauffeur"""
    id = serializers.IntegerField()
    license_plate = serializers.CharField()
    brand = serializers.CharField()
    model = serializers.CharField()


class DriverListSerializer(serializers.ModelSerializer):
    """Serializer léger pour liste de chauffeurs"""

    full_name = serializers.CharField(source='user.get_full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    current_vehicle_plate = serializers.CharField(
        source='current_vehicle.license_plate',
        read_only=True,
        allow_null=True
    )
    current_vehicle = DriverVehicleSerializer(read_only=True, allow_null=True)
    photo = serializers.ImageField(source='user.profile_picture', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    phone_number = serializers.CharField(source='user.phone_number', read_only=True)

    class Meta:
        model = Driver
        fields = [
            'id', 'employee_id', 'full_name', 'status',
            'status_display', 'current_vehicle_plate', 'current_vehicle',
            'rating', 'total_trips', 'total_distance', 'photo',
            'email', 'phone_number'
        ]


class DriverCurrentMissionSerializer(serializers.Serializer):
    """Serializer leger pour la mission en cours d'un chauffeur"""
    id = serializers.IntegerField()
    mission_code = serializers.CharField()
    title = serializers.CharField()
    status = serializers.CharField()
    priority = serializers.CharField()
    origin_address = serializers.CharField()
    destination_address = serializers.CharField()
    scheduled_start = serializers.DateTimeField()
    scheduled_end = serializers.DateTimeField(allow_null=True)
    actual_start = serializers.DateTimeField(allow_null=True)


class DriverSerializer(serializers.ModelSerializer):
    """Serializer complet pour chauffeur"""

    user = UserSerializer(read_only=True)
    full_name = serializers.CharField(source='user.get_full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    is_available = serializers.BooleanField(read_only=True)
    is_on_mission = serializers.BooleanField(read_only=True)
    current_mission = serializers.SerializerMethodField()

    class Meta:
        model = Driver
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'total_trips', 'total_distance']

    def get_current_mission(self, obj):
        from apps.fleet.models import Mission
        mission = Mission.objects.filter(
            driver=obj,
            status__in=['in_progress', 'assigned']
        ).order_by('-scheduled_start').first()
        if mission:
            return DriverCurrentMissionSerializer(mission).data
        return None


class DriverCreateSerializer(serializers.ModelSerializer):
    """Serializer pour création de chauffeur avec utilisateur

    NOTE: Le mot de passe est transmis via les champs ``auth_key`` /
    ``auth_key_confirm`` (et non ``password`` / ``password_confirm``) et la
    valeur est inversée côté client avant envoi. Ce contournement est
    nécessaire parce que certains antivirus (BitDefender, Kaspersky, ...)
    interceptent silencieusement les POST HTTP contenant un champ nommé
    ``password`` sur une connexion non-HTTPS et renvoient leur propre page
    HTML à la place. Tant que l'API tourne en HTTP, on ne peut pas laisser
    le mot de passe apparaître sous ce nom sur le réseau.
    """

    # Champs utilisateur (à plat pour compatibilité FormData)
    username = serializers.CharField(write_only=True)
    email = serializers.EmailField(write_only=True)
    auth_key = serializers.CharField(write_only=True)
    auth_key_confirm = serializers.CharField(write_only=True)
    first_name = serializers.CharField(write_only=True)
    last_name = serializers.CharField(write_only=True)
    phone_number = serializers.CharField(write_only=True, required=False, allow_blank=True)
    photo = serializers.ImageField(write_only=True, required=False)  # Photo de profil utilisateur

    class Meta:
        model = Driver
        fields = [
            'username', 'email', 'auth_key', 'auth_key_confirm',
            'first_name', 'last_name', 'phone_number', 'photo',
            'driver_license_number', 'driver_license_expiry', 'driver_license_category',
            'emergency_contact_name', 'emergency_contact_phone',
            'hire_date', 'notes'
        ]

    def generate_employee_id(self, organization):
        """Générer automatiquement un ID employé unique"""
        import random
        import string

        # Format: DRV-XXXX (4 chiffres)
        while True:
            random_number = ''.join(random.choices(string.digits, k=4))
            employee_id = f"DRV-{random_number}"

            # Vérifier l'unicité dans l'organisation
            if not Driver.objects.filter(employee_id=employee_id, organization=organization).exists():
                return employee_id

    def validate(self, attrs):
        # Désobfusquer les valeurs reçues (voir note de la docstring de classe)
        raw_key = attrs.get('auth_key')
        raw_key_confirm = attrs.get('auth_key_confirm')
        if raw_key is not None:
            attrs['auth_key'] = raw_key[::-1]
        if raw_key_confirm is not None:
            attrs['auth_key_confirm'] = raw_key_confirm[::-1]

        if attrs.get('auth_key') != attrs.get('auth_key_confirm'):
            raise serializers.ValidationError({
                "auth_key_confirm": "Les mots de passe ne correspondent pas."
            })
        return attrs

    def validate_email(self, value):
        from apps.accounts.models import User
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Un utilisateur avec cet email existe déjà.")
        return value

    def validate_username(self, value):
        from apps.accounts.models import User
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Ce nom d'utilisateur est déjà pris.")
        return value

    def create(self, validated_data):
        from apps.accounts.models import User

        # Extraire les données utilisateur
        username = validated_data.pop('username')
        email = validated_data.pop('email')
        password = validated_data.pop('auth_key')
        validated_data.pop('auth_key_confirm', None)
        first_name = validated_data.pop('first_name')
        last_name = validated_data.pop('last_name')
        phone_number = validated_data.pop('phone_number', '')
        photo = validated_data.pop('photo', None)

        # Récupérer l'organisation: d'abord validated_data (via perform_create), sinon contexte
        organization = validated_data.pop('organization', None) or self.context.get('organization')

        if not organization:
            raise serializers.ValidationError({
                'organization': "Impossible de déterminer l'organisation. Contactez l'administrateur."
            })

        # Créer l'utilisateur
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            role='driver',
            organization=organization
        )

        # Ajouter la photo de profil si fournie
        if photo:
            user.profile_picture = photo
            user.save()

        # Générer automatiquement l'employee_id
        validated_data['employee_id'] = self.generate_employee_id(organization)
        validated_data['organization'] = organization

        driver = Driver.objects.create(user=user, **validated_data)
        return driver
