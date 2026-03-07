from decimal import Decimal
import math
from apps.fleet.models import Trip, GPSLocationPoint
from django.db.models import Avg, Max


class TripCalculator:
    """Service pour calculer les métriques d'un trajet"""

    @staticmethod
    def calculate_distance(lat1, lon1, lat2, lon2):
        """Calculer la distance entre deux points GPS (formule Haversine)"""
        R = 6371  # Rayon de la Terre en km

        lat1_rad = math.radians(float(lat1))
        lat2_rad = math.radians(float(lat2))
        delta_lat = math.radians(float(lat2 - lat1))
        delta_lon = math.radians(float(lon2 - lon1))

        a = (math.sin(delta_lat / 2) ** 2 +
             math.cos(lat1_rad) * math.cos(lat2_rad) *
             math.sin(delta_lon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        distance = R * c
        return Decimal(str(distance))

    @staticmethod
    def calculate_trip_metrics(trip: Trip):
        """Calculer toutes les métriques d'un trajet"""
        points = GPSLocationPoint.objects.filter(trip=trip).order_by('recorded_at')

        if points.count() < 2:
            return None

        # Calculer la distance totale
        total_distance = Decimal('0')
        previous_point = None

        for point in points:
            if previous_point:
                distance = TripCalculator.calculate_distance(
                    previous_point.latitude,
                    previous_point.longitude,
                    point.latitude,
                    point.longitude
                )
                total_distance += distance
            previous_point = point

        # Calculer les vitesses
        avg_speed = points.aggregate(Avg('speed'))['speed__avg'] or 0
        max_speed = points.aggregate(Max('speed'))['speed__max'] or 0

        # Calculer la durée
        if trip.end_time and trip.start_time:
            duration = trip.end_time - trip.start_time
            total_minutes = int(duration.total_seconds() / 60)
        else:
            total_minutes = 0

        # Calculer le carburant consommé (estimation)
        fuel_consumed = Decimal('0')
        if total_distance > 0 and trip.vehicle.fuel_consumption:
            fuel_consumed = (total_distance * trip.vehicle.fuel_consumption) / Decimal('100')

        # Mettre à jour le trajet
        trip.total_distance = total_distance
        trip.average_speed = Decimal(str(avg_speed))
        trip.max_speed = Decimal(str(max_speed))
        trip.total_duration_minutes = total_minutes
        trip.fuel_consumed = fuel_consumed
        trip.save()

        return {
            'total_distance': float(total_distance),
            'average_speed': float(avg_speed),
            'max_speed': float(max_speed),
            'duration_minutes': total_minutes,
            'fuel_consumed': float(fuel_consumed),
        }

    @staticmethod
    def detect_speeding(trip: Trip, speed_limit=120):
        """Détecter les excès de vitesse"""
        speeding_points = GPSLocationPoint.objects.filter(
            trip=trip,
            speed__gt=speed_limit
        ).order_by('recorded_at')

        return [{
            'latitude': float(point.latitude),
            'longitude': float(point.longitude),
            'speed': float(point.speed),
            'timestamp': point.recorded_at.isoformat(),
        } for point in speeding_points]
