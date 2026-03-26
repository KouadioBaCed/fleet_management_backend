from rest_framework import serializers
from apps.fleet.models import VehicleDocument


class VehicleDocumentSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    days_until_expiry = serializers.IntegerField(read_only=True)
    file_name = serializers.CharField(read_only=True)

    class Meta:
        model = VehicleDocument
        fields = [
            'id', 'vehicle', 'document_type', 'document_number',
            'issue_date', 'expiry_date', 'file', 'file_name',
            'status', 'days_until_expiry', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'vehicle', 'created_at', 'updated_at']


class DocumentAlertSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    vehicle_id = serializers.IntegerField()
    vehicle_plate = serializers.CharField()
    vehicle_brand = serializers.CharField()
    vehicle_model = serializers.CharField()
    document_type = serializers.CharField()
    document_number = serializers.CharField()
    expiry_date = serializers.DateField()
    days_until_expiry = serializers.IntegerField()
    status = serializers.CharField()
