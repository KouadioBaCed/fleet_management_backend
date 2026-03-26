from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Q, Count
from apps.fleet.models import Mission, MissionCheckpoint
from apps.fleet.serializers import (
    MissionSerializer,
    MissionListSerializer,
    MissionCreateSerializer,
    MissionCheckpointSerializer
)
from apps.accounts.permissions import IsOrganizationMember


class MissionViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour gérer les missions (filtré par organisation)

    Paramètres de requête pour list():
    - status: Filtrer par statut (pending, assigned, in_progress, completed, cancelled)
    - priority: Filtrer par priorité (low, medium, high, urgent)
    - search: Recherche par titre, code mission, adresse, chauffeur ou véhicule
    - ordering: Tri (scheduled_start, -scheduled_start, created_at, -created_at, priority)
    """
    queryset = Mission.objects.select_related('vehicle', 'driver', 'driver__user', 'created_by', 'trip').prefetch_related('checkpoints').all()
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get_serializer_class(self):
        if self.action == 'list':
            return MissionListSerializer
        elif self.action == 'create':
            return MissionCreateSerializer
        return MissionSerializer

    def get_queryset(self):
        """Filtrer par organisation, rôle utilisateur et paramètres de requête"""
        user = self.request.user

        # Vérifier l'authentification et l'organisation
        if not user.is_authenticated or not user.organization:
            return self.queryset.none()

        # Filtrer par organisation
        queryset = self.queryset.filter(organization=user.organization)

        # Les chauffeurs ne voient que leurs missions
        if user.is_driver:
            queryset = queryset.filter(driver__user=user)

        # Filtrer par chauffeur (ID du driver)
        driver_filter = self.request.query_params.get('driver')
        if driver_filter:
            queryset = queryset.filter(driver__id=driver_filter)

        # Filtrer par statut (supporte les valeurs separees par virgule)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            valid_statuses = ['pending', 'assigned', 'in_progress', 'completed', 'cancelled']
            statuses = [s.strip() for s in status_filter.split(',') if s.strip() in valid_statuses]
            if statuses:
                queryset = queryset.filter(status__in=statuses)

        # Filtrer par priorité
        priority_filter = self.request.query_params.get('priority')
        if priority_filter and priority_filter in ['low', 'medium', 'high', 'urgent']:
            queryset = queryset.filter(priority=priority_filter)

        # Recherche
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(mission_code__icontains=search) |
                Q(origin_address__icontains=search) |
                Q(destination_address__icontains=search) |
                Q(driver__user__first_name__icontains=search) |
                Q(driver__user__last_name__icontains=search) |
                Q(vehicle__license_plate__icontains=search)
            )

        # Tri
        ordering = self.request.query_params.get('ordering', '-scheduled_start')
        allowed_ordering = [
            'scheduled_start', '-scheduled_start',
            'scheduled_end', '-scheduled_end',
            'created_at', '-created_at',
            'priority', '-priority',
            'title', '-title',
        ]
        if ordering in allowed_ordering:
            queryset = queryset.order_by(ordering)

        return queryset

    def list(self, request, *args, **kwargs):
        """Override list pour ajouter les statistiques"""
        queryset = self.filter_queryset(self.get_queryset())

        # Calculer les stats sur le queryset de base (sans filtres de statut/priorité)
        user = request.user
        base_queryset = self.queryset.filter(organization=user.organization)
        if user.is_driver:
            base_queryset = base_queryset.filter(driver__user=user)

        # Stats par statut
        status_stats = base_queryset.values('status').annotate(count=Count('id'))
        stats = {
            'total': base_queryset.count(),
            'by_status': {
                'pending': 0,
                'assigned': 0,
                'in_progress': 0,
                'completed': 0,
                'cancelled': 0,
            },
            'by_priority': {
                'low': 0,
                'medium': 0,
                'high': 0,
                'urgent': 0,
            }
        }
        for stat in status_stats:
            if stat['status'] in stats['by_status']:
                stats['by_status'][stat['status']] = stat['count']

        # Stats par priorité
        priority_stats = base_queryset.values('priority').annotate(count=Count('id'))
        for stat in priority_stats:
            if stat['priority'] in stats['by_priority']:
                stats['by_priority'][stat['priority']] = stat['count']

        # Pagination
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response.data['stats'] = stats
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'stats': stats,
            'count': queryset.count(),
        })

    def perform_create(self, serializer):
        """Assigner automatiquement l'organisation et le créateur"""
        serializer.save(
            organization=self.request.user.organization,
            created_by=self.request.user
        )

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Démarrer une mission"""
        mission = self.get_object()

        if mission.status != 'assigned':
            return Response(
                {'error': 'La mission doit être assignée pour être démarrée'},
                status=status.HTTP_400_BAD_REQUEST
            )

        mission.status = 'in_progress'
        mission.actual_start = timezone.now()
        mission.save()

        return Response({
            'message': 'Mission démarrée',
            'mission': MissionSerializer(mission).data
        })

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Terminer une mission"""
        mission = self.get_object()

        if mission.status != 'in_progress':
            return Response(
                {'error': 'La mission doit être en cours pour être terminée'},
                status=status.HTTP_400_BAD_REQUEST
            )

        signature = request.data.get('signature')
        if signature:
            mission.signature = signature

        mission.status = 'completed'
        mission.actual_end = timezone.now()
        mission.save()

        # Libérer le véhicule et le chauffeur
        mission.vehicle.status = 'available'
        mission.vehicle.save()

        mission.driver.status = 'available'
        mission.driver.current_vehicle = None
        mission.driver.save()

        return Response({
            'message': 'Mission terminée',
            'mission': MissionSerializer(mission).data
        })

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Annuler une mission avec motif"""
        from apps.fleet.models import NotificationService

        mission = self.get_object()

        if mission.status == 'completed':
            return Response(
                {'error': 'Impossible d\'annuler une mission terminée'},
                status=status.HTTP_400_BAD_REQUEST
            )

        reason = request.data.get('reason', '')
        if not reason:
            return Response(
                {'error': 'Le motif d\'annulation est requis'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Sauvegarder les references avant de modifier
        driver = mission.driver
        vehicle = mission.vehicle
        was_assigned = mission.status in ['assigned', 'in_progress']

        # Annuler la mission
        mission.status = 'cancelled'
        mission.cancellation_reason = reason
        mission.cancelled_at = timezone.now()
        mission.cancelled_by = request.user
        mission.save()

        # Libérer le véhicule et le chauffeur si assignés
        if vehicle and vehicle.status == 'in_use':
            vehicle.status = 'available'
            vehicle.save()

        if driver and driver.status == 'on_mission':
            driver.status = 'available'
            driver.current_vehicle = None
            driver.save()

        # Envoyer notification au conducteur si la mission etait assignee
        if was_assigned and driver:
            NotificationService.notify_mission_cancelled(
                mission=mission,
                reason=reason,
                created_by=request.user
            )

        return Response({
            'message': 'Mission annulée',
            'mission': MissionSerializer(mission).data
        })

    @action(detail=False, methods=['get'])
    def my_missions(self, request):
        """Récupérer les missions du chauffeur connecté (pour mobile)"""
        if not request.user.is_driver:
            return Response(
                {'error': 'Accessible uniquement aux chauffeurs'},
                status=status.HTTP_403_FORBIDDEN
            )

        driver = request.user.driver_profile
        missions = self.queryset.filter(
            driver=driver,
            status__in=['assigned', 'in_progress']
        ).order_by('-scheduled_start')

        serializer = MissionListSerializer(missions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def pending(self, request):
        """Récupérer les missions en attente d'assignation"""
        missions = self.get_queryset().filter(status='pending').order_by('-priority', 'scheduled_start')
        serializer = MissionListSerializer(missions, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        """Assigner un chauffeur et un véhicule à une mission"""
        from apps.fleet.models import Driver, Vehicle, NotificationService

        mission = self.get_object()

        if mission.status != 'pending':
            return Response(
                {'error': 'Seules les missions en attente peuvent être assignées'},
                status=status.HTTP_400_BAD_REQUEST
            )

        driver_id = request.data.get('driver_id')
        vehicle_id = request.data.get('vehicle_id')

        if not driver_id or not vehicle_id:
            return Response(
                {'error': 'driver_id et vehicle_id sont requis'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Vérifier que le chauffeur existe et est disponible
        try:
            driver = Driver.objects.get(
                id=driver_id,
                organization=request.user.organization
            )
        except Driver.DoesNotExist:
            return Response(
                {'error': 'Chauffeur non trouvé'},
                status=status.HTTP_404_NOT_FOUND
            )

        if driver.status != 'available':
            return Response(
                {'error': 'Le chauffeur n\'est pas disponible'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Vérifier que le véhicule existe et est disponible
        try:
            vehicle = Vehicle.objects.get(
                id=vehicle_id,
                organization=request.user.organization
            )
        except Vehicle.DoesNotExist:
            return Response(
                {'error': 'Véhicule non trouvé'},
                status=status.HTTP_404_NOT_FOUND
            )

        if vehicle.status != 'available':
            return Response(
                {'error': 'Le véhicule n\'est pas disponible'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Assigner la mission
        mission.driver = driver
        mission.vehicle = vehicle
        mission.status = 'assigned'
        mission.save()

        # Mettre à jour le statut du chauffeur
        driver.status = 'on_mission'
        driver.current_vehicle = vehicle
        driver.save()

        # Mettre à jour le statut du véhicule
        vehicle.status = 'in_use'
        vehicle.save()

        # Envoyer notification au conducteur
        NotificationService.notify_mission_assigned(
            mission=mission,
            created_by=request.user
        )

        return Response({
            'message': 'Mission assignée avec succès',
            'mission': MissionSerializer(mission).data
        })

    @action(detail=True, methods=['post'])
    def update_details(self, request, pk=None):
        """Mettre a jour les details d'une mission"""
        from apps.fleet.models import NotificationService

        mission = self.get_object()

        if mission.status == 'completed':
            return Response(
                {'error': 'Impossible de modifier une mission terminee'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Suivre les changements pour la notification
        changes = []
        updatable_fields = [
            'title', 'description', 'origin_address', 'origin_latitude', 'origin_longitude',
            'destination_address', 'destination_latitude', 'destination_longitude',
            'scheduled_start', 'scheduled_end', 'estimated_distance', 'priority',
            'responsible_person_name', 'responsible_person_phone', 'notes'
        ]

        field_labels = {
            'title': 'titre',
            'description': 'description',
            'origin_address': 'adresse de depart',
            'destination_address': 'adresse d\'arrivee',
            'scheduled_start': 'heure de depart',
            'scheduled_end': 'heure d\'arrivee',
            'estimated_distance': 'distance estimee',
            'priority': 'priorite',
            'notes': 'notes',
        }

        for field in updatable_fields:
            if field in request.data:
                old_value = getattr(mission, field)
                new_value = request.data[field]
                if str(old_value) != str(new_value):
                    setattr(mission, field, new_value)
                    if field in field_labels:
                        changes.append(field_labels[field])

        # Gérer les checkpoints
        if 'checkpoints' in request.data:
            mission.checkpoints.all().delete()
            for cp_data in request.data['checkpoints']:
                MissionCheckpoint.objects.create(
                    mission=mission,
                    order=cp_data['order'],
                    address=cp_data['address'],
                    latitude=cp_data['latitude'],
                    longitude=cp_data['longitude'],
                    notes=cp_data.get('notes', ''),
                )
            if 'points de passage' not in changes:
                changes.append('points de passage')

        if changes:
            mission.save()

            # Notifier le conducteur si la mission est assignee
            if mission.status in ['assigned', 'in_progress'] and mission.driver:
                NotificationService.notify_mission_updated(
                    mission=mission,
                    changes=changes,
                    created_by=request.user
                )

        return Response({
            'message': 'Mission mise a jour',
            'mission': MissionSerializer(mission).data,
            'changes': changes,
        })

    @action(detail=True, methods=['get'])
    def tracking(self, request, pk=None):
        """Recuperer les donnees de suivi en temps reel d'une mission"""
        from apps.fleet.models import GPSLocationPoint, MissionAlert

        mission = self.get_object()
        now = timezone.now()

        # Position GPS actuelle (dernier point enregistre)
        current_position = None
        last_update = None

        if hasattr(mission, 'trip') and mission.trip:
            last_point = GPSLocationPoint.objects.filter(
                trip=mission.trip
            ).order_by('-recorded_at').first()

            if last_point:
                current_position = {
                    'latitude': float(last_point.latitude),
                    'longitude': float(last_point.longitude),
                    'speed': float(last_point.speed),
                    'heading': float(last_point.heading) if last_point.heading else None,
                    'accuracy': float(last_point.accuracy),
                    'is_moving': last_point.is_moving,
                    'battery_level': last_point.battery_level,
                }
                last_update = last_point.recorded_at

        # Fallback: utiliser la position d'origine de la mission si pas de point GPS
        if current_position is None and mission.origin_latitude and mission.origin_longitude:
            current_position = {
                'latitude': float(mission.origin_latitude),
                'longitude': float(mission.origin_longitude),
                'speed': 0,
                'heading': None,
                'accuracy': 0,
                'is_moving': False,
                'battery_level': None,
            }
            last_update = mission.actual_start or mission.scheduled_start

        # Calculer le statut de retard
        delay_status = self._calculate_delay_status(mission, now)

        # Recuperer les alertes non acquittees
        alerts = MissionAlert.objects.filter(
            mission=mission,
            is_acknowledged=False
        ).order_by('-created_at')[:10]

        alerts_data = [{
            'id': alert.id,
            'type': alert.alert_type,
            'type_display': alert.get_alert_type_display(),
            'severity': alert.severity,
            'title': alert.title,
            'message': alert.message,
            'delay_minutes': alert.delay_minutes,
            'created_at': alert.created_at,
        } for alert in alerts]

        # Generer automatiquement des alertes de retard si necessaire
        self._check_and_create_delay_alerts(mission, delay_status, now)

        return Response({
            'mission': {
                'id': mission.id,
                'mission_code': mission.mission_code,
                'title': mission.title,
                'status': mission.status,
                'priority': mission.priority,
                'driver_name': f"{mission.driver.user.first_name} {mission.driver.user.last_name}",
                'vehicle_plate': mission.vehicle.license_plate,
            },
            'current_position': current_position,
            'last_update': last_update,
            'origin': {
                'address': mission.origin_address,
                'latitude': float(mission.origin_latitude),
                'longitude': float(mission.origin_longitude),
            },
            'destination': {
                'address': mission.destination_address,
                'latitude': float(mission.destination_latitude),
                'longitude': float(mission.destination_longitude),
            },
            'checkpoints': MissionCheckpointSerializer(
                mission.checkpoints.all(), many=True
            ).data,
            'schedule': {
                'scheduled_start': mission.scheduled_start,
                'scheduled_end': mission.scheduled_end,
                'actual_start': mission.actual_start,
                'actual_end': mission.actual_end,
            },
            'delay_status': delay_status,
            'alerts': alerts_data,
            'alerts_count': len(alerts_data),
        })

    def _calculate_delay_status(self, mission, now):
        """Calculer le statut de retard d'une mission"""
        delay_minutes = 0
        delay_type = None
        is_delayed = False

        if mission.status == 'assigned':
            # Mission assignee mais pas encore demarree
            if now > mission.scheduled_start:
                delay_minutes = int((now - mission.scheduled_start).total_seconds() / 60)
                delay_type = 'start'
                is_delayed = delay_minutes > 5  # Tolerance de 5 minutes

        elif mission.status == 'in_progress':
            # Mission en cours
            if mission.actual_start:
                # Verifier si le demarrage etait en retard
                if mission.actual_start > mission.scheduled_start:
                    start_delay = int((mission.actual_start - mission.scheduled_start).total_seconds() / 60)
                else:
                    start_delay = 0

                # Estimer le retard actuel base sur le temps ecoule
                scheduled_duration = (mission.scheduled_end - mission.scheduled_start).total_seconds() / 60
                elapsed_time = (now - mission.actual_start).total_seconds() / 60

                # Si on depasse la fin prevue
                if now > mission.scheduled_end:
                    delay_minutes = int((now - mission.scheduled_end).total_seconds() / 60)
                    delay_type = 'arrival'
                    is_delayed = True
                elif start_delay > 5:
                    delay_minutes = start_delay
                    delay_type = 'progress'
                    is_delayed = True

        return {
            'is_delayed': is_delayed,
            'delay_type': delay_type,
            'delay_minutes': delay_minutes,
            'severity': self._get_delay_severity(delay_minutes),
        }

    def _get_delay_severity(self, delay_minutes):
        """Determiner la severite du retard"""
        if delay_minutes <= 5:
            return 'none'
        elif delay_minutes <= 15:
            return 'info'
        elif delay_minutes <= 30:
            return 'warning'
        else:
            return 'critical'

    def _check_and_create_delay_alerts(self, mission, delay_status, now):
        """Verifier et creer des alertes de retard automatiquement"""
        from apps.fleet.models import MissionAlert
        from datetime import timedelta

        if not delay_status['is_delayed']:
            return

        # Verifier si une alerte similaire existe deja recemment (moins de 30 min)
        recent_alert = MissionAlert.objects.filter(
            mission=mission,
            alert_type=f"delay_{delay_status['delay_type']}",
            created_at__gte=now - timedelta(minutes=30)
        ).exists()

        if recent_alert:
            return

        # Creer une nouvelle alerte
        alert_messages = {
            'start': f"La mission n'a pas demarre a l'heure prevue. Retard: {delay_status['delay_minutes']} minutes.",
            'progress': f"La mission a demarre en retard de {delay_status['delay_minutes']} minutes.",
            'arrival': f"La mission depasse l'heure d'arrivee prevue de {delay_status['delay_minutes']} minutes.",
        }

        alert_titles = {
            'start': "Retard au demarrage",
            'progress': "Mission accompli",
            'arrival': "Retard a l'arrivee",
        }

        MissionAlert.objects.create(
            mission=mission,
            alert_type=f"delay_{delay_status['delay_type']}",
            severity=delay_status['severity'],
            title=alert_titles.get(delay_status['delay_type'], 'Alerte retard'),
            message=alert_messages.get(delay_status['delay_type'], 'Retard detecte'),
            delay_minutes=delay_status['delay_minutes'],
        )

    @action(detail=True, methods=['post'])
    def update_position(self, request, pk=None):
        """Mettre a jour la position GPS d'une mission (depuis l'app mobile)"""
        from apps.fleet.models import GPSLocationPoint, Trip
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        mission = self.get_object()

        if mission.status != 'in_progress':
            return Response(
                {'error': 'La mission doit etre en cours pour mettre a jour la position'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Recuperer ou creer le trip associe
        trip, created = Trip.objects.get_or_create(
            mission=mission,
            defaults={
                'organization': mission.organization,
                'vehicle': mission.vehicle,
                'driver': mission.driver,
                'start_time': mission.actual_start or timezone.now(),
                'start_mileage': mission.vehicle.current_mileage,
                'start_fuel_level': 100,  # A recuperer depuis le vehicule
                'status': 'active',
            }
        )

        # Creer le point GPS
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        speed = request.data.get('speed', 0)
        heading = request.data.get('heading')
        accuracy = request.data.get('accuracy', 10)
        battery_level = request.data.get('battery_level')
        is_moving = request.data.get('is_moving', True)

        if not latitude or not longitude:
            return Response(
                {'error': 'latitude et longitude sont requis'},
                status=status.HTTP_400_BAD_REQUEST
            )

        point = GPSLocationPoint.objects.create(
            trip=trip,
            latitude=latitude,
            longitude=longitude,
            speed=speed,
            heading=heading,
            accuracy=accuracy,
            battery_level=battery_level,
            is_moving=is_moving,
            recorded_at=timezone.now(),
        )

        # Diffuser la mise a jour de position via WebSocket
        channel_layer = get_channel_layer()
        if channel_layer:
            position_data = {
                'type': 'position_update',
                'data': {
                    'mission_id': mission.id,
                    'mission_code': mission.mission_code,
                    'title': mission.title,
                    'priority': mission.priority,
                    'driver_name': f"{mission.driver.user.first_name} {mission.driver.user.last_name}",
                    'vehicle_plate': mission.vehicle.license_plate,
                    'vehicle_id': mission.vehicle.id,
                    'position': {
                        'latitude': float(latitude),
                        'longitude': float(longitude),
                        'speed': float(speed),
                        'heading': float(heading) if heading else None,
                        'is_moving': is_moving,
                        'battery_level': battery_level,
                    },
                    'origin': {
                        'latitude': float(mission.origin_latitude),
                        'longitude': float(mission.origin_longitude),
                        'address': mission.origin_address,
                    },
                    'destination': {
                        'latitude': float(mission.destination_latitude),
                        'longitude': float(mission.destination_longitude),
                        'address': mission.destination_address,
                    },
                    'timestamp': point.recorded_at.isoformat(),
                }
            }
            async_to_sync(channel_layer.group_send)("live_map", position_data)

        return Response({
            'message': 'Position mise a jour',
            'point_id': point.id,
            'recorded_at': point.recorded_at,
        })

    @action(detail=True, methods=['post'])
    def acknowledge_alert(self, request, pk=None):
        """Acquitter une alerte de mission"""
        from apps.fleet.models import MissionAlert

        mission = self.get_object()
        alert_id = request.data.get('alert_id')

        if not alert_id:
            return Response(
                {'error': 'alert_id est requis'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            alert = MissionAlert.objects.get(id=alert_id, mission=mission)
        except MissionAlert.DoesNotExist:
            return Response(
                {'error': 'Alerte non trouvee'},
                status=status.HTTP_404_NOT_FOUND
            )

        alert.is_acknowledged = True
        alert.acknowledged_at = timezone.now()
        alert.acknowledged_by = request.user
        alert.save()

        return Response({
            'message': 'Alerte acquittee',
            'alert_id': alert.id,
        })

    @action(detail=False, methods=['get'])
    def active_tracking(self, request):
        """Recuperer toutes les missions en cours avec leurs donnees de suivi"""
        from apps.fleet.models import GPSLocationPoint, MissionAlert

        now = timezone.now()
        active_missions = self.get_queryset().filter(status='in_progress')

        tracking_data = []
        for mission in active_missions:
            # Position GPS actuelle
            current_position = None
            last_update = None

            if hasattr(mission, 'trip') and mission.trip:
                last_point = GPSLocationPoint.objects.filter(
                    trip=mission.trip
                ).order_by('-recorded_at').first()

                if last_point:
                    current_position = {
                        'latitude': float(last_point.latitude),
                        'longitude': float(last_point.longitude),
                        'speed': float(last_point.speed),
                        'is_moving': last_point.is_moving,
                    }
                    last_update = last_point.recorded_at

            # Fallback: utiliser la position d'origine de la mission si pas de point GPS
            if current_position is None and mission.origin_latitude and mission.origin_longitude:
                current_position = {
                    'latitude': float(mission.origin_latitude),
                    'longitude': float(mission.origin_longitude),
                    'speed': 0,
                    'is_moving': False,
                }
                last_update = mission.actual_start or mission.scheduled_start

            # Statut de retard
            delay_status = self._calculate_delay_status(mission, now)

            # Verifier les alertes
            self._check_and_create_delay_alerts(mission, delay_status, now)

            # Compter les alertes non acquittees
            alerts_count = MissionAlert.objects.filter(
                mission=mission,
                is_acknowledged=False
            ).count()

            tracking_data.append({
                'id': mission.id,
                'mission_code': mission.mission_code,
                'title': mission.title,
                'status': mission.status,
                'priority': mission.priority,
                'driver_name': f"{mission.driver.user.first_name} {mission.driver.user.last_name}",
                'vehicle_plate': mission.vehicle.license_plate,
                'origin': {
                    'address': mission.origin_address,
                    'latitude': float(mission.origin_latitude),
                    'longitude': float(mission.origin_longitude),
                },
                'destination': {
                    'address': mission.destination_address,
                    'latitude': float(mission.destination_latitude),
                    'longitude': float(mission.destination_longitude),
                },
                'current_position': current_position,
                'last_update': last_update,
                'delay_status': delay_status,
                'alerts_count': alerts_count,
                'checkpoints': [
                    {
                        'id': cp.id,
                        'order': cp.order,
                        'address': cp.address,
                        'latitude': float(cp.latitude),
                        'longitude': float(cp.longitude),
                        'notes': cp.notes or '',
                    }
                    for cp in mission.checkpoints.all().order_by('order')
                ],
                'checkpoint_count': mission.checkpoints.count(),
                'scheduled_start': mission.scheduled_start,
                'scheduled_end': mission.scheduled_end,
                'actual_start': mission.actual_start,
            })

        return Response({
            'count': len(tracking_data),
            'missions': tracking_data,
        })

    @action(detail=True, methods=['get'])
    def trip_history(self, request, pk=None):
        """Recuperer l'historique complet d'un trajet termine avec tous les points GPS"""
        from apps.fleet.models import GPSLocationPoint, Trip

        mission = self.get_object()

        # Verifier que la mission a un trajet associe
        try:
            trip = mission.trip
        except Trip.DoesNotExist:
            return Response(
                {'error': 'Aucun trajet associe a cette mission'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Recuperer tous les points GPS du trajet
        gps_points = GPSLocationPoint.objects.filter(trip=trip).order_by('recorded_at')

        # Construire le trace complet
        route_points = []
        stop_points = []
        total_points = gps_points.count()

        # Variables pour detecter les arrets
        stop_threshold_seconds = 120  # Un arret = immobile pendant 2+ minutes
        current_stop_start = None
        current_stop_points = []

        prev_point = None
        for point in gps_points:
            point_data = {
                'latitude': float(point.latitude),
                'longitude': float(point.longitude),
                'speed': float(point.speed),
                'heading': float(point.heading) if point.heading else None,
                'altitude': float(point.altitude) if point.altitude else None,
                'accuracy': float(point.accuracy),
                'is_moving': point.is_moving,
                'recorded_at': point.recorded_at.isoformat(),
            }
            route_points.append(point_data)

            # Detecter les arrets (vitesse < 2 km/h ou is_moving = False)
            is_stopped = point.speed < 2 or not point.is_moving

            if is_stopped:
                if current_stop_start is None:
                    current_stop_start = point
                    current_stop_points = [point]
                else:
                    current_stop_points.append(point)
            else:
                # Fin d'un arret potentiel
                if current_stop_start and len(current_stop_points) > 0:
                    stop_duration = (current_stop_points[-1].recorded_at - current_stop_start.recorded_at).total_seconds()
                    if stop_duration >= stop_threshold_seconds:
                        # C'est un vrai arret
                        # Calculer la position moyenne
                        avg_lat = sum(float(p.latitude) for p in current_stop_points) / len(current_stop_points)
                        avg_lng = sum(float(p.longitude) for p in current_stop_points) / len(current_stop_points)

                        stop_points.append({
                            'latitude': avg_lat,
                            'longitude': avg_lng,
                            'start_time': current_stop_start.recorded_at.isoformat(),
                            'end_time': current_stop_points[-1].recorded_at.isoformat(),
                            'duration_minutes': int(stop_duration / 60),
                        })

                current_stop_start = None
                current_stop_points = []

            prev_point = point

        # Verifier s'il y a un arret final
        if current_stop_start and len(current_stop_points) > 0:
            stop_duration = (current_stop_points[-1].recorded_at - current_stop_start.recorded_at).total_seconds()
            if stop_duration >= stop_threshold_seconds:
                avg_lat = sum(float(p.latitude) for p in current_stop_points) / len(current_stop_points)
                avg_lng = sum(float(p.longitude) for p in current_stop_points) / len(current_stop_points)
                stop_points.append({
                    'latitude': avg_lat,
                    'longitude': avg_lng,
                    'start_time': current_stop_start.recorded_at.isoformat(),
                    'end_time': current_stop_points[-1].recorded_at.isoformat(),
                    'duration_minutes': int(stop_duration / 60),
                })

        # Calculer les statistiques du trajet
        speeds = [float(p.speed) for p in gps_points if p.speed > 0]
        max_speed = max(speeds) if speeds else 0
        avg_speed = sum(speeds) / len(speeds) if speeds else 0

        return Response({
            'mission': {
                'id': mission.id,
                'mission_code': mission.mission_code,
                'title': mission.title,
                'status': mission.status,
                'priority': mission.priority,
                'driver_name': f"{mission.driver.user.first_name} {mission.driver.user.last_name}" if mission.driver else None,
                'vehicle_plate': mission.vehicle.license_plate if mission.vehicle else None,
            },
            'trip': {
                'id': trip.id,
                'status': trip.status,
                'start_time': trip.start_time.isoformat() if trip.start_time else None,
                'end_time': trip.end_time.isoformat() if trip.end_time else None,
                'total_distance': float(trip.total_distance),
                'total_duration_minutes': trip.total_duration_minutes,
                'pause_duration_minutes': trip.pause_duration_minutes,
                'average_speed': float(trip.average_speed) if trip.average_speed else avg_speed,
                'max_speed': float(trip.max_speed) if trip.max_speed else max_speed,
                'fuel_consumed': float(trip.fuel_consumed) if trip.fuel_consumed else None,
            },
            'origin': {
                'latitude': float(mission.origin_latitude),
                'longitude': float(mission.origin_longitude),
                'address': mission.origin_address,
            },
            'destination': {
                'latitude': float(mission.destination_latitude),
                'longitude': float(mission.destination_longitude),
                'address': mission.destination_address,
            },
            'checkpoints': MissionCheckpointSerializer(
                mission.checkpoints.all(), many=True
            ).data,
            'route': {
                'total_points': total_points,
                'points': route_points,
            },
            'stops': {
                'count': len(stop_points),
                'points': stop_points,
            },
        })
