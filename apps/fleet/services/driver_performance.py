"""
Service de calcul des métriques de performance des chauffeurs
"""
from django.db.models import Count, Avg, Sum, Q, F
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from apps.fleet.models import Driver, Mission, Trip, Incident


class DriverPerformanceService:
    """Service pour calculer les métriques de performance des chauffeurs"""

    @staticmethod
    def calculate_metrics(driver: Driver, period_days: int = 30) -> dict:
        """
        Calcule les métriques de performance pour un chauffeur

        Args:
            driver: Instance du chauffeur
            period_days: Période en jours pour les calculs (défaut: 30)

        Returns:
            Dictionnaire avec les métriques de performance
        """
        since_date = timezone.now() - timedelta(days=period_days)

        # Missions du chauffeur
        missions = Mission.objects.filter(driver=driver)
        recent_missions = missions.filter(created_at__gte=since_date)

        # Trajets du chauffeur
        trips = Trip.objects.filter(driver=driver)
        recent_trips = trips.filter(created_at__gte=since_date)

        # Incidents du chauffeur
        incidents = Incident.objects.filter(driver=driver)
        recent_incidents = incidents.filter(reported_at__gte=since_date)

        # === Métriques de base ===
        total_missions = missions.count()
        total_missions_period = recent_missions.count()
        completed_missions = missions.filter(status='completed').count()
        completed_missions_period = recent_missions.filter(status='completed').count()

        # === Taux de complétion ===
        completion_rate = 0
        if total_missions > 0:
            completion_rate = round((completed_missions / total_missions) * 100, 1)

        completion_rate_period = 0
        if total_missions_period > 0:
            completion_rate_period = round((completed_missions_period / total_missions_period) * 100, 1)

        # === Ponctualité (missions terminées dans les délais) ===
        on_time_missions = missions.filter(
            status='completed',
            actual_end__lte=F('scheduled_end')
        ).count()

        punctuality_rate = 0
        if completed_missions > 0:
            punctuality_rate = round((on_time_missions / completed_missions) * 100, 1)

        # === Distance et vitesse ===
        trip_stats = recent_trips.filter(status='completed').aggregate(
            total_distance=Sum('total_distance'),
            avg_speed=Avg('average_speed'),
            total_duration=Sum('total_duration_minutes'),
            total_fuel=Sum('fuel_consumed'),
        )

        total_distance_period = float(trip_stats['total_distance'] or 0)
        avg_speed = float(trip_stats['avg_speed'] or 0)
        total_duration_hours = (trip_stats['total_duration'] or 0) / 60

        # === Consommation carburant ===
        fuel_efficiency = 0
        if total_distance_period > 0 and trip_stats['total_fuel']:
            # L/100km
            fuel_efficiency = round((float(trip_stats['total_fuel']) / total_distance_period) * 100, 2)

        # === Taux d'incidents ===
        total_incidents = incidents.count()
        incidents_period = recent_incidents.count()

        incident_rate = 0
        if total_missions > 0:
            incident_rate = round((total_incidents / total_missions) * 100, 1)

        incident_rate_period = 0
        if total_missions_period > 0:
            incident_rate_period = round((incidents_period / total_missions_period) * 100, 1)

        # === Score de performance global ===
        # Pondération:
        # - Note client: 30%
        # - Taux de complétion: 25%
        # - Ponctualité: 25%
        # - Sécurité (inverse du taux d'incidents): 20%

        rating_score = float(driver.rating) * 20  # Max 100 (5 * 20)
        completion_score = completion_rate
        punctuality_score = punctuality_rate
        safety_score = max(0, 100 - (incident_rate * 10))  # Pénalité pour incidents

        performance_score = round(
            (rating_score * 0.30) +
            (completion_score * 0.25) +
            (punctuality_score * 0.25) +
            (safety_score * 0.20),
            1
        )

        return {
            # Identité
            'driver_id': driver.id,
            'name': driver.user.get_full_name(),
            'employee_id': driver.employee_id,
            'status': driver.status,

            # Métriques globales
            'rating': float(driver.rating),
            'total_trips': driver.total_trips,
            'total_distance': float(driver.total_distance),
            'total_missions': total_missions,
            'completed_missions': completed_missions,

            # Métriques période
            'missions_period': total_missions_period,
            'completed_missions_period': completed_missions_period,
            'distance_period': round(total_distance_period, 2),
            'hours_driven_period': round(total_duration_hours, 1),
            'incidents_period': incidents_period,

            # Taux
            'completion_rate': completion_rate,
            'completion_rate_period': completion_rate_period,
            'punctuality_rate': punctuality_rate,
            'incident_rate': incident_rate,
            'incident_rate_period': incident_rate_period,

            # Performance
            'avg_speed': round(avg_speed, 1),
            'fuel_efficiency': fuel_efficiency,
            'performance_score': performance_score,
        }

    @classmethod
    def get_rankings(cls, organization=None, limit: int = 10, period_days: int = 30) -> list:
        """
        Récupère le classement des chauffeurs par performance

        Args:
            organization: Organisation pour filtrer (optionnel)
            limit: Nombre maximum de chauffeurs à retourner
            period_days: Période pour les calculs

        Returns:
            Liste des chauffeurs triés par score de performance
        """
        drivers = Driver.objects.select_related('user').all()

        if organization:
            drivers = drivers.filter(organization=organization)

        # Calculer les métriques pour chaque chauffeur
        rankings = []
        for driver in drivers:
            metrics = cls.calculate_metrics(driver, period_days)
            rankings.append(metrics)

        # Trier par score de performance décroissant
        rankings.sort(key=lambda x: (x['performance_score'], x['rating']), reverse=True)

        # Ajouter le rang
        for i, driver in enumerate(rankings[:limit], 1):
            driver['rank'] = i

        return rankings[:limit]

    @classmethod
    def get_top_performers(cls, organization=None, limit: int = 5) -> list:
        """
        Récupère les top performers avec métriques simplifiées

        Args:
            organization: Organisation pour filtrer
            limit: Nombre de top performers

        Returns:
            Liste des top performers
        """
        rankings = cls.get_rankings(organization, limit=limit, period_days=30)

        # Simplifier pour l'affichage
        top_performers = []
        for driver in rankings:
            top_performers.append({
                'rank': driver['rank'],
                'driver_id': driver['driver_id'],
                'name': driver['name'],
                'initials': ''.join([n[0].upper() for n in driver['name'].split()[:2]]),
                'rating': driver['rating'],
                'performance_score': driver['performance_score'],
                'total_trips': driver['total_trips'],
                'completion_rate': driver['completion_rate'],
                'punctuality_rate': driver['punctuality_rate'],
                'distance_period': driver['distance_period'],
                'status': driver['status'],
            })

        return top_performers
