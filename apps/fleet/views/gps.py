from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from apps.fleet.models import GPSLocationPoint, Vehicle
from apps.fleet.serializers import GPSLocationPointSerializer, GPSBatchSerializer
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def track_location(request):
    """Enregistrer un point GPS"""
    serializer = GPSLocationPointSerializer(data=request.data)

    if serializer.is_valid():
        location_point = serializer.save()

        # Broadcaster via WebSocket
        channel_layer = get_channel_layer()

        # Envoyer à la carte globale (format attendu par le frontend)
        async_to_sync(channel_layer.group_send)(
            "live_map",
            {
                "type": "position_update",
                "data": {
                    "type": "position_update",
                    "mission_id": location_point.trip.mission.id,
                    "position": {
                        "latitude": float(location_point.latitude),
                        "longitude": float(location_point.longitude),
                        "speed": float(location_point.speed),
                        "heading": float(location_point.heading or 0),
                        "is_moving": location_point.is_moving,
                        "battery_level": location_point.battery_level,
                    },
                    "timestamp": location_point.recorded_at.isoformat(),
                }
            }
        )

        # Envoyer au groupe du trajet
        async_to_sync(channel_layer.group_send)(
            f"trip_{location_point.trip.id}",
            {
                "type": "trip_update",
                "data": GPSLocationPointSerializer(location_point).data
            }
        )

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def batch_track_location(request):
    """Enregistrer plusieurs points GPS en batch"""
    points_data = request.data.get('points', [])

    if not points_data:
        return Response(
            {"error": "Aucun point fourni"},
            status=status.HTTP_400_BAD_REQUEST
        )

    created_points = []
    errors = []

    for point_data in points_data:
        serializer = GPSLocationPointSerializer(data=point_data)
        if serializer.is_valid():
            location_point = serializer.save()
            created_points.append(location_point)
        else:
            errors.append(serializer.errors)

    # Broadcaster le dernier point
    if created_points:
        last_point = created_points[-1]
        channel_layer = get_channel_layer()

        async_to_sync(channel_layer.group_send)(
            "live_map",
            {
                "type": "position_update",
                "data": {
                    "type": "position_update",
                    "mission_id": last_point.trip.mission.id,
                    "position": {
                        "latitude": float(last_point.latitude),
                        "longitude": float(last_point.longitude),
                        "speed": float(last_point.speed),
                        "heading": float(last_point.heading or 0),
                        "is_moving": last_point.is_moving,
                        "battery_level": last_point.battery_level,
                    },
                    "timestamp": last_point.recorded_at.isoformat(),
                }
            }
        )

    return Response({
        "message": f"{len(created_points)} points enregistrés",
        "count": len(created_points),
        "errors": errors if errors else None
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def live_positions(request):
    """Récupérer les dernières positions de tous les véhicules actifs de l'organisation"""
    from apps.fleet.models import Trip

    user = request.user

    # Vérifier que l'utilisateur a une organisation
    if not user.organization:
        return Response([])

    # Récupérer les trajets actifs de l'organisation
    active_trips = Trip.objects.filter(
        status='active',
        organization=user.organization
    )

    positions = []
    for trip in active_trips:
        # Récupérer le dernier point GPS
        last_point = trip.location_points.order_by('-recorded_at').first()

        if last_point:
            positions.append({
                'vehicleId': trip.vehicle.id,
                'vehiclePlate': trip.vehicle.license_plate,
                'driverName': trip.driver.user.get_full_name(),
                'latitude': float(last_point.latitude),
                'longitude': float(last_point.longitude),
                'speed': float(last_point.speed),
                'heading': float(last_point.heading or 0),
                'timestamp': last_point.recorded_at.isoformat(),
                'tripId': trip.id,
                'missionCode': trip.mission.mission_code,
            })

    return Response(positions)
