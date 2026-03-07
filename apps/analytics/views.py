from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import generics
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta

from apps.fleet.models import Vehicle, Driver, Mission, Incident, Activity
from apps.fleet.serializers import ActivitySerializer
from apps.fleet.services import DriverPerformanceService


class DashboardStatsView(APIView):
    """
    Vue pour les statistiques du tableau de bord
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        org = user.organization

        # Filtrer par organisation si l'utilisateur en a une
        vehicle_qs = Vehicle.objects.all()
        driver_qs = Driver.objects.all()
        mission_qs = Mission.objects.all()
        incident_qs = Incident.objects.all()

        if org:
            vehicle_qs = vehicle_qs.filter(organization=org)
            driver_qs = driver_qs.filter(organization=org)
            mission_qs = mission_qs.filter(organization=org)
            incident_qs = incident_qs.filter(organization=org)

        # === Statistiques véhicules ===
        vehicles_by_status = vehicle_qs.values('status').annotate(
            count=Count('id')
        )
        vehicle_stats = {
            'total': vehicle_qs.count(),
            'available': 0,
            'in_use': 0,
            'maintenance': 0,
            'out_of_service': 0,
        }
        for item in vehicles_by_status:
            if item['status'] in vehicle_stats:
                vehicle_stats[item['status']] = item['count']

        # === Statistiques chauffeurs ===
        drivers_by_status = driver_qs.values('status').annotate(
            count=Count('id')
        )
        driver_stats = {
            'total': driver_qs.count(),
            'available': 0,
            'on_mission': 0,
            'on_break': 0,
            'off_duty': 0,
        }
        for item in drivers_by_status:
            if item['status'] in driver_stats:
                driver_stats[item['status']] = item['count']

        # Chauffeurs actifs = en mission ou disponibles
        driver_stats['active'] = driver_stats['available'] + driver_stats['on_mission']

        # === Statistiques missions ===
        missions_by_status = mission_qs.values('status').annotate(
            count=Count('id')
        )
        mission_stats = {
            'total': mission_qs.count(),
            'pending': 0,
            'assigned': 0,
            'in_progress': 0,
            'completed': 0,
            'cancelled': 0,
        }
        for item in missions_by_status:
            if item['status'] in mission_stats:
                mission_stats[item['status']] = item['count']

        # Missions du jour
        today = timezone.now().date()
        mission_stats['today'] = mission_qs.filter(
            scheduled_start__date=today
        ).count()

        # Missions de la semaine
        week_start = today - timedelta(days=today.weekday())
        mission_stats['this_week'] = mission_qs.filter(
            scheduled_start__date__gte=week_start
        ).count()

        # === Alertes/Incidents ===
        # Incidents non résolus
        unresolved_incidents = incident_qs.filter(is_resolved=False)

        # Par gravité
        incidents_by_severity = unresolved_incidents.values('severity').annotate(
            count=Count('id')
        )
        alert_stats = {
            'total_unresolved': unresolved_incidents.count(),
            'minor': 0,
            'moderate': 0,
            'major': 0,
            'critical': 0,
        }
        for item in incidents_by_severity:
            if item['severity'] in alert_stats:
                alert_stats[item['severity']] = item['count']

        # Incidents récents (dernières 24h)
        yesterday = timezone.now() - timedelta(hours=24)
        recent_incidents = incident_qs.filter(
            reported_at__gte=yesterday
        ).order_by('-reported_at')[:5]

        recent_alerts = []
        for incident in recent_incidents:
            recent_alerts.append({
                'id': incident.id,
                'type': incident.incident_type,
                'type_display': incident.get_incident_type_display(),
                'severity': incident.severity,
                'severity_display': incident.get_severity_display(),
                'title': incident.title,
                'vehicle': incident.vehicle.license_plate if incident.vehicle else None,
                'driver': incident.driver.user.get_full_name() if incident.driver else None,
                'reported_at': incident.reported_at.isoformat(),
                'is_resolved': incident.is_resolved,
            })

        # === Top chauffeurs ===
        top_drivers = driver_qs.order_by('-rating', '-total_trips')[:4]
        top_drivers_data = []
        for driver in top_drivers:
            top_drivers_data.append({
                'id': driver.id,
                'name': driver.user.get_full_name(),
                'initials': ''.join([n[0].upper() for n in driver.user.get_full_name().split()[:2]]),
                'trips': driver.total_trips,
                'rating': float(driver.rating),
            })

        return Response({
            'vehicles': vehicle_stats,
            'drivers': driver_stats,
            'missions': mission_stats,
            'alerts': alert_stats,
            'recent_alerts': recent_alerts,
            'top_drivers': top_drivers_data,
        })


class ActivityListView(generics.ListAPIView):
    """
    Liste des activités récentes

    Paramètres de requête:
    - type: Filtrer par type d'activité (mission_started, incident_reported, etc.)
    - severity: Filtrer par sévérité (info, warning, success, error)
    - limit: Nombre d'activités à retourner (défaut: 20, max: 100)
    - since: Activités depuis cette date (format ISO)
    """
    permission_classes = [IsAuthenticated]
    serializer_class = ActivitySerializer

    def get_queryset(self):
        user = self.request.user
        org = user.organization

        queryset = Activity.objects.all()

        # Filtrer par organisation
        if org:
            queryset = queryset.filter(organization=org)

        # Filtrer par type
        activity_type = self.request.query_params.get('type')
        if activity_type:
            queryset = queryset.filter(activity_type=activity_type)

        # Filtrer par sévérité
        severity = self.request.query_params.get('severity')
        if severity:
            queryset = queryset.filter(severity=severity)

        # Filtrer par date
        since = self.request.query_params.get('since')
        if since:
            try:
                from django.utils.dateparse import parse_datetime
                since_date = parse_datetime(since)
                if since_date:
                    queryset = queryset.filter(created_at__gte=since_date)
            except (ValueError, TypeError):
                pass

        # Limiter les résultats
        limit = self.request.query_params.get('limit', 20)
        try:
            limit = min(int(limit), 100)
        except (ValueError, TypeError):
            limit = 20

        return queryset.order_by('-created_at')[:limit]


class ActivityTypesView(APIView):
    """
    Liste des types d'activités disponibles
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            'types': [
                {'value': choice[0], 'label': choice[1]}
                for choice in Activity.ACTIVITY_TYPES
            ],
            'severities': [
                {'value': choice[0], 'label': choice[1]}
                for choice in Activity.SEVERITY_CHOICES
            ],
        })


class DriverRankingView(APIView):
    """
    Classement des chauffeurs par performance

    Paramètres de requête:
    - limit: Nombre de chauffeurs à retourner (défaut: 10, max: 50)
    - period: Période en jours pour les calculs (défaut: 30)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        org = user.organization

        # Paramètres
        try:
            limit = min(int(request.query_params.get('limit', 10)), 50)
        except (ValueError, TypeError):
            limit = 10

        try:
            period = min(int(request.query_params.get('period', 30)), 365)
        except (ValueError, TypeError):
            period = 30

        # Récupérer le classement
        rankings = DriverPerformanceService.get_rankings(
            organization=org,
            limit=limit,
            period_days=period
        )

        return Response({
            'period_days': period,
            'total_drivers': len(rankings),
            'rankings': rankings,
        })


class TopPerformersView(APIView):
    """
    Top 5 des meilleurs chauffeurs (version simplifiée pour le dashboard)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        org = user.organization

        try:
            limit = min(int(request.query_params.get('limit', 5)), 10)
        except (ValueError, TypeError):
            limit = 5

        top_performers = DriverPerformanceService.get_top_performers(
            organization=org,
            limit=limit
        )

        return Response({
            'top_performers': top_performers,
        })


class DriverPerformanceDetailView(APIView):
    """
    Détails de performance d'un chauffeur spécifique
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, driver_id):
        user = request.user
        org = user.organization

        try:
            driver = Driver.objects.get(pk=driver_id)

            # Vérifier l'organisation
            if org and driver.organization != org:
                return Response(
                    {'error': 'Chauffeur non trouvé'},
                    status=404
                )

            try:
                period = min(int(request.query_params.get('period', 30)), 365)
            except (ValueError, TypeError):
                period = 30

            metrics = DriverPerformanceService.calculate_metrics(driver, period)

            return Response({
                'period_days': period,
                'metrics': metrics,
            })

        except Driver.DoesNotExist:
            return Response(
                {'error': 'Chauffeur non trouvé'},
                status=404
            )
