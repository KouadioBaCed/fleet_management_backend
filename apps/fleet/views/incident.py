from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Q, Sum, Avg
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from apps.fleet.models import Incident
from apps.fleet.serializers import IncidentSerializer, IncidentCreateSerializer
from apps.fleet.mixins import OrganizationFilterMixin
from apps.accounts.permissions import IsOrganizationMember


def get_date_range(period, start_date=None, end_date=None):
    """Calcule la plage de dates selon la période sélectionnée"""
    today = timezone.now().date()

    if start_date and end_date:
        return datetime.strptime(start_date, '%Y-%m-%d').date(), datetime.strptime(end_date, '%Y-%m-%d').date()

    if period == 'week':
        return today - timedelta(days=7), today
    elif period == 'month':
        return today.replace(day=1), today
    elif period == 'last_month':
        first_of_month = today.replace(day=1)
        last_month_end = first_of_month - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        return last_month_start, last_month_end
    elif period == '3_months':
        return today - timedelta(days=90), today
    elif period == '6_months':
        return today - timedelta(days=180), today
    elif period == 'year':
        return today.replace(month=1, day=1), today
    else:
        return today.replace(day=1), today


def get_previous_period(start_date, end_date):
    """Calcule la période précédente pour comparaison"""
    delta = end_date - start_date
    prev_end = start_date - timedelta(days=1)
    prev_start = prev_end - delta
    return prev_start, prev_end


class IncidentViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    """ViewSet pour gérer les incidents (filtré par organisation)"""
    queryset = Incident.objects.select_related('trip', 'driver', 'vehicle', 'resolved_by').all()
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get_serializer_class(self):
        if self.action == 'create':
            return IncidentCreateSerializer
        return IncidentSerializer

    def get_queryset(self):
        """Filtrer par organisation et appliquer les filtres de requête"""
        queryset = super().get_queryset()

        # Filtrer par type d'incident
        incident_type = self.request.query_params.get('incident_type')
        if incident_type and incident_type != 'all':
            queryset = queryset.filter(incident_type=incident_type)

        # Filtrer par gravité
        severity = self.request.query_params.get('severity')
        if severity and severity != 'all':
            queryset = queryset.filter(severity=severity)

        # Filtrer par statut de résolution
        is_resolved = self.request.query_params.get('is_resolved')
        if is_resolved is not None:
            if is_resolved.lower() == 'true':
                queryset = queryset.filter(is_resolved=True)
            elif is_resolved.lower() == 'false':
                queryset = queryset.filter(is_resolved=False)

        # Recherche textuelle
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(address__icontains=search) |
                Q(driver__user__first_name__icontains=search) |
                Q(driver__user__last_name__icontains=search) |
                Q(vehicle__license_plate__icontains=search)
            )

        # Tri
        ordering = self.request.query_params.get('ordering', '-reported_at')
        queryset = queryset.order_by(ordering)

        return queryset

    def list(self, request, *args, **kwargs):
        """Liste des incidents avec statistiques"""
        queryset = self.get_queryset()

        # Calculer les stats sur le queryset non paginé (filtré par org)
        base_queryset = super().get_queryset()
        stats = {
            'total': base_queryset.count(),
            'by_severity': {
                'minor': base_queryset.filter(severity='minor').count(),
                'moderate': base_queryset.filter(severity='moderate').count(),
                'major': base_queryset.filter(severity='major').count(),
                'critical': base_queryset.filter(severity='critical').count(),
            },
            'by_type': {
                'flat_tire': base_queryset.filter(incident_type='flat_tire').count(),
                'breakdown': base_queryset.filter(incident_type='breakdown').count(),
                'accident': base_queryset.filter(incident_type='accident').count(),
                'fuel_issue': base_queryset.filter(incident_type='fuel_issue').count(),
                'traffic_violation': base_queryset.filter(incident_type='traffic_violation').count(),
                'other': base_queryset.filter(incident_type='other').count(),
            },
            'by_status': {
                'unresolved': base_queryset.filter(is_resolved=False).count(),
                'resolved': base_queryset.filter(is_resolved=True).count(),
            }
        }

        serializer = IncidentSerializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'count': queryset.count(),
            'stats': stats
        })

    @action(detail=False, methods=['get'])
    def unresolved(self, request):
        """Récupérer tous les incidents non résolus de l'organisation"""
        incidents = self.get_queryset().filter(is_resolved=False).order_by('-reported_at')
        serializer = IncidentSerializer(incidents, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Résoudre un incident avec preuves (facture, coût)"""
        from apps.fleet.models.notification import NotificationService

        incident = self.get_object()

        from django.utils import timezone
        incident.is_resolved = True
        incident.resolved_at = timezone.now()
        incident.resolved_by = request.user
        incident.resolution_notes = request.data.get('resolution_notes', '')
        if request.data.get('estimated_cost'):
            incident.estimated_cost = request.data.get('estimated_cost')
        if request.data.get('repair_cost'):
            incident.repair_cost = request.data.get('repair_cost')
        if request.FILES.get('repair_invoice'):
            incident.repair_invoice = request.FILES['repair_invoice']
        incident.save()

        # Notifier les admins/superviseurs que l'incident a ete resolu
        try:
            NotificationService.notify_incident_resolved(incident)
        except Exception as e:
            print(f"Error sending incident resolved notification: {e}")

        return Response({
            'message': 'Incident résolu',
            'incident': IncidentSerializer(incident).data
        })

    @action(detail=True, methods=['post'])
    def reopen(self, request, pk=None):
        """Rouvrir un incident résolu"""
        incident = self.get_object()

        if not incident.is_resolved:
            return Response(
                {'error': 'Cet incident n\'est pas résolu'},
                status=status.HTTP_400_BAD_REQUEST
            )

        incident.is_resolved = False
        incident.resolved_at = None
        incident.resolved_by = None
        incident.save()

        return Response({
            'message': 'Incident rouvert',
            'incident': IncidentSerializer(incident).data
        })

    @action(detail=False, methods=['get'])
    def analytics(self, request):
        """Analyse des incidents avec période, répartition par type/gravité et coûts"""
        try:
            return self._analytics_data(request)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response(
                {'detail': f'Erreur lors du calcul des analyses: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _analytics_data(self, request):
        # Paramètres
        period = request.query_params.get('period', 'month')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        # Calcul des dates
        date_start, date_end = get_date_range(period, start_date, end_date)
        prev_start, prev_end = get_previous_period(date_start, date_end)

        # Base queryset filtré par organisation
        base_qs = super().get_queryset()

        # Incidents de la période
        incidents_period = base_qs.filter(
            reported_at__date__gte=date_start,
            reported_at__date__lte=date_end
        )
        incidents_prev = base_qs.filter(
            reported_at__date__gte=prev_start,
            reported_at__date__lte=prev_end
        )

        # ===== STATISTIQUES GÉNÉRALES =====
        total_count = incidents_period.count()
        prev_count = incidents_prev.count()
        count_change = ((total_count - prev_count) / prev_count * 100) if prev_count else 0

        resolved_count = incidents_period.filter(is_resolved=True).count()
        unresolved_count = incidents_period.filter(is_resolved=False).count()
        resolution_rate = (resolved_count / total_count * 100) if total_count else 0

        # ===== COÛTS =====
        total_cost = incidents_period.aggregate(total=Sum('estimated_cost'))['total'] or Decimal('0')
        prev_cost = incidents_prev.aggregate(total=Sum('estimated_cost'))['total'] or Decimal('0')
        cost_change = ((total_cost - prev_cost) / prev_cost * 100) if prev_cost else 0

        avg_cost = incidents_period.filter(estimated_cost__isnull=False).aggregate(
            avg=Avg('estimated_cost')
        )['avg'] or Decimal('0')

        # ===== RÉPARTITION PAR TYPE =====
        type_labels = {
            'flat_tire': 'Pneu crevé',
            'breakdown': 'Panne',
            'accident': 'Accident',
            'fuel_issue': 'Problème carburant',
            'traffic_violation': 'Infraction',
            'other': 'Autre'
        }

        by_type = {}
        for type_key, type_label in type_labels.items():
            type_incidents = incidents_period.filter(incident_type=type_key)
            type_count = type_incidents.count()
            type_cost = type_incidents.aggregate(total=Sum('estimated_cost'))['total'] or Decimal('0')
            type_resolved = type_incidents.filter(is_resolved=True).count()

            by_type[type_key] = {
                'label': type_label,
                'count': type_count,
                'percentage': (type_count / total_count * 100) if total_count else 0,
                'cost': float(type_cost),
                'resolved': type_resolved,
                'unresolved': type_count - type_resolved
            }

        # ===== RÉPARTITION PAR GRAVITÉ =====
        severity_labels = {
            'minor': 'Mineur',
            'moderate': 'Modéré',
            'major': 'Majeur',
            'critical': 'Critique'
        }

        severity_colors = {
            'minor': '#6A8A82',
            'moderate': '#6B7280',
            'major': '#B87333',
            'critical': '#DC2626'
        }

        by_severity = {}
        for sev_key, sev_label in severity_labels.items():
            sev_incidents = incidents_period.filter(severity=sev_key)
            sev_count = sev_incidents.count()
            sev_cost = sev_incidents.aggregate(total=Sum('estimated_cost'))['total'] or Decimal('0')
            sev_resolved = sev_incidents.filter(is_resolved=True).count()

            by_severity[sev_key] = {
                'label': sev_label,
                'color': severity_colors[sev_key],
                'count': sev_count,
                'percentage': (sev_count / total_count * 100) if total_count else 0,
                'cost': float(sev_cost),
                'avg_cost': float(sev_cost / sev_count) if sev_count else 0,
                'resolved': sev_resolved,
                'unresolved': sev_count - sev_resolved
            }

        # ===== COÛTS PAR TYPE =====
        costs_by_type = []
        for type_key, type_data in by_type.items():
            if type_data['cost'] > 0:
                costs_by_type.append({
                    'type': type_key,
                    'label': type_data['label'],
                    'cost': type_data['cost'],
                    'count': type_data['count']
                })
        costs_by_type.sort(key=lambda x: x['cost'], reverse=True)

        # ===== TENDANCES MENSUELLES =====
        monthly_trends = []
        current = date_start
        while current <= date_end:
            month_start = current.replace(day=1)
            if current.month == 12:
                month_end = current.replace(year=current.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                month_end = current.replace(month=current.month + 1, day=1) - timedelta(days=1)

            if month_end > date_end:
                month_end = date_end

            month_incidents = incidents_period.filter(
                reported_at__date__gte=month_start,
                reported_at__date__lte=month_end
            )

            month_cost = month_incidents.aggregate(total=Sum('estimated_cost'))['total'] or Decimal('0')

            # Par gravité pour ce mois
            month_by_severity = {}
            for sev_key in severity_labels.keys():
                month_by_severity[sev_key] = month_incidents.filter(severity=sev_key).count()

            monthly_trends.append({
                'month': month_start.strftime('%Y-%m'),
                'label': month_start.strftime('%b %Y'),
                'count': month_incidents.count(),
                'cost': float(month_cost),
                'resolved': month_incidents.filter(is_resolved=True).count(),
                'by_severity': month_by_severity
            })

            # Mois suivant
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1, day=1)
            else:
                current = current.replace(month=current.month + 1, day=1)

        # ===== INCIDENTS RÉCENTS =====
        recent_incidents = []
        for incident in incidents_period.order_by('-reported_at')[:10]:
            recent_incidents.append({
                'id': incident.id,
                'title': incident.title,
                'type': incident.incident_type,
                'type_display': incident.get_incident_type_display(),
                'severity': incident.severity,
                'severity_display': incident.get_severity_display(),
                'vehicle_plate': incident.vehicle.license_plate if incident.vehicle else None,
                'driver_name': incident.driver.full_name if incident.driver else None,
                'cost': float(incident.estimated_cost) if incident.estimated_cost else None,
                'is_resolved': incident.is_resolved,
                'reported_at': incident.reported_at.isoformat()
            })

        # ===== TOP VÉHICULES PAR INCIDENTS =====
        vehicle_incidents = incidents_period.filter(
            vehicle__isnull=False
        ).values(
            'vehicle_id',
            'vehicle__license_plate',
            'vehicle__brand',
            'vehicle__model'
        ).annotate(
            count=Count('id'),
            total_cost=Sum('estimated_cost')
        ).order_by('-count')[:5]

        top_vehicles = [{
            'vehicle_id': v['vehicle_id'],
            'plate': v['vehicle__license_plate'],
            'brand': v['vehicle__brand'],
            'model': v['vehicle__model'],
            'count': v['count'],
            'cost': float(v['total_cost'] or 0)
        } for v in vehicle_incidents]

        # ===== TOP CONDUCTEURS PAR INCIDENTS =====
        driver_incidents = incidents_period.filter(
            driver__isnull=False
        ).values(
            'driver_id',
            'driver__user__first_name',
            'driver__user__last_name'
        ).annotate(
            count=Count('id'),
            total_cost=Sum('estimated_cost')
        ).order_by('-count')[:5]

        top_drivers = [{
            'driver_id': d['driver_id'],
            'name': f"{d['driver__user__first_name']} {d['driver__user__last_name']}",
            'count': d['count'],
            'cost': float(d['total_cost'] or 0)
        } for d in driver_incidents]

        return Response({
            'period': {
                'start': date_start.strftime('%Y-%m-%d'),
                'end': date_end.strftime('%Y-%m-%d'),
                'label': period
            },
            'summary': {
                'total_count': total_count,
                'count_change': round(float(count_change), 1),
                'resolved_count': resolved_count,
                'unresolved_count': unresolved_count,
                'resolution_rate': round(resolution_rate, 1),
                'total_cost': float(total_cost),
                'cost_change': round(float(cost_change), 1),
                'avg_cost': float(avg_cost)
            },
            'by_type': by_type,
            'by_severity': by_severity,
            'costs_by_type': costs_by_type,
            'monthly_trends': monthly_trends,
            'recent_incidents': recent_incidents,
            'top_vehicles': top_vehicles,
            'top_drivers': top_drivers
        })
