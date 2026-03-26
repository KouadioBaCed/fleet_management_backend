from .vehicle import VehicleSerializer, VehicleListSerializer, VehicleCreateSerializer
from .driver import DriverSerializer, DriverListSerializer, DriverCreateSerializer
from .mission import MissionSerializer, MissionListSerializer, MissionCreateSerializer, MissionCheckpointSerializer
from .trip import TripSerializer, TripCreateSerializer, TripUpdateSerializer
from .gps import GPSLocationPointSerializer, GPSBatchSerializer
from .incident import IncidentSerializer, IncidentCreateSerializer
from .maintenance import MaintenanceRecordSerializer, MaintenanceRecordCreateSerializer
from .fuel import FuelRecordSerializer, FuelRecordCreateSerializer
from .activity import ActivitySerializer
from .vehicle_document import VehicleDocumentSerializer, DocumentAlertSerializer
from .notification import (
    DriverNotificationSerializer,
    UserNotificationSerializer,
    NotificationListSerializer,
    MarkNotificationsReadSerializer
)

__all__ = [
    'VehicleSerializer',
    'VehicleListSerializer',
    'VehicleCreateSerializer',
    'DriverSerializer',
    'DriverListSerializer',
    'DriverCreateSerializer',
    'MissionSerializer',
    'MissionListSerializer',
    'MissionCreateSerializer',
    'MissionCheckpointSerializer',
    'TripSerializer',
    'TripCreateSerializer',
    'TripUpdateSerializer',
    'GPSLocationPointSerializer',
    'GPSBatchSerializer',
    'IncidentSerializer',
    'IncidentCreateSerializer',
    'MaintenanceRecordSerializer',
    'MaintenanceRecordCreateSerializer',
    'FuelRecordSerializer',
    'FuelRecordCreateSerializer',
    'ActivitySerializer',
    'DriverNotificationSerializer',
    'UserNotificationSerializer',
    'NotificationListSerializer',
    'MarkNotificationsReadSerializer',
    'VehicleDocumentSerializer',
    'DocumentAlertSerializer',
]
