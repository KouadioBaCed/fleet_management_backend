from rest_framework import serializers
from apps.fleet.models import Trip
from .mission import MissionListSerializer


class TripSerializer(serializers.ModelSerializer):
    """Serializer complet pour trajet"""

    status_display = serializers.CharField(source='get_status_display', read_only=True)
    mission = MissionListSerializer(read_only=True)
    vehicle_plate = serializers.CharField(source='vehicle.license_plate', read_only=True)
    driver_name = serializers.CharField(source='driver.user.get_full_name', read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    is_completed = serializers.BooleanField(read_only=True)
    duration = serializers.SerializerMethodField()

    class Meta:
        model = Trip
        fields = '__all__'
        read_only_fields = [
            'created_at', 'updated_at', 'total_duration_minutes',
            'total_distance', 'fuel_consumed', 'average_speed', 'max_speed'
        ]

    def get_duration(self, obj):
        duration = obj.duration
        if duration:
            total_seconds = int(duration.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours}h {minutes}min"
        return None


class TripCreateSerializer(serializers.ModelSerializer):
    """Serializer pour demarrer un trajet"""

    class Meta:
        model = Trip
        fields = [
            'id', 'mission', 'vehicle', 'driver', 'start_mileage', 'start_fuel_level', 'status'
        ]
        read_only_fields = ['id', 'status']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.fleet.models import Vehicle, Driver
        # Override vehicle and driver fields to make them optional (auto-completed from mission)
        self.fields['vehicle'] = serializers.PrimaryKeyRelatedField(
            queryset=Vehicle.objects.all(),
            required=False,
            allow_null=True
        )
        self.fields['driver'] = serializers.PrimaryKeyRelatedField(
            queryset=Driver.objects.all(),
            required=False,
            allow_null=True
        )

    def validate(self, attrs):
        """Validations"""
        mission = attrs.get('mission')

        # Verifier que la mission n'a pas deja un trajet actif
        from apps.fleet.models import Trip
        active_trip = Trip.objects.filter(
            mission=mission,
            status__in=['active', 'paused']
        ).first()
        if active_trip:
            raise serializers.ValidationError({
                'mission': 'Cette mission a deja un trajet actif.'
            })

        # Verifier que la mission est en attente, assignee ou en cours
        if mission.status not in ['pending', 'assigned', 'in_progress']:
            raise serializers.ValidationError({
                'mission': 'La mission doit etre en attente, assignee ou en cours pour demarrer un trajet.'
            })

        # Auto-completer vehicle et driver depuis la mission
        if not attrs.get('vehicle') and mission.vehicle:
            attrs['vehicle'] = mission.vehicle
        if not attrs.get('driver') and mission.driver:
            attrs['driver'] = mission.driver

        # Verifier que vehicle et driver sont definis
        if not attrs.get('vehicle'):
            raise serializers.ValidationError({
                'vehicle': 'Un vehicule doit etre assigne a la mission.'
            })
        if not attrs.get('driver'):
            raise serializers.ValidationError({
                'driver': 'Un chauffeur doit etre assigne a la mission.'
            })

        return attrs

    def create(self, validated_data):
        from django.utils import timezone

        mission = validated_data['mission']
        vehicle = validated_data['vehicle']
        driver = validated_data['driver']

        # Definir l'heure de depart
        validated_data['start_time'] = timezone.now()
        validated_data['status'] = 'active'

        # Ajouter l'organisation
        validated_data['organization'] = mission.organization

        # Mettre a jour la mission si elle n'est pas encore en cours
        if mission.status in ['pending', 'assigned']:
            mission.status = 'in_progress'
            mission.actual_start = timezone.now()
            mission.save(update_fields=['status', 'actual_start'])

        # Mettre a jour le vehicule
        vehicle.status = 'in_use'
        vehicle.save(update_fields=['status'])

        # Mettre a jour le chauffeur
        driver.status = 'on_mission'
        driver.current_vehicle = vehicle
        driver.save(update_fields=['status', 'current_vehicle'])

        trip = Trip.objects.create(**validated_data)
        return trip


class TripUpdateSerializer(serializers.ModelSerializer):
    """Serializer pour mettre à jour un trajet"""

    class Meta:
        model = Trip
        fields = [
            'end_mileage', 'end_fuel_level', 'notes'
        ]

    def update(self, instance, validated_data):
        from django.utils import timezone

        end_mileage = validated_data.get('end_mileage')
        end_fuel_level = validated_data.get('end_fuel_level')

        # Si on termine le trajet
        if end_mileage and not instance.end_time:
            instance.end_time = timezone.now()
            instance.status = 'completed'
            instance.end_mileage = end_mileage

            if end_fuel_level is not None:
                instance.end_fuel_level = end_fuel_level

            # Calculer la distance
            if instance.start_mileage:
                instance.total_distance = end_mileage - instance.start_mileage

            # Calculer le carburant consommé
            if instance.start_fuel_level and end_fuel_level is not None:
                instance.fuel_consumed = instance.start_fuel_level - end_fuel_level

            # Calculer la durée totale
            if instance.start_time:
                duration = instance.end_time - instance.start_time
                instance.total_duration_minutes = max(0, int(duration.total_seconds() / 60) - instance.pause_duration_minutes)

            # Mettre à jour la mission
            instance.mission.status = 'completed'
            instance.mission.actual_end = timezone.now()
            instance.mission.save()

            # Libérer le véhicule et le chauffeur
            instance.vehicle.status = 'available'
            instance.vehicle.current_mileage = end_mileage
            instance.vehicle.save()

            instance.driver.status = 'available'
            instance.driver.current_vehicle = None
            instance.driver.total_trips += 1
            instance.driver.total_distance += instance.total_distance
            instance.driver.save()

        return super().update(instance, validated_data)
