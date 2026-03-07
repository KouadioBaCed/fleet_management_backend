from rest_framework import serializers
from apps.fleet.models.notification import DriverNotification, UserNotification


class DriverNotificationSerializer(serializers.ModelSerializer):
    """Serializer pour les notifications des conducteurs"""

    notification_type_display = serializers.CharField(source='get_notification_type_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    driver_name = serializers.SerializerMethodField()
    mission_code = serializers.SerializerMethodField()

    class Meta:
        model = DriverNotification
        fields = [
            'id', 'driver', 'driver_name', 'notification_type', 'notification_type_display',
            'priority', 'priority_display', 'title', 'message', 'mission', 'mission_code',
            'data', 'is_read', 'read_at', 'push_sent', 'push_sent_at',
            'created_by', 'created_at'
        ]
        read_only_fields = ['created_at', 'read_at', 'push_sent_at']

    def get_driver_name(self, obj):
        if obj.driver and obj.driver.user:
            return obj.driver.user.get_full_name()
        return None

    def get_mission_code(self, obj):
        return obj.mission.mission_code if obj.mission else None


class UserNotificationSerializer(serializers.ModelSerializer):
    """Serializer pour les notifications des utilisateurs (admin/superviseur)"""

    notification_type_display = serializers.CharField(source='get_notification_type_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    vehicle_plate = serializers.SerializerMethodField()
    driver_name = serializers.SerializerMethodField()
    incident_title = serializers.SerializerMethodField()
    maintenance_type = serializers.SerializerMethodField()
    mission_code = serializers.SerializerMethodField()

    class Meta:
        model = UserNotification
        fields = [
            'id', 'user', 'notification_type', 'notification_type_display',
            'priority', 'priority_display', 'title', 'message',
            'incident', 'incident_title', 'vehicle', 'vehicle_plate',
            'driver', 'driver_name', 'maintenance', 'maintenance_type',
            'mission', 'mission_code', 'data',
            'is_read', 'read_at', 'email_sent', 'sms_sent', 'push_sent',
            'created_at'
        ]
        read_only_fields = ['created_at', 'read_at']

    def get_vehicle_plate(self, obj):
        return obj.vehicle.license_plate if obj.vehicle else None

    def get_driver_name(self, obj):
        if obj.driver and obj.driver.user:
            return obj.driver.user.get_full_name()
        return None

    def get_incident_title(self, obj):
        return obj.incident.title if obj.incident else None

    def get_maintenance_type(self, obj):
        return obj.maintenance.get_maintenance_type_display() if obj.maintenance else None

    def get_mission_code(self, obj):
        return obj.mission.mission_code if obj.mission else None


class NotificationListSerializer(serializers.ModelSerializer):
    """Serializer simplifie pour les listes de notifications"""

    notification_type_display = serializers.CharField(source='get_notification_type_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)

    class Meta:
        model = UserNotification
        fields = [
            'id', 'notification_type', 'notification_type_display',
            'priority', 'priority_display', 'title', 'message',
            'is_read', 'created_at', 'data'
        ]


class MarkNotificationsReadSerializer(serializers.Serializer):
    """Serializer pour marquer des notifications comme lues"""
    notification_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="Liste des IDs de notifications a marquer comme lues. Si vide, toutes les notifications seront marquees."
    )
