from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    VehicleViewSet,
    DriverViewSet,
    MissionViewSet,
    TripViewSet,
    IncidentViewSet,
    MaintenanceRecordViewSet,
    FuelRecordViewSet,
    track_location,
    batch_track_location,
    live_positions,
    reports_summary,
    export_csv,
    export_json,
    fleet_analytics,
    UserNotificationViewSet,
    DriverNotificationViewSet
)

router = DefaultRouter()
router.register(r'vehicles', VehicleViewSet, basename='vehicle')
router.register(r'drivers', DriverViewSet, basename='driver')
router.register(r'missions', MissionViewSet, basename='mission')
router.register(r'trips', TripViewSet, basename='trip')
router.register(r'incidents', IncidentViewSet, basename='incident')
router.register(r'maintenance', MaintenanceRecordViewSet, basename='maintenance')
router.register(r'fuel', FuelRecordViewSet, basename='fuel')
router.register(r'notifications', UserNotificationViewSet, basename='user-notification')
router.register(r'driver-notifications', DriverNotificationViewSet, basename='driver-notification')

urlpatterns = [
    # GPS endpoints
    path('gps/track/', track_location, name='gps_track'),
    path('gps/batch/', batch_track_location, name='gps_batch'),
    path('gps/live-positions/', live_positions, name='live_positions'),

    # Reports endpoints
    path('reports/summary/', reports_summary, name='reports_summary'),
    path('reports/export/csv/', export_csv, name='export_csv'),
    path('reports/export/json/', export_json, name='export_json'),

    # Analytics endpoints
    path('analytics/fleet/', fleet_analytics, name='fleet_analytics'),

    # Router endpoints
    path('', include(router.urls)),
]
