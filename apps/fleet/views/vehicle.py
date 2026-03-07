from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Count
from apps.fleet.models import Vehicle
from apps.fleet.serializers import (
    VehicleSerializer,
    VehicleListSerializer,
    VehicleCreateSerializer
)
from apps.fleet.mixins import OrganizationFilterMixin
from apps.accounts.permissions import IsOrganizationMember


class VehicleViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    """
    ViewSet pour gérer les véhicules (filtré par organisation)

    Paramètres de requête pour list():
    - status: Filtrer par statut (available, in_use, maintenance, out_of_service)
    - search: Recherche par immatriculation, marque ou modèle
    - fuel_type: Filtrer par type de carburant
    - vehicle_type: Filtrer par type de véhicule
    - ordering: Tri (license_plate, brand, year, -created_at, etc.)
    """
    queryset = Vehicle.objects.all()
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get_serializer_class(self):
        if self.action == 'list':
            return VehicleListSerializer
        elif self.action == 'create':
            return VehicleCreateSerializer
        return VehicleSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filtrer par statut
        status_filter = self.request.query_params.get('status')
        if status_filter and status_filter in ['available', 'in_use', 'maintenance', 'out_of_service']:
            queryset = queryset.filter(status=status_filter)

        # Recherche par immatriculation, marque ou modèle
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(license_plate__icontains=search) |
                Q(brand__icontains=search) |
                Q(model__icontains=search) |
                Q(vin_number__icontains=search)
            )

        # Filtrer par type de carburant
        fuel_type = self.request.query_params.get('fuel_type')
        if fuel_type:
            queryset = queryset.filter(fuel_type=fuel_type)

        # Filtrer par type de véhicule
        vehicle_type = self.request.query_params.get('vehicle_type')
        if vehicle_type:
            queryset = queryset.filter(vehicle_type=vehicle_type)

        # Tri
        ordering = self.request.query_params.get('ordering', '-created_at')
        allowed_ordering = ['license_plate', '-license_plate', 'brand', '-brand',
                           'year', '-year', 'created_at', '-created_at',
                           'current_mileage', '-current_mileage']
        if ordering in allowed_ordering:
            queryset = queryset.order_by(ordering)

        return queryset

    def list(self, request, *args, **kwargs):
        """Override list pour ajouter les statistiques"""
        queryset = self.filter_queryset(self.get_queryset())

        # Calculer les stats par statut sur le queryset de base (sans filtre de statut)
        base_queryset = super().get_queryset()
        stats = base_queryset.values('status').annotate(count=Count('id'))
        stats_dict = {
            'total': base_queryset.count(),
            'available': 0,
            'in_use': 0,
            'maintenance': 0,
            'out_of_service': 0,
        }
        for stat in stats:
            if stat['status'] in stats_dict:
                stats_dict[stat['status']] = stat['count']

        # Pagination
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response.data['stats'] = stats_dict
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'stats': stats_dict,
            'count': queryset.count(),
        })

    @action(detail=False, methods=['get'])
    def available(self, request):
        """Récupérer tous les véhicules disponibles de l'organisation"""
        vehicles = self.get_queryset().filter(status='available')
        serializer = VehicleListSerializer(vehicles, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Récupérer les statistiques des véhicules"""
        queryset = super().get_queryset()
        stats = queryset.values('status').annotate(count=Count('id'))

        result = {
            'total': queryset.count(),
            'by_status': {
                'available': 0,
                'in_use': 0,
                'maintenance': 0,
                'out_of_service': 0,
            },
            'by_fuel_type': {},
            'by_vehicle_type': {},
        }

        for stat in stats:
            if stat['status'] in result['by_status']:
                result['by_status'][stat['status']] = stat['count']

        # Stats par type de carburant
        fuel_stats = queryset.values('fuel_type').annotate(count=Count('id'))
        for stat in fuel_stats:
            result['by_fuel_type'][stat['fuel_type']] = stat['count']

        # Stats par type de véhicule
        type_stats = queryset.values('vehicle_type').annotate(count=Count('id'))
        for stat in type_stats:
            result['by_vehicle_type'][stat['vehicle_type']] = stat['count']

        return Response(result)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """Récupérer l'historique des trajets d'un véhicule"""
        vehicle = self.get_object()
        trips = vehicle.trips.all().order_by('-start_time')[:20]
        from apps.fleet.serializers import TripSerializer
        serializer = TripSerializer(trips, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def maintenance_history(self, request, pk=None):
        """Récupérer l'historique de maintenance d'un véhicule"""
        vehicle = self.get_object()
        records = vehicle.maintenance_records.all().order_by('-scheduled_date')[:20]
        from apps.fleet.serializers import MaintenanceRecordSerializer
        serializer = MaintenanceRecordSerializer(records, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def current_driver(self, request, pk=None):
        """Récupérer le conducteur actuel du véhicule"""
        vehicle = self.get_object()
        driver = vehicle.current_driver.first()
        if driver:
            from apps.fleet.serializers import DriverSerializer
            serializer = DriverSerializer(driver)
            return Response(serializer.data)
        return Response(None)

    @action(detail=True, methods=['get'])
    def details(self, request, pk=None):
        """Récupérer tous les détails d'un véhicule (info, historique, maintenance, conducteur)"""
        vehicle = self.get_object()

        # Context pour les serializers (nécessaire pour les URLs absolues des images)
        context = {'request': request}

        # Info du véhicule
        vehicle_serializer = VehicleSerializer(vehicle, context=context)

        # Historique des trajets (20 derniers)
        trips = vehicle.trips.all().order_by('-start_time')[:20]
        from apps.fleet.serializers import TripSerializer
        trips_serializer = TripSerializer(trips, many=True, context=context)

        # Historique de maintenance (20 derniers)
        maintenance = vehicle.maintenance_records.all().order_by('-scheduled_date')[:20]
        from apps.fleet.serializers import MaintenanceRecordSerializer
        maintenance_serializer = MaintenanceRecordSerializer(maintenance, many=True, context=context)

        # Conducteur actuel
        driver = vehicle.current_driver.first()
        driver_data = None
        if driver:
            from apps.fleet.serializers import DriverSerializer
            driver_data = DriverSerializer(driver, context=context).data

        return Response({
            'vehicle': vehicle_serializer.data,
            'trips': trips_serializer.data,
            'maintenance': maintenance_serializer.data,
            'current_driver': driver_data,
        })

    @action(detail=True, methods=['post'])
    def assign_driver(self, request, pk=None):
        """Assigner un chauffeur à un véhicule"""
        vehicle = self.get_object()
        driver_id = request.data.get('driver_id')

        if not driver_id:
            return Response(
                {'error': 'driver_id requis'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from apps.fleet.models import Driver
        try:
            driver = Driver.objects.get(id=driver_id)
            if not driver.is_available:
                return Response(
                    {'error': 'Le chauffeur n\'est pas disponible'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            driver.current_vehicle = vehicle
            driver.save()

            return Response({'message': 'Chauffeur assigné avec succès'})
        except Driver.DoesNotExist:
            return Response(
                {'error': 'Chauffeur non trouvé'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=['post'])
    def unassign_driver(self, request, pk=None):
        """Retirer le chauffeur assigné à un véhicule"""
        vehicle = self.get_object()
        driver = vehicle.current_driver.first()

        if not driver:
            return Response(
                {'error': 'Aucun chauffeur assigné à ce véhicule'},
                status=status.HTTP_400_BAD_REQUEST
            )

        driver.current_vehicle = None
        driver.save()

        return Response({'message': 'Chauffeur retiré avec succès'})

    @action(detail=True, methods=['post'])
    def change_status(self, request, pk=None):
        """Changer le statut d'un véhicule"""
        vehicle = self.get_object()
        new_status = request.data.get('status')

        if not new_status:
            return Response(
                {'error': 'status requis'},
                status=status.HTTP_400_BAD_REQUEST
            )

        valid_statuses = ['available', 'in_use', 'maintenance', 'out_of_service']
        if new_status not in valid_statuses:
            return Response(
                {'error': f'Statut invalide. Valeurs possibles: {", ".join(valid_statuses)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        vehicle.status = new_status
        vehicle.save()

        serializer = VehicleSerializer(vehicle)
        return Response(serializer.data)
