from rest_framework import serializers
from apps.fleet.models import Vehicle


class VehicleListSerializer(serializers.ModelSerializer):
    """Serializer léger pour liste de véhicules"""

    status_display = serializers.CharField(source='get_status_display', read_only=True)
    vehicle_type_display = serializers.CharField(source='get_vehicle_type_display', read_only=True)
    fuel_type_display = serializers.CharField(source='get_fuel_type_display', read_only=True)
    needs_maintenance = serializers.BooleanField(read_only=True)
    maintenance_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Vehicle
        fields = [
            'id', 'license_plate', 'brand', 'model', 'year',
            'vehicle_type', 'vehicle_type_display', 'status',
            'status_display', 'current_mileage', 'needs_maintenance',
            'maintenance_overdue', 'maintenance_frequency_km', 'maintenance_frequency_months',
            'last_maintenance_date', 'next_maintenance_mileage',
            'photo', 'fuel_type', 'fuel_type_display', 'color',
            'fuel_capacity', 'fuel_consumption', 'vin_number',
            'insurance_number', 'insurance_expiry', 'gps_device_id', 'notes'
        ]


class VehicleSerializer(serializers.ModelSerializer):
    """Serializer complet pour véhicule"""

    status_display = serializers.CharField(source='get_status_display', read_only=True)
    vehicle_type_display = serializers.CharField(source='get_vehicle_type_display', read_only=True)
    fuel_type_display = serializers.CharField(source='get_fuel_type_display', read_only=True)
    is_available = serializers.BooleanField(read_only=True)
    needs_maintenance = serializers.BooleanField(read_only=True)
    maintenance_overdue = serializers.BooleanField(read_only=True)
    next_maintenance_date = serializers.DateField(read_only=True, allow_null=True)

    class Meta:
        model = Vehicle
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class VehicleCreateSerializer(serializers.ModelSerializer):
    """Serializer pour création de véhicule"""

    class Meta:
        model = Vehicle
        exclude = ['created_at', 'updated_at']
        extra_kwargs = {
            'organization': {'required': False, 'allow_null': True},
        }

    def validate_license_plate(self, value):
        """Valider que la plaque est unique"""
        if Vehicle.objects.filter(license_plate=value).exists():
            raise serializers.ValidationError(
                "Un véhicule avec cette plaque existe déjà."
            )
        return value.upper()

    def validate_vin_number(self, value):
        """Valider que le VIN est unique et de longueur correcte"""
        if len(value) != 17:
            raise serializers.ValidationError(
                "Le numéro VIN doit contenir exactement 17 caractères."
            )
        if Vehicle.objects.filter(vin_number=value).exists():
            raise serializers.ValidationError(
                "Un véhicule avec ce numéro VIN existe déjà."
            )
        return value.upper()
