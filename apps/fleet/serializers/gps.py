from rest_framework import serializers
from apps.fleet.models import GPSLocationPoint
from math import radians, sin, cos, sqrt, atan2, degrees
from decimal import Decimal


class GPSLocationPointSerializer(serializers.ModelSerializer):
    """Serializer pour point GPS"""

    class Meta:
        model = GPSLocationPoint
        fields = '__all__'

    def validate(self, attrs):
        """Validations"""
        # Verifier que le trajet est actif ou en pause
        trip = attrs.get('trip')
        if trip and trip.status not in ['active', 'paused']:
            raise serializers.ValidationError({
                'trip': 'Le trajet doit etre actif ou en pause pour enregistrer des points GPS.'
            })

        # Valider la latitude
        latitude = attrs.get('latitude')
        if latitude and (latitude < -90 or latitude > 90):
            raise serializers.ValidationError({
                'latitude': 'La latitude doit etre entre -90 et 90.'
            })

        # Valider la longitude
        longitude = attrs.get('longitude')
        if longitude and (longitude < -180 or longitude > 180):
            raise serializers.ValidationError({
                'longitude': 'La longitude doit etre entre -180 et 180.'
            })

        return attrs

    def create(self, validated_data):
        trip = validated_data.get('trip')

        # Calculer la vitesse et le cap si non fournis
        if trip:
            last_point = trip.location_points.order_by('-recorded_at').first()

            if last_point:
                # Calculer la distance
                distance = self._calculate_distance(
                    float(last_point.latitude),
                    float(last_point.longitude),
                    float(validated_data['latitude']),
                    float(validated_data['longitude'])
                )

                # Calculer le temps ecoule
                new_time = validated_data.get('recorded_at')
                if new_time and last_point.recorded_at:
                    time_diff = (new_time - last_point.recorded_at).total_seconds()

                    # Calculer la vitesse si non fournie ou nulle
                    speed = validated_data.get('speed', 0)
                    if (speed is None or speed == 0) and time_diff > 0:
                        # km/h = (km / seconds) * 3600
                        calculated_speed = (distance / time_diff) * 3600
                        validated_data['speed'] = Decimal(str(min(calculated_speed, 300)))  # Max 300 km/h

                # Calculer le cap si non fourni
                heading = validated_data.get('heading')
                if heading is None:
                    calculated_heading = self._calculate_heading(
                        float(last_point.latitude),
                        float(last_point.longitude),
                        float(validated_data['latitude']),
                        float(validated_data['longitude'])
                    )
                    validated_data['heading'] = Decimal(str(calculated_heading))

        # Toujours determiner is_moving depuis la vitesse finale
        final_speed = float(validated_data.get('speed', 0) or 0)
        validated_data['is_moving'] = final_speed > 2

        # Creer le point
        point = super().create(validated_data)

        # Mettre a jour les statistiques du trajet
        if trip:
            self._update_trip_stats(trip)

        return point

    def _calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calcule la distance entre deux points GPS en km (formule Haversine)"""
        R = 6371  # Rayon de la Terre en km

        lat1_rad = radians(lat1)
        lat2_rad = radians(lat2)
        delta_lat = radians(lat2 - lat1)
        delta_lon = radians(lon2 - lon1)

        a = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        return R * c

    def _calculate_heading(self, lat1, lon1, lat2, lon2):
        """Calcule le cap entre deux points GPS en degres"""
        lat1_rad = radians(lat1)
        lat2_rad = radians(lat2)
        delta_lon = radians(lon2 - lon1)

        y = sin(delta_lon) * cos(lat2_rad)
        x = cos(lat1_rad) * sin(lat2_rad) - sin(lat1_rad) * cos(lat2_rad) * cos(delta_lon)

        heading = degrees(atan2(y, x))
        return (heading + 360) % 360  # Normaliser entre 0 et 360

    def _update_trip_stats(self, trip):
        """Met a jour les statistiques du trajet"""
        from django.db.models import Avg, Max, Sum
        from django.utils import timezone

        points = trip.location_points.all()
        points_count = points.count()

        if points_count < 2:
            return

        # Calculer la distance totale
        total_distance = Decimal('0')
        points_list = list(points.order_by('recorded_at'))

        for i in range(1, len(points_list)):
            prev = points_list[i - 1]
            curr = points_list[i]
            distance = self._calculate_distance(
                float(prev.latitude), float(prev.longitude),
                float(curr.latitude), float(curr.longitude)
            )
            total_distance += Decimal(str(distance))

        # Calculer les statistiques de vitesse
        stats = points.aggregate(
            avg_speed=Avg('speed'),
            max_speed=Max('speed')
        )

        # Calculer la duree totale
        first_point = points_list[0]
        last_point = points_list[-1]
        duration_seconds = (last_point.recorded_at - first_point.recorded_at).total_seconds()
        duration_minutes = int(duration_seconds / 60)

        # Mettre a jour le trajet
        trip.total_distance = total_distance
        trip.average_speed = stats['avg_speed'] or Decimal('0')
        trip.max_speed = stats['max_speed'] or Decimal('0')
        trip.total_duration_minutes = duration_minutes - trip.pause_duration_minutes

        trip.save(update_fields=[
            'total_distance', 'average_speed', 'max_speed', 'total_duration_minutes'
        ])


class GPSBatchSerializer(serializers.Serializer):
    """Serializer pour batch de points GPS"""

    points = GPSLocationPointSerializer(many=True)

    def create(self, validated_data):
        points_data = validated_data['points']
        created_points = []

        for point_data in points_data:
            serializer = GPSLocationPointSerializer(data=point_data)
            if serializer.is_valid():
                point = serializer.save()
                created_points.append(point)

        return created_points
