from django.contrib import admin
from .models import (
    Vehicle, Driver, Mission, Trip, TripPause, GPSLocationPoint,
    Incident, MaintenanceRecord, FuelRecord, Activity, MissionAlert,
    DriverNotification
)


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ['license_plate', 'brand', 'model', 'year', 'vehicle_type', 'status', 'organization']
    list_filter = ['status', 'vehicle_type', 'fuel_type', 'organization']
    search_fields = ['license_plate', 'brand', 'model', 'vin']
    ordering = ['-created_at']


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ['user', 'employee_id', 'status', 'driver_license_number', 'total_trips', 'rating', 'organization']
    list_filter = ['status', 'organization']
    search_fields = ['user__username', 'user__email', 'employee_id', 'driver_license_number']
    ordering = ['-created_at']


@admin.register(Mission)
class MissionAdmin(admin.ModelAdmin):
    list_display = ['mission_code', 'title', 'status', 'priority', 'driver', 'vehicle', 'organization']
    list_filter = ['status', 'priority', 'organization']
    search_fields = ['mission_code', 'title', 'description']
    ordering = ['-created_at']


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ['id', 'driver', 'vehicle', 'mission', 'status', 'organization']
    list_filter = ['status', 'organization']
    search_fields = ['driver__user__username', 'vehicle__license_plate']
    ordering = ['-created_at']


@admin.register(TripPause)
class TripPauseAdmin(admin.ModelAdmin):
    list_display = ['trip', 'reason']
    ordering = ['-id']


@admin.register(GPSLocationPoint)
class GPSLocationPointAdmin(admin.ModelAdmin):
    list_display = ['trip', 'latitude', 'longitude', 'speed']
    ordering = ['-id']


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ['id', 'incident_type', 'severity', 'driver', 'vehicle', 'organization']
    list_filter = ['incident_type', 'severity', 'organization']
    search_fields = ['description']
    ordering = ['-id']


@admin.register(MaintenanceRecord)
class MaintenanceRecordAdmin(admin.ModelAdmin):
    list_display = ['vehicle', 'maintenance_type', 'status', 'organization']
    list_filter = ['maintenance_type', 'status', 'organization']
    search_fields = ['vehicle__license_plate', 'description']
    ordering = ['-created_at']


@admin.register(FuelRecord)
class FuelRecordAdmin(admin.ModelAdmin):
    list_display = ['vehicle', 'driver', 'fuel_type', 'quantity', 'total_cost', 'organization']
    list_filter = ['fuel_type', 'organization']
    search_fields = ['vehicle__license_plate', 'driver__user__username']
    ordering = ['-created_at']


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ['activity_type', 'user', 'description', 'created_at', 'organization']
    list_filter = ['activity_type', 'organization', 'created_at']
    search_fields = ['description', 'user__username']
    ordering = ['-created_at']


@admin.register(MissionAlert)
class MissionAlertAdmin(admin.ModelAdmin):
    list_display = ['mission', 'alert_type', 'severity', 'created_at']
    list_filter = ['alert_type', 'severity']
    ordering = ['-created_at']


@admin.register(DriverNotification)
class DriverNotificationAdmin(admin.ModelAdmin):
    list_display = ['driver', 'notification_type', 'title', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read']
    search_fields = ['title', 'message', 'driver__user__username']
    ordering = ['-created_at']
