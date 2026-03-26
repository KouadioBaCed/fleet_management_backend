from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from apps.fleet.models import Trip, TripPause, TripStop
from apps.fleet.serializers import (
    TripSerializer,
    TripCreateSerializer,
    TripUpdateSerializer
)
from apps.fleet.mixins import OrganizationFilterMixin
from apps.accounts.permissions import IsOrganizationMember


class TripViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    """ViewSet pour gérer les trajets (filtré par organisation)"""
    queryset = Trip.objects.select_related('mission', 'vehicle', 'driver').all()
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get_serializer_class(self):
        if self.action == 'create':
            return TripCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return TripUpdateSerializer
        return TripSerializer

    def create(self, request, *args, **kwargs):
        """Override create to log validation errors"""
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            print(f"[Trip Create] Validation errors: {serializer.errors}")
            print(f"[Trip Create] Request data: {request.data}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=False, methods=['get'])
    def active(self, request):
        """Récupérer tous les trajets actifs de l'organisation"""
        trips = self.get_queryset().filter(status='active')
        serializer = TripSerializer(trips, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        """Mettre en pause un trajet"""
        trip = self.get_object()

        if trip.status != 'active':
            return Response(
                {'error': 'Le trajet doit être actif pour être mis en pause'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Creer un enregistrement de pause
        pause_data = {
            'trip': trip,
            'started_at': timezone.now(),
            'reason': request.data.get('reason', 'break'),
            'notes': request.data.get('notes', ''),
        }

        # Ajouter localisation si fournie
        if 'latitude' in request.data and 'longitude' in request.data:
            pause_data['latitude'] = request.data['latitude']
            pause_data['longitude'] = request.data['longitude']

        pause = TripPause.objects.create(**pause_data)

        trip.status = 'paused'
        trip.save()

        return Response({
            'message': 'Trajet mis en pause',
            'trip': TripSerializer(trip).data,
            'pause': {
                'id': pause.id,
                'started_at': pause.started_at.isoformat(),
                'reason': pause.reason,
            }
        })

    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        """Reprendre un trajet en pause"""
        trip = self.get_object()

        if trip.status != 'paused':
            return Response(
                {'error': 'Le trajet doit être en pause pour être repris'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Terminer la pause active
        active_pause = trip.pauses.filter(ended_at__isnull=True).first()
        pause_duration = 0

        if active_pause:
            active_pause.end_pause()
            pause_duration = active_pause.duration_minutes

        trip.status = 'active'
        trip.save()

        return Response({
            'message': 'Trajet repris',
            'trip': TripSerializer(trip).data,
            'pause_duration_minutes': pause_duration,
            'total_pause_minutes': trip.pause_duration_minutes,
        })

    @action(detail=True, methods=['get'])
    def pauses(self, request, pk=None):
        """Recuperer l'historique des pauses du trajet"""
        trip = self.get_object()
        pauses = trip.pauses.all().order_by('-started_at')

        pauses_data = [{
            'id': p.id,
            'started_at': p.started_at.isoformat(),
            'ended_at': p.ended_at.isoformat() if p.ended_at else None,
            'duration_minutes': p.duration_minutes,
            'reason': p.reason,
            'reason_display': p.get_reason_display(),
            'notes': p.notes,
            'is_active': p.is_active,
            'latitude': float(p.latitude) if p.latitude else None,
            'longitude': float(p.longitude) if p.longitude else None,
        } for p in pauses]

        return Response({
            'pauses': pauses_data,
            'total_pause_minutes': trip.pause_duration_minutes,
            'pauses_count': len(pauses_data),
        })

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Terminer un trajet"""
        trip = self.get_object()

        if trip.status not in ['active', 'paused']:
            return Response(
                {'error': 'Le trajet doit être actif ou en pause pour être terminé'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Mise à jour avec les données de fin
        serializer = TripUpdateSerializer(trip, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'Trajet terminé',
                'trip': TripSerializer(trip).data
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def report_stop(self, request, pk=None):
        """Enregistrer un arret detecte pendant le trajet"""
        trip = self.get_object()

        if trip.status not in ['active', 'paused']:
            return Response(
                {'error': 'Le trajet doit etre actif pour enregistrer un arret'},
                status=status.HTTP_400_BAD_REQUEST
            )

        reason = request.data.get('reason', 'other')
        valid_reasons = [c[0] for c in TripStop.REASON_CHOICES]
        if reason not in valid_reasons:
            return Response(
                {'error': f'Raison invalide. Choix: {valid_reasons}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        stop = TripStop.objects.create(
            trip=trip,
            reason=reason,
            notes=request.data.get('notes', ''),
            stopped_at=request.data.get('stopped_at', timezone.now()),
            duration_seconds=request.data.get('duration_seconds', 0),
            latitude=request.data.get('latitude'),
            longitude=request.data.get('longitude'),
        )

        return Response({
            'id': stop.id,
            'reason': stop.reason,
            'reason_display': stop.get_reason_display(),
            'notes': stop.notes,
            'stopped_at': stop.stopped_at.isoformat(),
            'duration_seconds': stop.duration_seconds,
            'latitude': float(stop.latitude) if stop.latitude else None,
            'longitude': float(stop.longitude) if stop.longitude else None,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def stops(self, request, pk=None):
        """Recuperer l'historique des arrets du trajet"""
        trip = self.get_object()
        stops = trip.stops.all().order_by('-stopped_at')

        stops_data = [{
            'id': s.id,
            'reason': s.reason,
            'reason_display': s.get_reason_display(),
            'notes': s.notes,
            'stopped_at': s.stopped_at.isoformat(),
            'duration_seconds': s.duration_seconds,
            'latitude': float(s.latitude) if s.latitude else None,
            'longitude': float(s.longitude) if s.longitude else None,
        } for s in stops]

        return Response({
            'stops': stops_data,
            'stops_count': len(stops_data),
        })

    @action(detail=True, methods=['get'])
    def route(self, request, pk=None):
        """Récupérer les points GPS du trajet"""
        trip = self.get_object()
        points = trip.location_points.all().order_by('recorded_at')
        from apps.fleet.serializers import GPSLocationPointSerializer
        serializer = GPSLocationPointSerializer(points, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def analytics(self, request, pk=None):
        """Récupérer les analytiques du trajet"""
        trip = self.get_object()

        analytics = {
            'total_distance': float(trip.total_distance),
            'total_duration_minutes': trip.total_duration_minutes,
            'average_speed': float(trip.average_speed),
            'max_speed': float(trip.max_speed),
            'fuel_consumed': float(trip.fuel_consumed),
            'has_incidents': trip.has_incidents,
            'incidents_count': trip.incidents.count(),
            'points_count': trip.location_points.count(),
        }

        return Response(analytics)
