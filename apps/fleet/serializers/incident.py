from rest_framework import serializers
from apps.fleet.models import Incident


class IncidentSerializer(serializers.ModelSerializer):
    """Serializer complet pour incident"""

    incident_type_display = serializers.CharField(source='get_incident_type_display', read_only=True)
    severity_display = serializers.CharField(source='get_severity_display', read_only=True)
    vehicle_plate = serializers.SerializerMethodField()
    driver_name = serializers.SerializerMethodField()
    resolved_by_name = serializers.CharField(
        source='resolved_by.get_full_name',
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = Incident
        fields = '__all__'
        read_only_fields = ['reported_at', 'updated_at']

    def get_vehicle_plate(self, obj):
        return obj.vehicle.license_plate if obj.vehicle else None

    def get_driver_name(self, obj):
        return obj.driver.user.get_full_name() if obj.driver and obj.driver.user else None


class IncidentCreateSerializer(serializers.ModelSerializer):
    """Serializer pour créer un incident"""

    class Meta:
        model = Incident
        fields = [
            'trip', 'driver', 'vehicle', 'incident_type', 'severity',
            'title', 'description', 'latitude', 'longitude', 'address',
            'photo1', 'photo2', 'photo3', 'estimated_cost'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.fleet.models import Vehicle, Driver, Trip
        # Override fields to make them optional
        self.fields['trip'] = serializers.PrimaryKeyRelatedField(
            queryset=Trip.objects.all(),
            required=False,
            allow_null=True
        )
        self.fields['driver'] = serializers.PrimaryKeyRelatedField(
            queryset=Driver.objects.all(),
            required=False,
            allow_null=True
        )
        self.fields['vehicle'] = serializers.PrimaryKeyRelatedField(
            queryset=Vehicle.objects.all(),
            required=False,
            allow_null=True
        )

    def validate(self, attrs):
        """Validations"""
        trip = attrs.get('trip')

        # Si un trajet est fourni, vérifier qu'il est actif
        if trip and trip.status not in ['active', 'paused']:
            raise serializers.ValidationError({
                'trip': 'Le trajet doit etre actif ou en pause pour signaler un incident.'
            })

        # Auto-compléter driver et vehicle depuis le trip si fourni
        if trip:
            if not attrs.get('driver') and trip.driver:
                attrs['driver'] = trip.driver
            if not attrs.get('vehicle') and trip.vehicle:
                attrs['vehicle'] = trip.vehicle

        return attrs

    def create(self, validated_data):
        from apps.fleet.models.notification import NotificationService

        trip = validated_data.get('trip')
        request = self.context.get('request')

        # Ajouter l'organisation depuis le trip ou l'utilisateur
        if trip:
            validated_data['organization'] = trip.organization
            # Marquer le trajet comme ayant des incidents
            trip.has_incidents = True
            trip.save(update_fields=['has_incidents'])
        elif request and hasattr(request, 'user') and request.user.organization:
            validated_data['organization'] = request.user.organization

        incident = Incident.objects.create(**validated_data)

        # Notifier les admins/superviseurs du nouvel incident
        try:
            NotificationService.notify_incident_reported(incident)
        except Exception as e:
            print(f"Error sending incident notification: {e}")

        return incident
