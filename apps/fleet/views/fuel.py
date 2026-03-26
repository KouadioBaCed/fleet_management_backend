from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Avg, Q
from django.utils import timezone
from datetime import datetime, timedelta
from apps.fleet.models import FuelRecord
from apps.fleet.serializers import FuelRecordSerializer, FuelRecordCreateSerializer
from apps.fleet.mixins import OrganizationFilterMixin
from apps.accounts.permissions import IsOrganizationMember


class FuelRecordViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    """ViewSet pour gérer les ravitaillements (filtré par organisation)"""
    queryset = FuelRecord.objects.select_related('vehicle', 'driver', 'trip').all()
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def create(self, request, *args, **kwargs):
        """Override create pour logger les erreurs de validation"""
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            print(f"[FUEL CREATE ERROR] Data: {request.data}")
            print(f"[FUEL CREATE ERROR] Errors: {serializer.errors}")
        return super().create(request, *args, **kwargs)

    def get_serializer_class(self):
        if self.action == 'create':
            return FuelRecordCreateSerializer
        return FuelRecordSerializer

    def get_queryset(self):
        """Filtrer par organisation et appliquer les filtres de requête"""
        queryset = super().get_queryset()

        # Filtrer par véhicule
        vehicle_id = self.request.query_params.get('vehicle')
        if vehicle_id:
            queryset = queryset.filter(vehicle_id=vehicle_id)

        # Filtrer par conducteur
        driver_id = self.request.query_params.get('driver')
        if driver_id:
            queryset = queryset.filter(driver_id=driver_id)

        # Filtrer par type de carburant
        fuel_type = self.request.query_params.get('fuel_type')
        if fuel_type and fuel_type != 'all':
            queryset = queryset.filter(fuel_type=fuel_type)

        # Filtrer par date
        start_date = self.request.query_params.get('start_date')
        if start_date:
            queryset = queryset.filter(refuel_date__gte=start_date)

        end_date = self.request.query_params.get('end_date')
        if end_date:
            queryset = queryset.filter(refuel_date__lte=end_date)

        # Recherche textuelle
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(station_name__icontains=search) |
                Q(station_address__icontains=search) |
                Q(vehicle__license_plate__icontains=search) |
                Q(receipt_number__icontains=search)
            )

        # Tri
        ordering = self.request.query_params.get('ordering', '-refuel_date')
        queryset = queryset.order_by(ordering)

        return queryset

    def list(self, request, *args, **kwargs):
        """Liste des ravitaillements avec statistiques"""
        queryset = self.get_queryset()

        # Stats sur le queryset de base (filtré par org)
        base_queryset = super().get_queryset()

        # Aggregate stats
        agg_stats = base_queryset.aggregate(
            total_quantity=Sum('quantity'),
            total_cost=Sum('total_cost'),
            average_consumption=Avg('calculated_consumption'),
            average_unit_price=Avg('unit_price')
        )

        # Stats par type de carburant
        by_fuel_type = {}
        for fuel_type in ['gasoline', 'diesel', 'electric']:
            type_records = base_queryset.filter(fuel_type=fuel_type)
            type_agg = type_records.aggregate(
                total_quantity=Sum('quantity'),
                total_cost=Sum('total_cost')
            )
            by_fuel_type[fuel_type] = {
                'count': type_records.count(),
                'quantity': float(type_agg['total_quantity'] or 0),
                'cost': float(type_agg['total_cost'] or 0),
            }

        # Stats par véhicule (top 10)
        from apps.fleet.models import Vehicle
        by_vehicle = []
        vehicles = Vehicle.objects.filter(organization=request.user.organization)
        for vehicle in vehicles[:10]:
            vehicle_records = base_queryset.filter(vehicle=vehicle)
            vehicle_agg = vehicle_records.aggregate(
                total_quantity=Sum('quantity'),
                total_cost=Sum('total_cost'),
                avg_consumption=Avg('calculated_consumption')
            )
            if vehicle_agg['total_quantity']:
                by_vehicle.append({
                    'vehicle_id': vehicle.id,
                    'vehicle_plate': vehicle.license_plate,
                    'total_quantity': float(vehicle_agg['total_quantity'] or 0),
                    'total_cost': float(vehicle_agg['total_cost'] or 0),
                    'avg_consumption': float(vehicle_agg['avg_consumption'] or 0),
                })

        # Stats mensuelles (6 derniers mois)
        monthly_data = []
        for i in range(5, -1, -1):
            date = timezone.now() - timedelta(days=i * 30)
            month_start = date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if i > 0:
                next_month = (month_start + timedelta(days=32)).replace(day=1)
            else:
                next_month = timezone.now() + timedelta(days=1)

            month_records = base_queryset.filter(
                refuel_date__gte=month_start,
                refuel_date__lt=next_month
            )
            month_agg = month_records.aggregate(
                total_quantity=Sum('quantity'),
                total_cost=Sum('total_cost')
            )
            monthly_data.append({
                'month': month_start.strftime('%B %Y'),
                'quantity': float(month_agg['total_quantity'] or 0),
                'cost': float(month_agg['total_cost'] or 0),
                'records': month_records.count(),
            })

        stats = {
            'total_records': base_queryset.count(),
            'total_quantity': float(agg_stats['total_quantity'] or 0),
            'total_cost': float(agg_stats['total_cost'] or 0),
            'average_consumption': float(agg_stats['average_consumption'] or 0),
            'average_unit_price': float(agg_stats['average_unit_price'] or 0),
            'by_fuel_type': by_fuel_type,
            'by_vehicle': sorted(by_vehicle, key=lambda x: x['total_cost'], reverse=True),
            'monthly_data': monthly_data,
        }

        serializer = FuelRecordSerializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'count': queryset.count(),
            'stats': stats
        })

    def perform_create(self, serializer):
        """Assigner l'organisation"""
        vehicle = serializer.validated_data['vehicle']
        mileage = serializer.validated_data.get('mileage_at_refuel', 0)

        distance = None
        if mileage and float(mileage) > 0:
            last_refuel = FuelRecord.objects.filter(
                vehicle=vehicle,
                is_full_tank=True
            ).order_by('-refuel_date').first()

            if last_refuel and float(mileage) > float(last_refuel.mileage_at_refuel):
                distance = float(mileage) - float(last_refuel.mileage_at_refuel)

            # Mettre à jour le kilométrage du véhicule
            if float(mileage) > float(vehicle.current_mileage):
                vehicle.current_mileage = mileage
                vehicle.save()

        serializer.save(
            organization=self.request.user.organization,
            distance_since_last_refuel=distance
        )

    @action(detail=False, methods=['get'], url_path='vehicle/(?P<vehicle_id>[^/.]+)/stats')
    def vehicle_stats(self, request, vehicle_id=None):
        """Récupérer les statistiques de carburant d'un véhicule de l'organisation"""
        records = self.get_queryset().filter(vehicle_id=vehicle_id)

        stats = records.aggregate(
            total_quantity=Sum('quantity'),
            total_cost=Sum('total_cost'),
            average_consumption=Avg('calculated_consumption')
        )

        return Response({
            'vehicle_id': vehicle_id,
            'total_quantity': float(stats['total_quantity'] or 0),
            'total_cost': float(stats['total_cost'] or 0),
            'average_consumption': float(stats['average_consumption'] or 0),
            'records_count': records.count()
        })

    @action(detail=False, methods=['get'])
    def consumption_report(self, request):
        """Rapport de consommation général de l'organisation"""
        from apps.fleet.models import Vehicle

        # Récupérer uniquement les véhicules de l'organisation
        user = request.user
        if not user.organization:
            return Response([])

        vehicles_consumption = []
        org_vehicles = Vehicle.objects.filter(organization=user.organization)

        for vehicle in org_vehicles:
            records = self.get_queryset().filter(vehicle=vehicle, is_full_tank=True)
            avg_consumption = records.aggregate(Avg('calculated_consumption'))['calculated_consumption__avg']

            if avg_consumption:
                vehicles_consumption.append({
                    'vehicle_id': vehicle.id,
                    'vehicle_plate': vehicle.license_plate,
                    'average_consumption': float(avg_consumption),
                    'expected_consumption': float(vehicle.fuel_consumption),
                    'difference': float(avg_consumption - vehicle.fuel_consumption),
                })

        return Response(vehicles_consumption)

    @action(detail=False, methods=['get'])
    def analytics(self, request):
        """Analyse complète: consommation par véhicule, coût/km, comparaison flotte"""
        from apps.fleet.models import Vehicle
        from django.db.models import Min, Max

        user = request.user
        if not user.organization:
            return Response({'error': 'No organization'}, status=400)

        base_queryset = super().get_queryset()
        org_vehicles = Vehicle.objects.filter(organization=user.organization)

        # 1. Consommation par véhicule avec détails complets
        vehicles_data = []
        fleet_total_distance = 0
        fleet_total_cost = 0
        fleet_total_quantity = 0

        for vehicle in org_vehicles:
            records = base_queryset.filter(vehicle=vehicle).order_by('refuel_date')

            if not records.exists():
                continue

            # Agrégations
            agg = records.aggregate(
                total_quantity=Sum('quantity'),
                total_cost=Sum('total_cost'),
                avg_consumption=Avg('calculated_consumption'),
                avg_unit_price=Avg('unit_price'),
                min_mileage=Min('mileage_at_refuel'),
                max_mileage=Max('mileage_at_refuel'),
                total_distance=Sum('distance_since_last_refuel')
            )

            total_quantity = float(agg['total_quantity'] or 0)
            total_cost = float(agg['total_cost'] or 0)
            avg_consumption = float(agg['avg_consumption'] or 0)

            # Calcul distance parcourue
            min_mileage = float(agg['min_mileage'] or 0)
            max_mileage = float(agg['max_mileage'] or 0)
            total_distance = max_mileage - min_mileage if max_mileage > min_mileage else float(agg['total_distance'] or 0)

            # Coût par kilomètre
            cost_per_km = total_cost / total_distance if total_distance > 0 else 0

            # Efficacité vs consommation attendue
            expected_consumption = float(vehicle.fuel_consumption) if vehicle.fuel_consumption else 0
            efficiency_ratio = (expected_consumption / avg_consumption * 100) if avg_consumption > 0 else 100
            consumption_diff = avg_consumption - expected_consumption if expected_consumption > 0 else 0

            # Tendance mensuelle (3 derniers mois)
            monthly_trend = []
            for i in range(2, -1, -1):
                date = timezone.now() - timedelta(days=i * 30)
                month_start = date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                if i > 0:
                    next_month = (month_start + timedelta(days=32)).replace(day=1)
                else:
                    next_month = timezone.now() + timedelta(days=1)

                month_records = records.filter(
                    refuel_date__gte=month_start,
                    refuel_date__lt=next_month,
                    is_full_tank=True
                )
                month_avg = month_records.aggregate(Avg('calculated_consumption'))['calculated_consumption__avg']
                monthly_trend.append({
                    'month': month_start.strftime('%b'),
                    'consumption': float(month_avg) if month_avg else None,
                })

            vehicles_data.append({
                'vehicle_id': vehicle.id,
                'vehicle_plate': vehicle.license_plate,
                'vehicle_brand': vehicle.brand,
                'vehicle_model': vehicle.model,
                'vehicle_type': vehicle.vehicle_type,
                'fuel_type': vehicle.fuel_type,
                'fuel_type_display': vehicle.get_fuel_type_display(),
                'total_quantity': total_quantity,
                'total_cost': total_cost,
                'total_distance': total_distance,
                'refuel_count': records.count(),
                'avg_consumption': avg_consumption,
                'expected_consumption': expected_consumption,
                'consumption_diff': consumption_diff,
                'efficiency_ratio': efficiency_ratio,
                'cost_per_km': cost_per_km,
                'avg_unit_price': float(agg['avg_unit_price'] or 0),
                'monthly_trend': monthly_trend,
                'status': 'efficient' if efficiency_ratio >= 100 else ('warning' if efficiency_ratio >= 85 else 'critical'),
            })

            fleet_total_distance += total_distance
            fleet_total_cost += total_cost
            fleet_total_quantity += total_quantity

        # Trier par consommation (plus efficace en premier)
        vehicles_data.sort(key=lambda x: x['avg_consumption'] if x['avg_consumption'] > 0 else 999)

        # 2. Statistiques globales de la flotte
        fleet_avg_consumption = sum(v['avg_consumption'] for v in vehicles_data if v['avg_consumption'] > 0) / len([v for v in vehicles_data if v['avg_consumption'] > 0]) if vehicles_data else 0
        fleet_cost_per_km = fleet_total_cost / fleet_total_distance if fleet_total_distance > 0 else 0

        # 3. Comparaison et classement
        efficient_count = len([v for v in vehicles_data if v['status'] == 'efficient'])
        warning_count = len([v for v in vehicles_data if v['status'] == 'warning'])
        critical_count = len([v for v in vehicles_data if v['status'] == 'critical'])

        # Top/Bottom performers
        sorted_by_efficiency = sorted([v for v in vehicles_data if v['avg_consumption'] > 0], key=lambda x: x['efficiency_ratio'], reverse=True)
        top_performers = sorted_by_efficiency[:3] if len(sorted_by_efficiency) >= 3 else sorted_by_efficiency
        bottom_performers = sorted_by_efficiency[-3:] if len(sorted_by_efficiency) >= 3 else []

        # Distribution par type de véhicule
        by_vehicle_type = {}
        for v in vehicles_data:
            vtype = v['vehicle_type']
            if vtype not in by_vehicle_type:
                by_vehicle_type[vtype] = {
                    'count': 0,
                    'total_cost': 0,
                    'total_distance': 0,
                    'avg_consumption': [],
                }
            by_vehicle_type[vtype]['count'] += 1
            by_vehicle_type[vtype]['total_cost'] += v['total_cost']
            by_vehicle_type[vtype]['total_distance'] += v['total_distance']
            if v['avg_consumption'] > 0:
                by_vehicle_type[vtype]['avg_consumption'].append(v['avg_consumption'])

        for vtype in by_vehicle_type:
            consumptions = by_vehicle_type[vtype]['avg_consumption']
            by_vehicle_type[vtype]['avg_consumption'] = sum(consumptions) / len(consumptions) if consumptions else 0
            by_vehicle_type[vtype]['cost_per_km'] = by_vehicle_type[vtype]['total_cost'] / by_vehicle_type[vtype]['total_distance'] if by_vehicle_type[vtype]['total_distance'] > 0 else 0

        # Distribution par type de carburant
        by_fuel_type = {}
        for v in vehicles_data:
            ftype = v['fuel_type']
            if ftype not in by_fuel_type:
                by_fuel_type[ftype] = {
                    'label': v['fuel_type_display'],
                    'count': 0,
                    'total_cost': 0,
                    'total_quantity': 0,
                    'total_distance': 0,
                    'avg_consumption': [],
                }
            by_fuel_type[ftype]['count'] += 1
            by_fuel_type[ftype]['total_cost'] += v['total_cost']
            by_fuel_type[ftype]['total_quantity'] += v['total_quantity']
            by_fuel_type[ftype]['total_distance'] += v['total_distance']
            if v['avg_consumption'] > 0:
                by_fuel_type[ftype]['avg_consumption'].append(v['avg_consumption'])

        for ftype in by_fuel_type:
            consumptions = by_fuel_type[ftype]['avg_consumption']
            by_fuel_type[ftype]['avg_consumption'] = sum(consumptions) / len(consumptions) if consumptions else 0
            by_fuel_type[ftype]['cost_per_km'] = by_fuel_type[ftype]['total_cost'] / by_fuel_type[ftype]['total_distance'] if by_fuel_type[ftype]['total_distance'] > 0 else 0

        return Response({
            'vehicles': vehicles_data,
            'fleet_summary': {
                'total_vehicles': len(vehicles_data),
                'total_distance': fleet_total_distance,
                'total_cost': fleet_total_cost,
                'total_quantity': fleet_total_quantity,
                'avg_consumption': fleet_avg_consumption,
                'cost_per_km': fleet_cost_per_km,
                'efficiency_distribution': {
                    'efficient': efficient_count,
                    'warning': warning_count,
                    'critical': critical_count,
                },
            },
            'comparison': {
                'top_performers': top_performers,
                'bottom_performers': bottom_performers,
                'by_vehicle_type': by_vehicle_type,
                'by_fuel_type': by_fuel_type,
            },
        })
