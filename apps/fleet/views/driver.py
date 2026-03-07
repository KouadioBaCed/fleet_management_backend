from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Count, Sum, Avg, F
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from apps.fleet.models import Driver
from apps.fleet.serializers import (
    DriverSerializer,
    DriverListSerializer,
    DriverCreateSerializer
)
from apps.fleet.mixins import OrganizationFilterMixin
from apps.accounts.permissions import IsOrganizationMember


def get_analytics_date_range(period, start_date=None, end_date=None):
    """Calcule la plage de dates selon la période sélectionnée"""
    from datetime import datetime
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


def get_previous_analytics_period(start_date, end_date):
    """Calcule la période précédente pour comparaison"""
    delta = end_date - start_date
    prev_end = start_date - timedelta(days=1)
    prev_start = prev_end - delta
    return prev_start, prev_end


class DriverViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    """
    ViewSet pour gérer les chauffeurs (filtré par organisation)

    Paramètres de requête pour list():
    - status: Filtrer par statut (available, on_mission, on_break, off_duty)
    - search: Recherche par nom, prénom, employee_id ou numéro de permis
    - ordering: Tri (full_name, employee_id, rating, total_trips, -created_at, etc.)
    """
    queryset = Driver.objects.select_related('user', 'current_vehicle').all()
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get_serializer_context(self):
        """Ajouter l'organisation au contexte du serializer"""
        context = super().get_serializer_context()
        if self.request.user.is_authenticated and self.request.user.organization:
            context['organization'] = self.request.user.organization
        return context

    def get_serializer_class(self):
        if self.action == 'list':
            return DriverListSerializer
        elif self.action == 'create':
            return DriverCreateSerializer
        return DriverSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filtrer par statut
        status_filter = self.request.query_params.get('status')
        if status_filter and status_filter in ['available', 'on_mission', 'on_break', 'off_duty']:
            queryset = queryset.filter(status=status_filter)

        # Recherche par nom, prénom, employee_id ou numéro de permis
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(employee_id__icontains=search) |
                Q(driver_license_number__icontains=search)
            )

        # Tri
        ordering = self.request.query_params.get('ordering', '-created_at')
        allowed_ordering = [
            'employee_id', '-employee_id',
            'rating', '-rating',
            'total_trips', '-total_trips',
            'total_distance', '-total_distance',
            'created_at', '-created_at',
            'hire_date', '-hire_date',
        ]
        if ordering in allowed_ordering:
            queryset = queryset.order_by(ordering)
        elif ordering == 'full_name':
            queryset = queryset.order_by('user__first_name', 'user__last_name')
        elif ordering == '-full_name':
            queryset = queryset.order_by('-user__first_name', '-user__last_name')

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
            'on_mission': 0,
            'on_break': 0,
            'off_duty': 0,
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
    def me(self, request):
        """Récupérer le profil du chauffeur connecté"""
        try:
            driver = Driver.objects.select_related('user', 'current_vehicle').get(user=request.user)
            serializer = DriverSerializer(driver, context=self.get_serializer_context())
            return Response(serializer.data)
        except Driver.DoesNotExist:
            return Response(
                {'detail': 'Profil chauffeur non trouvé pour cet utilisateur.'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Récupérer les statistiques globales des chauffeurs"""
        queryset = super().get_queryset()
        stats = queryset.values('status').annotate(count=Count('id'))

        result = {
            'total': queryset.count(),
            'by_status': {
                'available': 0,
                'on_mission': 0,
                'on_break': 0,
                'off_duty': 0,
            },
        }

        for stat in stats:
            if stat['status'] in result['by_status']:
                result['by_status'][stat['status']] = stat['count']

        return Response(result)

    @action(detail=False, methods=['get'])
    def available(self, request):
        """Récupérer tous les chauffeurs disponibles de l'organisation"""
        drivers = self.get_queryset().filter(status='available')
        serializer = DriverListSerializer(drivers, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        """Récupérer les statistiques d'un chauffeur"""
        driver = self.get_object()
        stats = {
            'total_trips': driver.total_trips,
            'total_distance': float(driver.total_distance),
            'rating': float(driver.rating),
            'status': driver.status,
            'current_vehicle': driver.current_vehicle.license_plate if driver.current_vehicle else None,
        }
        return Response(stats)

    @action(detail=True, methods=['post'])
    def toggle_status(self, request, pk=None):
        """Changer le statut du chauffeur"""
        driver = self.get_object()
        new_status = request.data.get('status')

        if new_status not in dict(Driver.STATUS_CHOICES):
            return Response(
                {'error': 'Statut invalide'},
                status=status.HTTP_400_BAD_REQUEST
            )

        driver.status = new_status
        driver.save()

        return Response({
            'message': 'Statut mis à jour',
            'status': driver.status
        })

    @action(detail=True, methods=['get'])
    def incidents(self, request, pk=None):
        """Récupérer l'historique des incidents d'un chauffeur"""
        from apps.fleet.models import Incident
        from apps.fleet.serializers import IncidentSerializer

        driver = self.get_object()
        incidents = Incident.objects.filter(driver=driver).order_by('-reported_at')

        # Filtrer par résolution
        is_resolved = request.query_params.get('is_resolved')
        if is_resolved is not None:
            incidents = incidents.filter(is_resolved=is_resolved.lower() == 'true')

        # Filtrer par gravité
        severity = request.query_params.get('severity')
        if severity and severity in ['minor', 'moderate', 'major', 'critical']:
            incidents = incidents.filter(severity=severity)

        # Limiter les résultats (par défaut 20)
        limit = request.query_params.get('limit', 20)
        try:
            limit = int(limit)
        except ValueError:
            limit = 20
        incidents = incidents[:limit]

        serializer = IncidentSerializer(incidents, many=True)

        # Calculer les stats des incidents
        all_incidents = Incident.objects.filter(driver=driver)
        stats = {
            'total': all_incidents.count(),
            'resolved': all_incidents.filter(is_resolved=True).count(),
            'pending': all_incidents.filter(is_resolved=False).count(),
            'by_severity': {
                'minor': all_incidents.filter(severity='minor').count(),
                'moderate': all_incidents.filter(severity='moderate').count(),
                'major': all_incidents.filter(severity='major').count(),
                'critical': all_incidents.filter(severity='critical').count(),
            },
            'by_type': {
                'flat_tire': all_incidents.filter(incident_type='flat_tire').count(),
                'breakdown': all_incidents.filter(incident_type='breakdown').count(),
                'accident': all_incidents.filter(incident_type='accident').count(),
                'fuel_issue': all_incidents.filter(incident_type='fuel_issue').count(),
                'traffic_violation': all_incidents.filter(incident_type='traffic_violation').count(),
                'other': all_incidents.filter(incident_type='other').count(),
            }
        }

        return Response({
            'incidents': serializer.data,
            'stats': stats
        })

    @action(detail=False, methods=['get'])
    def analytics(self, request):
        """
        Analyse complète des conducteurs avec métriques, comparaison et évolution temporelle
        """
        from apps.fleet.models import Trip, Incident, FuelRecord

        # Paramètres
        period = request.query_params.get('period', 'month')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        # Calcul des dates
        date_start, date_end = get_analytics_date_range(period, start_date, end_date)
        prev_start, prev_end = get_previous_analytics_period(date_start, date_end)

        # Base queryset filtré par organisation
        drivers = super().get_queryset()

        # ===== RÉSUMÉ GLOBAL =====
        total_drivers = drivers.count()
        active_drivers = drivers.exclude(status='off_duty').count()
        total_trips = drivers.aggregate(total=Sum('total_trips'))['total'] or 0
        total_distance = drivers.aggregate(total=Sum('total_distance'))['total'] or Decimal('0')
        avg_rating = drivers.aggregate(avg=Avg('rating'))['avg'] or Decimal('0')

        # Trips dans la période
        trips_period = Trip.objects.filter(
            driver__in=drivers,
            created_at__date__gte=date_start,
            created_at__date__lte=date_end
        )
        trips_prev = Trip.objects.filter(
            driver__in=drivers,
            created_at__date__gte=prev_start,
            created_at__date__lte=prev_end
        )

        period_trips_count = trips_period.count()
        prev_trips_count = trips_prev.count()
        trips_change = ((period_trips_count - prev_trips_count) / prev_trips_count * 100) if prev_trips_count else 0

        # Distance dans la période
        period_distance = trips_period.aggregate(total=Sum('total_distance'))['total'] or Decimal('0')
        prev_distance = trips_prev.aggregate(total=Sum('total_distance'))['total'] or Decimal('0')
        distance_change = ((period_distance - prev_distance) / prev_distance * 100) if prev_distance else 0

        # Incidents dans la période
        incidents_period = Incident.objects.filter(
            driver__in=drivers,
            reported_at__date__gte=date_start,
            reported_at__date__lte=date_end
        )
        incidents_prev = Incident.objects.filter(
            driver__in=drivers,
            reported_at__date__gte=prev_start,
            reported_at__date__lte=prev_end
        )

        period_incidents_count = incidents_period.count()
        prev_incidents_count = incidents_prev.count()
        incidents_change = ((period_incidents_count - prev_incidents_count) / prev_incidents_count * 100) if prev_incidents_count else 0

        # ===== MÉTRIQUES PAR CONDUCTEUR =====
        driver_metrics = []
        for driver in drivers:
            driver_trips = trips_period.filter(driver=driver)
            driver_incidents = incidents_period.filter(driver=driver)
            driver_fuel = FuelRecord.objects.filter(
                driver=driver,
                refuel_date__gte=date_start,
                refuel_date__lte=date_end
            )

            trips_count = driver_trips.count()
            distance = driver_trips.aggregate(total=Sum('total_distance'))['total'] or Decimal('0')
            incidents_count = driver_incidents.count()
            fuel_total = driver_fuel.aggregate(total=Sum('total_cost'))['total'] or Decimal('0')
            fuel_liters = driver_fuel.aggregate(total=Sum('quantity'))['total'] or Decimal('0')

            # Calcul efficacité (km/L)
            efficiency = float(distance / fuel_liters) if fuel_liters > 0 else 0

            # Calcul score global (pondéré)
            score = 0
            if trips_count > 0:
                # Base sur trips
                score += min(trips_count * 2, 30)  # Max 30 points pour trips
                # Bonus distance
                score += min(float(distance) / 100, 30)  # Max 30 points pour distance
                # Bonus note
                score += float(driver.rating) * 6  # Max 30 points pour rating
                # Malus incidents
                score -= incidents_count * 5  # -5 points par incident
                score = max(0, min(100, score))  # Clamp 0-100

            driver_metrics.append({
                'id': driver.id,
                'name': f"{driver.user.first_name} {driver.user.last_name}",
                'employee_id': driver.employee_id,
                'photo': driver.user.profile_picture.url if hasattr(driver.user, 'profile_picture') and driver.user.profile_picture else None,
                'status': driver.status,
                'status_display': driver.get_status_display(),
                'trips_count': trips_count,
                'distance': float(distance),
                'incidents_count': incidents_count,
                'incidents_resolved': driver_incidents.filter(is_resolved=True).count(),
                'fuel_cost': float(fuel_total),
                'fuel_liters': float(fuel_liters),
                'efficiency': round(efficiency, 2),
                'rating': float(driver.rating),
                'score': round(score, 1),
                'total_trips': driver.total_trips,
                'total_distance': float(driver.total_distance),
            })

        # Trier par score décroissant
        driver_metrics.sort(key=lambda x: x['score'], reverse=True)

        # Ajouter le rang
        for i, dm in enumerate(driver_metrics):
            dm['rank'] = i + 1

        # ===== COMPARAISON (TOP PERFORMERS) =====
        top_by_trips = sorted(driver_metrics, key=lambda x: x['trips_count'], reverse=True)[:5]
        top_by_distance = sorted(driver_metrics, key=lambda x: x['distance'], reverse=True)[:5]
        top_by_efficiency = sorted([d for d in driver_metrics if d['efficiency'] > 0], key=lambda x: x['efficiency'], reverse=True)[:5]
        top_by_rating = sorted(driver_metrics, key=lambda x: x['rating'], reverse=True)[:5]
        most_incidents = sorted(driver_metrics, key=lambda x: x['incidents_count'], reverse=True)[:5]

        # ===== ÉVOLUTION TEMPORELLE (MENSUELLE) =====
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

            month_trips = Trip.objects.filter(
                driver__in=drivers,
                created_at__date__gte=month_start,
                created_at__date__lte=month_end
            )
            month_incidents = Incident.objects.filter(
                driver__in=drivers,
                reported_at__date__gte=month_start,
                reported_at__date__lte=month_end
            )
            month_fuel = FuelRecord.objects.filter(
                driver__in=drivers,
                refuel_date__gte=month_start,
                refuel_date__lte=month_end
            )

            # Conducteurs actifs ce mois
            active_driver_ids = set(month_trips.values_list('driver_id', flat=True))

            monthly_trends.append({
                'month': month_start.strftime('%Y-%m'),
                'label': month_start.strftime('%b %Y'),
                'trips': month_trips.count(),
                'distance': float(month_trips.aggregate(total=Sum('total_distance'))['total'] or 0),
                'incidents': month_incidents.count(),
                'fuel_cost': float(month_fuel.aggregate(total=Sum('total_cost'))['total'] or 0),
                'active_drivers': len(active_driver_ids),
            })

            # Mois suivant
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1, day=1)
            else:
                current = current.replace(month=current.month + 1, day=1)

        # ===== RÉPARTITION PAR STATUT =====
        status_distribution = []
        status_labels = {
            'available': 'Disponible',
            'on_mission': 'En mission',
            'on_break': 'En pause',
            'off_duty': 'Hors service'
        }
        status_colors = {
            'available': '#6A8A82',
            'on_mission': '#B87333',
            'on_break': '#6B7280',
            'off_duty': '#DC2626'
        }
        for status_key, status_label in status_labels.items():
            count = drivers.filter(status=status_key).count()
            status_distribution.append({
                'status': status_key,
                'label': status_label,
                'color': status_colors[status_key],
                'count': count,
                'percentage': round((count / total_drivers * 100), 1) if total_drivers else 0
            })

        # ===== INCIDENTS PAR CONDUCTEUR (TOP 10) =====
        incidents_by_driver = []
        for dm in sorted(driver_metrics, key=lambda x: x['incidents_count'], reverse=True)[:10]:
            if dm['incidents_count'] > 0:
                driver_incidents_detail = incidents_period.filter(driver_id=dm['id'])
                incidents_by_driver.append({
                    'driver_id': dm['id'],
                    'name': dm['name'],
                    'total': dm['incidents_count'],
                    'resolved': dm['incidents_resolved'],
                    'unresolved': dm['incidents_count'] - dm['incidents_resolved'],
                    'by_severity': {
                        'minor': driver_incidents_detail.filter(severity='minor').count(),
                        'moderate': driver_incidents_detail.filter(severity='moderate').count(),
                        'major': driver_incidents_detail.filter(severity='major').count(),
                        'critical': driver_incidents_detail.filter(severity='critical').count(),
                    }
                })

        return Response({
            'period': {
                'start': date_start.strftime('%Y-%m-%d'),
                'end': date_end.strftime('%Y-%m-%d'),
                'label': period
            },
            'summary': {
                'total_drivers': total_drivers,
                'active_drivers': active_drivers,
                'total_trips': total_trips,
                'total_distance': float(total_distance),
                'avg_rating': round(float(avg_rating), 2),
                'period_trips': period_trips_count,
                'trips_change': round(float(trips_change), 1),
                'period_distance': float(period_distance),
                'distance_change': round(float(distance_change), 1),
                'period_incidents': period_incidents_count,
                'incidents_change': round(float(incidents_change), 1),
            },
            'driver_metrics': driver_metrics,
            'comparison': {
                'top_by_trips': top_by_trips,
                'top_by_distance': top_by_distance,
                'top_by_efficiency': top_by_efficiency,
                'top_by_rating': top_by_rating,
                'most_incidents': most_incidents,
            },
            'monthly_trends': monthly_trends,
            'status_distribution': status_distribution,
            'incidents_by_driver': incidents_by_driver,
        })
