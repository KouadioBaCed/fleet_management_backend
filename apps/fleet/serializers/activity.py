from rest_framework import serializers
from apps.fleet.models import Activity


class ActivitySerializer(serializers.ModelSerializer):
    """Serializer pour les activités"""

    activity_type_display = serializers.CharField(
        source='get_activity_type_display',
        read_only=True
    )
    severity_display = serializers.CharField(
        source='get_severity_display',
        read_only=True
    )
    vehicle_plate = serializers.SerializerMethodField()
    driver_name = serializers.SerializerMethodField()
    mission_code = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = Activity
        fields = [
            'id',
            'activity_type',
            'activity_type_display',
            'severity',
            'severity_display',
            'title',
            'description',
            'vehicle_plate',
            'driver_name',
            'mission_code',
            'user_name',
            'metadata',
            'created_at',
        ]
        read_only_fields = fields

    def get_vehicle_plate(self, obj):
        return obj.vehicle.license_plate if obj.vehicle else None

    def get_driver_name(self, obj):
        return obj.driver.user.get_full_name() if obj.driver else None

    def get_mission_code(self, obj):
        return obj.mission.mission_code if obj.mission else None

    def get_user_name(self, obj):
        return obj.user.get_full_name() if obj.user else None
