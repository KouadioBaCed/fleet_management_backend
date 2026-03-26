from rest_framework import serializers
from apps.fleet.models import Mission, MissionCheckpoint
from .vehicle import VehicleListSerializer
from .driver import DriverListSerializer


class MissionCheckpointSerializer(serializers.ModelSerializer):
    """Serializer pour les points de passage"""

    class Meta:
        model = MissionCheckpoint
        fields = ['id', 'order', 'address', 'latitude', 'longitude', 'notes']


class MissionListSerializer(serializers.ModelSerializer):
    """Serializer léger pour liste de missions"""

    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    vehicle_plate = serializers.CharField(source='vehicle.license_plate', read_only=True)
    driver_name = serializers.CharField(source='driver.user.get_full_name', read_only=True)
    checkpoint_count = serializers.SerializerMethodField()

    class Meta:
        model = Mission
        fields = [
            'id', 'mission_code', 'title', 'status', 'status_display',
            'priority', 'priority_display', 'vehicle_plate', 'driver_name',
            'scheduled_start', 'scheduled_end', 'actual_start', 'actual_end',
            'origin_address', 'destination_address', 'estimated_distance',
            'checkpoint_count'
        ]

    def get_checkpoint_count(self, obj):
        return obj.checkpoints.count()


class ActiveTripSerializer(serializers.Serializer):
    """Serializer leger pour le trip actif inclus dans la mission"""
    id = serializers.IntegerField()
    status = serializers.CharField()
    start_time = serializers.DateTimeField()
    start_mileage = serializers.DecimalField(max_digits=10, decimal_places=2)
    start_fuel_level = serializers.DecimalField(max_digits=5, decimal_places=2)
    pause_duration_minutes = serializers.IntegerField()


class MissionSerializer(serializers.ModelSerializer):
    """Serializer complet pour mission"""

    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    vehicle = VehicleListSerializer(read_only=True)
    driver = DriverListSerializer(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    is_completed = serializers.BooleanField(read_only=True)
    duration = serializers.SerializerMethodField()
    active_trip = serializers.SerializerMethodField()
    checkpoints = MissionCheckpointSerializer(many=True, read_only=True)
    checkpoint_count = serializers.SerializerMethodField()

    class Meta:
        model = Mission
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'created_by']

    def get_duration(self, obj):
        duration = obj.duration
        if duration:
            total_seconds = int(duration.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours}h {minutes}min"
        return None

    def get_active_trip(self, obj):
        try:
            trip = obj.trip
            if trip and trip.status in ('active', 'paused'):
                return ActiveTripSerializer(trip).data
        except Exception:
            pass
        return None

    def get_checkpoint_count(self, obj):
        return obj.checkpoints.count()


class MissionCreateSerializer(serializers.ModelSerializer):
    """Serializer pour création de mission"""

    checkpoints = MissionCheckpointSerializer(many=True, required=False, default=[])

    class Meta:
        model = Mission
        fields = [
            'mission_code', 'title', 'description', 'vehicle', 'driver',
            'scheduled_start', 'scheduled_end', 'origin_address',
            'origin_latitude', 'origin_longitude', 'destination_address',
            'destination_latitude', 'destination_longitude',
            'estimated_distance', 'priority', 'responsible_person_name',
            'responsible_person_phone', 'notes', 'checkpoints'
        ]

    def validate(self, attrs):
        """Validations personnalisées"""
        vehicle = attrs.get('vehicle')
        driver = attrs.get('driver')
        request = self.context.get('request')
        user_org = request.user.organization if request and hasattr(request, 'user') else None

        # Vérifier que le véhicule appartient à la même organisation
        if vehicle and user_org and vehicle.organization != user_org:
            raise serializers.ValidationError({
                'vehicle': 'Ce véhicule n\'appartient pas à votre organisation.'
            })

        # Vérifier que le chauffeur appartient à la même organisation
        if driver and user_org and driver.organization != user_org:
            raise serializers.ValidationError({
                'driver': 'Ce chauffeur n\'appartient pas à votre organisation.'
            })

        # Vérifier que le véhicule est disponible
        # Accepter aussi 'in_use' si c'est le véhicule déjà assigné au chauffeur sélectionné
        if vehicle and vehicle.status != 'available':
            is_driver_vehicle = driver and hasattr(driver, 'current_vehicle') and driver.current_vehicle == vehicle
            if not is_driver_vehicle:
                raise serializers.ValidationError({
                    'vehicle': 'Le véhicule sélectionné n\'est pas disponible.'
                })

        # Vérifier que le chauffeur est disponible
        if driver and driver.status != 'available':
            raise serializers.ValidationError({
                'driver': 'Le chauffeur sélectionné n\'est pas disponible.'
            })

        # Vérifier que la date de fin est après la date de début
        if attrs['scheduled_end'] <= attrs['scheduled_start']:
            raise serializers.ValidationError({
                'scheduled_end': 'La date de fin doit être après la date de début.'
            })

        return attrs

    def create(self, validated_data):
        checkpoints_data = validated_data.pop('checkpoints', [])

        # Définir le créateur
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['created_by'] = request.user

        # Mettre à jour le statut du véhicule et du chauffeur
        vehicle = validated_data.get('vehicle')
        driver = validated_data.get('driver')

        # Si un chauffeur et un véhicule sont assignés, mettre le statut à 'assigned'
        if vehicle and driver:
            validated_data['status'] = 'assigned'

        mission = Mission.objects.create(**validated_data)

        # Créer les checkpoints
        for cp_data in checkpoints_data:
            MissionCheckpoint.objects.create(mission=mission, **cp_data)

        # Mettre à jour les statuts si véhicule et chauffeur sont assignés
        if vehicle and driver:
            vehicle.status = 'in_use'
            vehicle.save()

            driver.status = 'on_mission'
            driver.current_vehicle = vehicle
            driver.save()

        return mission
