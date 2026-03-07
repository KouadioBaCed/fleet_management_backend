from rest_framework import serializers
from apps.fleet.models import MaintenanceRecord


class MaintenanceRecordSerializer(serializers.ModelSerializer):
    """Serializer complet pour maintenance"""

    maintenance_type_display = serializers.CharField(
        source='get_maintenance_type_display',
        read_only=True
    )
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    vehicle_plate = serializers.CharField(source='vehicle.license_plate', read_only=True)
    created_by_name = serializers.CharField(
        source='created_by.get_full_name',
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = MaintenanceRecord
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'created_by']


class MaintenanceRecordCreateSerializer(serializers.ModelSerializer):
    """Serializer pour créer une maintenance"""

    class Meta:
        model = MaintenanceRecord
        fields = [
            'vehicle', 'maintenance_type', 'scheduled_date',
            'mileage_at_service', 'description', 'service_provider',
            'total_cost', 'notes'
        ]

    def create(self, validated_data):
        # Définir le créateur
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['created_by'] = request.user

        maintenance = MaintenanceRecord.objects.create(**validated_data)

        # Si la maintenance est programmée, marquer le véhicule en maintenance
        if validated_data.get('scheduled_date'):
            vehicle = validated_data['vehicle']
            vehicle.status = 'maintenance'
            vehicle.last_maintenance_date = validated_data['scheduled_date']
            vehicle.save()

        return maintenance
