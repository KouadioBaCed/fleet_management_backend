from rest_framework import serializers
from apps.fleet.models import FuelRecord


class FuelRecordSerializer(serializers.ModelSerializer):
    """Serializer complet pour ravitaillement"""

    fuel_type_display = serializers.CharField(source='get_fuel_type_display', read_only=True)
    vehicle_plate = serializers.CharField(source='vehicle.license_plate', read_only=True)
    driver_name = serializers.CharField(
        source='driver.user.get_full_name',
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = FuelRecord
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'calculated_consumption']


class FuelRecordCreateSerializer(serializers.ModelSerializer):
    """Serializer pour créer un ravitaillement"""

    class Meta:
        model = FuelRecord
        fields = [
            'vehicle', 'driver', 'trip', 'refuel_date', 'station_name',
            'station_address', 'latitude', 'longitude', 'fuel_type',
            'quantity', 'unit_price', 'total_cost', 'mileage_at_refuel',
            'distance_since_last_refuel', 'is_full_tank', 'receipt_photo',
            'receipt_number', 'notes'
        ]

    def validate(self, attrs):
        """Validations"""
        # Vérifier que le type de carburant correspond au véhicule
        vehicle = attrs.get('vehicle')
        fuel_type = attrs.get('fuel_type')

        if vehicle and fuel_type and vehicle.fuel_type != fuel_type:
            raise serializers.ValidationError({
                'fuel_type': f'Le véhicule utilise du {vehicle.get_fuel_type_display()}, pas du {dict(FuelRecord.FUEL_TYPE_CHOICES)[fuel_type]}.'
            })

        # Calculer le coût total si pas fourni
        if 'total_cost' not in attrs and 'quantity' in attrs and 'unit_price' in attrs:
            attrs['total_cost'] = attrs['quantity'] * attrs['unit_price']

        return attrs

    def create(self, validated_data):
        # Calculer la distance depuis le dernier plein si non fournie
        vehicle = validated_data['vehicle']
        mileage = validated_data['mileage_at_refuel']

        if 'distance_since_last_refuel' not in validated_data:
            last_refuel = FuelRecord.objects.filter(
                vehicle=vehicle,
                is_full_tank=True
            ).order_by('-refuel_date').first()

            if last_refuel:
                validated_data['distance_since_last_refuel'] = mileage - last_refuel.mileage_at_refuel

        return super().create(validated_data)
