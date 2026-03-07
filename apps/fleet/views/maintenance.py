from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, F
from django.utils import timezone
from datetime import datetime, timedelta
from apps.fleet.models import MaintenanceRecord, Vehicle
from apps.fleet.serializers import MaintenanceRecordSerializer, MaintenanceRecordCreateSerializer
from apps.fleet.mixins import OrganizationFilterMixin
from apps.accounts.permissions import IsOrganizationMember


class MaintenanceRecordViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    """ViewSet pour gérer les maintenances (filtré par organisation)"""
    queryset = MaintenanceRecord.objects.select_related('vehicle', 'created_by').all()
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get_serializer_class(self):
        if self.action == 'create':
            return MaintenanceRecordCreateSerializer
        return MaintenanceRecordSerializer

    def get_queryset(self):
        """Filtrer par organisation et appliquer les filtres de requête"""
        queryset = super().get_queryset()

        # Filtrer par statut
        status_filter = self.request.query_params.get('status')
        if status_filter and status_filter != 'all':
            queryset = queryset.filter(status=status_filter)

        # Filtrer par type
        maintenance_type = self.request.query_params.get('maintenance_type')
        if maintenance_type and maintenance_type != 'all':
            queryset = queryset.filter(maintenance_type=maintenance_type)

        # Filtrer par véhicule
        vehicle_id = self.request.query_params.get('vehicle')
        if vehicle_id:
            queryset = queryset.filter(vehicle_id=vehicle_id)

        # Recherche textuelle
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(description__icontains=search) |
                Q(service_provider__icontains=search) |
                Q(vehicle__license_plate__icontains=search) |
                Q(vehicle__brand__icontains=search)
            )

        # Tri
        ordering = self.request.query_params.get('ordering', '-scheduled_date')
        queryset = queryset.order_by(ordering)

        return queryset

    def list(self, request, *args, **kwargs):
        """Liste des maintenances avec statistiques"""
        queryset = self.get_queryset()

        # Stats sur le queryset de base (filtré par org)
        base_queryset = super().get_queryset()
        stats = {
            'total': base_queryset.count(),
            'by_status': {
                'scheduled': base_queryset.filter(status='scheduled').count(),
                'in_progress': base_queryset.filter(status='in_progress').count(),
                'completed': base_queryset.filter(status='completed').count(),
                'cancelled': base_queryset.filter(status='cancelled').count(),
            },
            'by_type': {
                'oil_change': base_queryset.filter(maintenance_type='oil_change').count(),
                'tire_change': base_queryset.filter(maintenance_type='tire_change').count(),
                'brake_service': base_queryset.filter(maintenance_type='brake_service').count(),
                'inspection': base_queryset.filter(maintenance_type='inspection').count(),
                'repair': base_queryset.filter(maintenance_type='repair').count(),
                'preventive': base_queryset.filter(maintenance_type='preventive').count(),
                'other': base_queryset.filter(maintenance_type='other').count(),
            },
            'this_month_cost': sum(
                m.total_cost for m in base_queryset.filter(
                    scheduled_date__month=timezone.now().month,
                    scheduled_date__year=timezone.now().year
                )
            )
        }

        serializer = MaintenanceRecordSerializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'count': queryset.count(),
            'stats': stats
        })

    def perform_create(self, serializer):
        """Assigner l'organisation et le créateur"""
        serializer.save(
            organization=self.request.user.organization,
            created_by=self.request.user
        )

    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """Récupérer les maintenances à venir de l'organisation"""
        maintenances = self.get_queryset().filter(
            status='scheduled',
            scheduled_date__gte=timezone.now().date()
        ).order_by('scheduled_date')[:10]
        serializer = MaintenanceRecordSerializer(maintenances, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def calendar(self, request):
        """Récupérer les maintenances pour une vue calendrier"""
        # Paramètres de date
        start_date = request.query_params.get('start')
        end_date = request.query_params.get('end')

        if not start_date or not end_date:
            # Par défaut, le mois en cours
            today = timezone.now().date()
            start_date = today.replace(day=1)
            end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        else:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()

        maintenances = self.get_queryset().filter(
            scheduled_date__gte=start_date,
            scheduled_date__lte=end_date
        ).order_by('scheduled_date')

        # Formater pour le calendrier
        events = []
        for m in maintenances:
            events.append({
                'id': m.id,
                'title': f"{m.get_maintenance_type_display()} - {m.vehicle.license_plate}",
                'date': m.scheduled_date.isoformat(),
                'status': m.status,
                'status_display': m.get_status_display(),
                'maintenance_type': m.maintenance_type,
                'maintenance_type_display': m.get_maintenance_type_display(),
                'vehicle_id': m.vehicle.id,
                'vehicle_plate': m.vehicle.license_plate,
                'vehicle_brand': m.vehicle.brand,
                'vehicle_model': m.vehicle.model,
                'description': m.description,
                'service_provider': m.service_provider,
                'total_cost': float(m.total_cost) if m.total_cost else 0,
                'mileage_at_service': float(m.mileage_at_service) if m.mileage_at_service else 0,
            })

        return Response({
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'count': len(events),
            'events': events
        })

    @action(detail=False, methods=['get'])
    def mileage_alerts(self, request):
        """Récupérer les alertes de kilométrage pour maintenances préventives"""
        org = request.user.organization

        # Récupérer les véhicules de l'organisation avec kilométrage proche de la maintenance
        vehicles = Vehicle.objects.filter(organization=org)

        alerts = []
        for vehicle in vehicles:
            if vehicle.next_maintenance_mileage and vehicle.current_mileage:
                remaining = float(vehicle.next_maintenance_mileage) - float(vehicle.current_mileage)
                percentage = (float(vehicle.current_mileage) / float(vehicle.next_maintenance_mileage)) * 100

                # Déterminer la gravité
                if remaining <= 0:
                    severity = 'critical'
                    message = 'Maintenance dépassée'
                elif remaining <= 500:
                    severity = 'warning'
                    message = f'{int(remaining)} km restants'
                elif remaining <= 1000:
                    severity = 'info'
                    message = f'{int(remaining)} km restants'
                else:
                    continue  # Pas d'alerte si plus de 1000km restants

                # Trouver la dernière maintenance
                last_maintenance = MaintenanceRecord.objects.filter(
                    vehicle=vehicle,
                    status='completed'
                ).order_by('-completed_date').first()

                alerts.append({
                    'id': vehicle.id,
                    'vehicle_id': vehicle.id,
                    'vehicle_plate': vehicle.license_plate,
                    'vehicle_brand': vehicle.brand,
                    'vehicle_model': vehicle.model,
                    'current_mileage': float(vehicle.current_mileage),
                    'next_maintenance_mileage': float(vehicle.next_maintenance_mileage),
                    'remaining_km': remaining,
                    'percentage': min(percentage, 100),
                    'severity': severity,
                    'message': message,
                    'last_maintenance_date': last_maintenance.completed_date.isoformat() if last_maintenance and last_maintenance.completed_date else None,
                    'last_maintenance_type': last_maintenance.get_maintenance_type_display() if last_maintenance else None,
                })

        # Trier par gravité puis par km restants
        severity_order = {'critical': 0, 'warning': 1, 'info': 2}
        alerts.sort(key=lambda x: (severity_order.get(x['severity'], 3), x['remaining_km']))

        return Response({
            'count': len(alerts),
            'alerts': alerts
        })

    @action(detail=False, methods=['get'])
    def preventive_schedule(self, request):
        """Récupérer le planning des maintenances préventives"""
        # Récupérer les maintenances préventives planifiées
        preventive = self.get_queryset().filter(
            maintenance_type='preventive',
            status='scheduled'
        ).order_by('scheduled_date')

        # Grouper par mois
        schedule = {}
        for m in preventive:
            month_key = m.scheduled_date.strftime('%Y-%m')
            if month_key not in schedule:
                schedule[month_key] = {
                    'month': m.scheduled_date.strftime('%B %Y'),
                    'count': 0,
                    'total_cost': 0,
                    'maintenances': []
                }
            schedule[month_key]['count'] += 1
            schedule[month_key]['total_cost'] += float(m.total_cost) if m.total_cost else 0
            schedule[month_key]['maintenances'].append({
                'id': m.id,
                'date': m.scheduled_date.isoformat(),
                'vehicle_plate': m.vehicle.license_plate,
                'description': m.description,
                'cost': float(m.total_cost) if m.total_cost else 0,
            })

        return Response({
            'schedule': list(schedule.values())
        })

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Démarrer une maintenance"""
        maintenance = self.get_object()

        if maintenance.status != 'scheduled':
            return Response(
                {'error': 'Cette maintenance ne peut pas être démarrée'},
                status=status.HTTP_400_BAD_REQUEST
            )

        maintenance.status = 'in_progress'
        maintenance.save()

        # Marquer le véhicule en maintenance
        maintenance.vehicle.status = 'maintenance'
        maintenance.vehicle.save()

        return Response({
            'message': 'Maintenance démarrée',
            'maintenance': MaintenanceRecordSerializer(maintenance).data
        })

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Marquer une maintenance comme terminée"""
        maintenance = self.get_object()

        maintenance.status = 'completed'
        maintenance.completed_date = timezone.now().date()
        maintenance.work_performed = request.data.get('work_performed', '')
        maintenance.parts_replaced = request.data.get('parts_replaced', '')

        # Mettre à jour le kilométrage de prochaine maintenance
        if request.data.get('next_service_mileage'):
            maintenance.next_service_mileage = request.data.get('next_service_mileage')
            maintenance.vehicle.next_maintenance_mileage = request.data.get('next_service_mileage')

        # Mettre à jour le kilométrage actuel si fourni
        if request.data.get('current_mileage'):
            maintenance.mileage_at_service = request.data.get('current_mileage')
            maintenance.vehicle.current_mileage = request.data.get('current_mileage')

        maintenance.save()

        # Remettre le véhicule en service
        maintenance.vehicle.status = 'available'
        maintenance.vehicle.last_maintenance_date = timezone.now().date()
        maintenance.vehicle.save()

        return Response({
            'message': 'Maintenance terminée',
            'maintenance': MaintenanceRecordSerializer(maintenance).data
        })

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Annuler une maintenance"""
        maintenance = self.get_object()

        if maintenance.status == 'completed':
            return Response(
                {'error': 'Impossible d\'annuler une maintenance terminée'},
                status=status.HTTP_400_BAD_REQUEST
            )

        maintenance.status = 'cancelled'
        maintenance.notes = request.data.get('reason', '') + '\n' + maintenance.notes
        maintenance.save()

        # Remettre le véhicule disponible si en maintenance
        if maintenance.vehicle.status == 'maintenance':
            maintenance.vehicle.status = 'available'
            maintenance.vehicle.save()

        return Response({
            'message': 'Maintenance annulée',
            'maintenance': MaintenanceRecordSerializer(maintenance).data
        })

    @action(detail=False, methods=['get'])
    def history(self, request):
        """Récupérer l'historique des interventions avec détails pièces et coûts cumulés"""
        # Filtrer par véhicule si spécifié
        vehicle_id = request.query_params.get('vehicle')

        # Récupérer les maintenances terminées
        queryset = self.get_queryset().filter(status='completed').order_by('-completed_date')

        if vehicle_id:
            queryset = queryset.filter(vehicle_id=vehicle_id)

        # Calculer les coûts cumulés
        total_labor_cost = sum(float(m.labor_cost) if m.labor_cost else 0 for m in queryset)
        total_parts_cost = sum(float(m.parts_cost) if m.parts_cost else 0 for m in queryset)
        total_cost = sum(float(m.total_cost) if m.total_cost else 0 for m in queryset)

        # Statistiques par type
        by_type = {}
        for m in queryset:
            type_key = m.maintenance_type
            if type_key not in by_type:
                by_type[type_key] = {
                    'label': m.get_maintenance_type_display(),
                    'count': 0,
                    'total_cost': 0
                }
            by_type[type_key]['count'] += 1
            by_type[type_key]['total_cost'] += float(m.total_cost) if m.total_cost else 0

        # Statistiques par mois (6 derniers mois)
        monthly_costs = {}
        for m in queryset:
            if m.completed_date:
                month_key = m.completed_date.strftime('%Y-%m')
                if month_key not in monthly_costs:
                    monthly_costs[month_key] = {
                        'month': m.completed_date.strftime('%B %Y'),
                        'labor_cost': 0,
                        'parts_cost': 0,
                        'total_cost': 0,
                        'count': 0
                    }
                monthly_costs[month_key]['labor_cost'] += float(m.labor_cost) if m.labor_cost else 0
                monthly_costs[month_key]['parts_cost'] += float(m.parts_cost) if m.parts_cost else 0
                monthly_costs[month_key]['total_cost'] += float(m.total_cost) if m.total_cost else 0
                monthly_costs[month_key]['count'] += 1

        # Trier les mois par date décroissante et prendre les 6 derniers
        sorted_months = sorted(monthly_costs.keys(), reverse=True)[:6]
        monthly_data = [monthly_costs[m] for m in reversed(sorted_months)]

        # Formater les interventions avec détails pièces
        interventions = []
        for m in queryset[:50]:  # Limiter à 50 résultats
            # Parser les pièces remplacées
            parts_list = []
            if m.parts_replaced:
                # Essayer de parser comme liste (séparée par virgules ou retours à la ligne)
                parts_raw = m.parts_replaced.replace('\n', ',').split(',')
                for part in parts_raw:
                    part = part.strip()
                    if part:
                        parts_list.append(part)

            interventions.append({
                'id': m.id,
                'vehicle_id': m.vehicle.id,
                'vehicle_plate': m.vehicle.license_plate,
                'vehicle_brand': m.vehicle.brand,
                'vehicle_model': m.vehicle.model,
                'maintenance_type': m.maintenance_type,
                'maintenance_type_display': m.get_maintenance_type_display(),
                'scheduled_date': m.scheduled_date.isoformat() if m.scheduled_date else None,
                'completed_date': m.completed_date.isoformat() if m.completed_date else None,
                'description': m.description,
                'work_performed': m.work_performed,
                'parts_replaced': parts_list,
                'parts_replaced_raw': m.parts_replaced,
                'service_provider': m.service_provider,
                'technician_name': m.technician_name,
                'labor_cost': float(m.labor_cost) if m.labor_cost else 0,
                'parts_cost': float(m.parts_cost) if m.parts_cost else 0,
                'total_cost': float(m.total_cost) if m.total_cost else 0,
                'mileage_at_service': int(m.mileage_at_service) if m.mileage_at_service else 0,
                'next_service_mileage': int(m.next_service_mileage) if m.next_service_mileage else None,
            })

        return Response({
            'count': queryset.count(),
            'interventions': interventions,
            'cumulative_costs': {
                'labor_cost': total_labor_cost,
                'parts_cost': total_parts_cost,
                'total_cost': total_cost,
            },
            'by_type': list(by_type.values()),
            'monthly_costs': monthly_data
        })
