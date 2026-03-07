from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Avg, Count, Min, Max, F, Q
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
import csv
from django.http import HttpResponse
from apps.fleet.models import Vehicle, Driver, FuelRecord, MaintenanceRecord, Trip, Incident, Mission
from apps.accounts.permissions import IsOrganizationMember


def get_date_range(period, start_date=None, end_date=None):
    """Calcule la plage de dates selon la période sélectionnée"""
    today = timezone.now().date()

    if start_date and end_date:
        return datetime.strptime(start_date, '%Y-%m-%d').date(), datetime.strptime(end_date, '%Y-%m-%d').date()

    if period == 'today':
        return today, today
    elif period == 'week':
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
        # Default: this month
        return today.replace(day=1), today


def get_previous_period_range(start_date, end_date):
    """Calcule la période précédente pour comparaison"""
    delta = end_date - start_date
    prev_end = start_date - timedelta(days=1)
    prev_start = prev_end - delta
    return prev_start, prev_end


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsOrganizationMember])
def reports_summary(request):
    """Récupère un résumé complet pour les rapports avec filtres"""
    organization = request.user.organization

    # Paramètres
    period = request.query_params.get('period', 'month')
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    vehicle_id = request.query_params.get('vehicle')
    driver_id = request.query_params.get('driver')

    # Calcul des dates
    date_start, date_end = get_date_range(period, start_date, end_date)
    prev_start, prev_end = get_previous_period_range(date_start, date_end)

    # Base querysets filtrés par organisation
    vehicles_qs = Vehicle.objects.filter(organization=organization)
    drivers_qs = Driver.objects.filter(organization=organization)
    fuel_qs = FuelRecord.objects.filter(organization=organization)
    maintenance_qs = MaintenanceRecord.objects.filter(organization=organization)
    trips_qs = Trip.objects.filter(organization=organization)
    incidents_qs = Incident.objects.filter(organization=organization)
    missions_qs = Mission.objects.filter(organization=organization)

    # Appliquer les filtres
    if vehicle_id:
        fuel_qs = fuel_qs.filter(vehicle_id=vehicle_id)
        maintenance_qs = maintenance_qs.filter(vehicle_id=vehicle_id)
        trips_qs = trips_qs.filter(vehicle_id=vehicle_id)
        incidents_qs = incidents_qs.filter(vehicle_id=vehicle_id)

    if driver_id:
        fuel_qs = fuel_qs.filter(driver_id=driver_id)
        trips_qs = trips_qs.filter(driver_id=driver_id)
        incidents_qs = incidents_qs.filter(driver_id=driver_id)
        missions_qs = missions_qs.filter(driver_id=driver_id)

    # Filtrer par période
    fuel_period = fuel_qs.filter(refuel_date__date__gte=date_start, refuel_date__date__lte=date_end)
    fuel_prev = fuel_qs.filter(refuel_date__date__gte=prev_start, refuel_date__date__lte=prev_end)

    maintenance_period = maintenance_qs.filter(scheduled_date__gte=date_start, scheduled_date__lte=date_end)
    maintenance_prev = maintenance_qs.filter(scheduled_date__gte=prev_start, scheduled_date__lte=prev_end)

    trips_period = trips_qs.filter(start_time__date__gte=date_start, start_time__date__lte=date_end)
    trips_prev = trips_qs.filter(start_time__date__gte=prev_start, start_time__date__lte=prev_end)

    incidents_period = incidents_qs.filter(reported_at__date__gte=date_start, reported_at__date__lte=date_end)
    incidents_prev = incidents_qs.filter(reported_at__date__gte=prev_start, reported_at__date__lte=prev_end)

    # ===== STATISTIQUES PRINCIPALES =====

    # Distance totale
    distance_current = trips_period.aggregate(total=Sum('total_distance'))['total'] or Decimal('0')
    distance_prev = trips_prev.aggregate(total=Sum('total_distance'))['total'] or Decimal('0')
    distance_change = ((distance_current - distance_prev) / distance_prev * 100) if distance_prev else 0

    # Carburant total
    fuel_current = fuel_period.aggregate(total=Sum('quantity'))['total'] or Decimal('0')
    fuel_prev = fuel_prev.aggregate(total=Sum('quantity'))['total'] or Decimal('0')
    fuel_change = ((fuel_current - fuel_prev) / fuel_prev * 100) if fuel_prev else 0

    # Coûts carburant
    fuel_cost_current = fuel_period.aggregate(total=Sum('total_cost'))['total'] or Decimal('0')
    fuel_cost_prev_val = fuel_qs.filter(
        refuel_date__date__gte=prev_start,
        refuel_date__date__lte=prev_end
    ).aggregate(total=Sum('total_cost'))['total'] or Decimal('0')
    fuel_cost_change = ((fuel_cost_current - fuel_cost_prev_val) / fuel_cost_prev_val * 100) if fuel_cost_prev_val else 0

    # Coûts maintenance
    maintenance_cost_current = maintenance_period.aggregate(total=Sum('total_cost'))['total'] or Decimal('0')
    maintenance_cost_prev = maintenance_prev.aggregate(total=Sum('total_cost'))['total'] or Decimal('0')
    maintenance_cost_change = ((maintenance_cost_current - maintenance_cost_prev) / maintenance_cost_prev * 100) if maintenance_cost_prev else 0

    # Coûts totaux
    total_cost = fuel_cost_current + maintenance_cost_current
    total_cost_prev = fuel_cost_prev_val + maintenance_cost_prev
    total_cost_change = ((total_cost - total_cost_prev) / total_cost_prev * 100) if total_cost_prev else 0

    # Trajets
    trips_count = trips_period.count()
    trips_prev_count = trips_prev.count()
    trips_change = ((trips_count - trips_prev_count) / trips_prev_count * 100) if trips_prev_count else 0

    # Temps d'utilisation (en heures)
    trips_with_duration = trips_period.exclude(end_time__isnull=True)
    total_hours = sum(
        (t.end_time - t.start_time).total_seconds() / 3600
        for t in trips_with_duration
    )
    trips_prev_duration = trips_prev.exclude(end_time__isnull=True)
    prev_hours = sum(
        (t.end_time - t.start_time).total_seconds() / 3600
        for t in trips_prev_duration
    )
    hours_change = ((total_hours - prev_hours) / prev_hours * 100) if prev_hours else 0

    # Incidents
    incidents_count = incidents_period.count()
    incidents_prev_count = incidents_prev.count()
    incidents_change = ((incidents_count - incidents_prev_count) / incidents_prev_count * 100) if incidents_prev_count else 0

    # Consommation moyenne
    avg_consumption = fuel_period.aggregate(avg=Avg('calculated_consumption'))['avg'] or 0
    avg_consumption_prev = fuel_qs.filter(
        refuel_date__date__gte=prev_start,
        refuel_date__date__lte=prev_end
    ).aggregate(avg=Avg('calculated_consumption'))['avg'] or 0
    consumption_change = ((avg_consumption - avg_consumption_prev) / avg_consumption_prev * 100) if avg_consumption_prev else 0

    # ===== TOP VÉHICULES =====
    top_vehicles = []
    vehicle_stats = trips_period.values('vehicle_id', 'vehicle__license_plate', 'vehicle__brand', 'vehicle__model').annotate(
        trips_count=Count('id'),
        total_distance=Sum('total_distance')
    ).order_by('-total_distance')[:5]

    for vs in vehicle_stats:
        vehicle_fuel = fuel_period.filter(vehicle_id=vs['vehicle_id']).aggregate(
            total_fuel=Sum('quantity'),
            avg_consumption=Avg('calculated_consumption')
        )
        top_vehicles.append({
            'vehicle_id': vs['vehicle_id'],
            'plate': vs['vehicle__license_plate'],
            'brand': vs['vehicle__brand'],
            'model': vs['vehicle__model'],
            'trips': vs['trips_count'],
            'distance': float(vs['total_distance'] or 0),
            'fuel': float(vehicle_fuel['total_fuel'] or 0),
            'efficiency': float(vehicle_fuel['avg_consumption'] or 0)
        })

    # ===== TOP CONDUCTEURS =====
    top_drivers = []
    driver_stats = trips_period.values('driver_id', 'driver__user__first_name', 'driver__user__last_name').annotate(
        trips_count=Count('id'),
        total_distance=Sum('total_distance')
    ).order_by('-total_distance')[:5]

    for ds in driver_stats:
        driver_incidents = incidents_period.filter(driver_id=ds['driver_id']).count()
        top_drivers.append({
            'driver_id': ds['driver_id'],
            'name': f"{ds['driver__user__first_name']} {ds['driver__user__last_name']}",
            'trips': ds['trips_count'],
            'distance': float(ds['total_distance'] or 0),
            'incidents': driver_incidents
        })

    # ===== DONNÉES HEBDOMADAIRES =====
    weekly_data = []
    for i in range(7):
        day = date_end - timedelta(days=6-i)
        day_trips = trips_period.filter(start_time__date=day)
        day_fuel = fuel_period.filter(refuel_date__date=day)

        weekly_data.append({
            'date': day.strftime('%Y-%m-%d'),
            'day': ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'][day.weekday()],
            'trips': day_trips.count(),
            'distance': float(day_trips.aggregate(total=Sum('total_distance'))['total'] or 0),
            'fuel_cost': float(day_fuel.aggregate(total=Sum('total_cost'))['total'] or 0)
        })

    # ===== DONNÉES MENSUELLES =====
    monthly_data = []
    current = date_start
    while current <= date_end:
        month_start = current.replace(day=1)
        if current.month == 12:
            month_end = current.replace(year=current.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = current.replace(month=current.month + 1, day=1) - timedelta(days=1)

        if month_end > date_end:
            month_end = date_end

        month_trips = trips_period.filter(start_time__date__gte=month_start, start_time__date__lte=month_end)
        month_fuel = fuel_period.filter(refuel_date__date__gte=month_start, refuel_date__date__lte=month_end)
        month_maintenance = maintenance_period.filter(scheduled_date__gte=month_start, scheduled_date__lte=month_end)

        monthly_data.append({
            'month': month_start.strftime('%Y-%m'),
            'label': month_start.strftime('%B %Y'),
            'trips': month_trips.count(),
            'distance': float(month_trips.aggregate(total=Sum('total_distance'))['total'] or 0),
            'fuel_quantity': float(month_fuel.aggregate(total=Sum('quantity'))['total'] or 0),
            'fuel_cost': float(month_fuel.aggregate(total=Sum('total_cost'))['total'] or 0),
            'maintenance_cost': float(month_maintenance.aggregate(total=Sum('total_cost'))['total'] or 0)
        })

        # Passer au mois suivant
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1, day=1)
        else:
            current = current.replace(month=current.month + 1, day=1)

    # ===== RÉPARTITION PAR TYPE =====
    fuel_by_type = {}
    for fuel_type in ['gasoline', 'diesel', 'electric']:
        type_stats = fuel_period.filter(fuel_type=fuel_type).aggregate(
            count=Count('id'),
            quantity=Sum('quantity'),
            cost=Sum('total_cost')
        )
        fuel_by_type[fuel_type] = {
            'count': type_stats['count'] or 0,
            'quantity': float(type_stats['quantity'] or 0),
            'cost': float(type_stats['cost'] or 0)
        }

    # ===== DISPONIBILITÉ FLOTTE =====
    total_vehicles = vehicles_qs.count()
    available_vehicles = vehicles_qs.filter(status='available').count()
    availability_rate = (available_vehicles / total_vehicles * 100) if total_vehicles else 0

    # ===== RÉPONSE =====
    return Response({
        'period': {
            'start': date_start.strftime('%Y-%m-%d'),
            'end': date_end.strftime('%Y-%m-%d'),
            'label': period
        },
        'filters': {
            'vehicle_id': int(vehicle_id) if vehicle_id else None,
            'driver_id': int(driver_id) if driver_id else None
        },
        'stats': {
            'distance': {
                'value': float(distance_current),
                'change': round(float(distance_change), 1),
                'unit': 'km'
            },
            'fuel': {
                'value': float(fuel_current),
                'change': round(float(fuel_change), 1),
                'unit': 'L'
            },
            'fuel_cost': {
                'value': float(fuel_cost_current),
                'change': round(float(fuel_cost_change), 1),
                'unit': '$'
            },
            'maintenance_cost': {
                'value': float(maintenance_cost_current),
                'change': round(float(maintenance_cost_change), 1),
                'unit': '$'
            },
            'total_cost': {
                'value': float(total_cost),
                'change': round(float(total_cost_change), 1),
                'unit': '$'
            },
            'trips': {
                'value': trips_count,
                'change': round(float(trips_change), 1)
            },
            'hours': {
                'value': round(total_hours, 1),
                'change': round(float(hours_change), 1),
                'unit': 'h'
            },
            'incidents': {
                'value': incidents_count,
                'change': round(float(incidents_change), 1)
            },
            'avg_consumption': {
                'value': round(float(avg_consumption), 2),
                'change': round(float(consumption_change), 1),
                'unit': 'L/100km'
            },
            'availability': {
                'value': round(availability_rate, 1),
                'unit': '%'
            }
        },
        'top_vehicles': top_vehicles,
        'top_drivers': top_drivers,
        'weekly_data': weekly_data,
        'monthly_data': monthly_data,
        'fuel_by_type': fuel_by_type,
        'fleet': {
            'total_vehicles': total_vehicles,
            'total_drivers': drivers_qs.count()
        }
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsOrganizationMember])
def export_csv(request):
    """Export des données en CSV"""
    organization = request.user.organization

    # Paramètres
    export_type = request.query_params.get('type', 'all')  # all, fuel, trips, maintenance, incidents
    period = request.query_params.get('period', 'month')
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    vehicle_id = request.query_params.get('vehicle')
    driver_id = request.query_params.get('driver')

    date_start, date_end = get_date_range(period, start_date, end_date)

    # Créer la réponse CSV
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="rapport_{export_type}_{date_start}_{date_end}.csv"'
    response.write('\ufeff')  # BOM pour Excel

    writer = csv.writer(response, delimiter=';')

    if export_type == 'fuel' or export_type == 'all':
        fuel_qs = FuelRecord.objects.filter(
            organization=organization,
            refuel_date__date__gte=date_start,
            refuel_date__date__lte=date_end
        ).select_related('vehicle', 'driver__user')

        if vehicle_id:
            fuel_qs = fuel_qs.filter(vehicle_id=vehicle_id)
        if driver_id:
            fuel_qs = fuel_qs.filter(driver_id=driver_id)

        writer.writerow(['=== CARBURANT ==='])
        writer.writerow(['Date', 'Véhicule', 'Conducteur', 'Station', 'Type', 'Quantité (L)', 'Prix unitaire', 'Coût total', 'Kilométrage', 'Consommation'])

        for record in fuel_qs:
            writer.writerow([
                record.refuel_date.strftime('%Y-%m-%d %H:%M'),
                record.vehicle.license_plate if record.vehicle else '',
                f"{record.driver.user.first_name} {record.driver.user.last_name}" if record.driver else '',
                record.station_name,
                record.get_fuel_type_display(),
                record.quantity,
                record.unit_price,
                record.total_cost,
                record.mileage_at_refuel,
                record.calculated_consumption or ''
            ])
        writer.writerow([])

    if export_type == 'trips' or export_type == 'all':
        trips_qs = Trip.objects.filter(
            organization=organization,
            start_time__date__gte=date_start,
            start_time__date__lte=date_end
        ).select_related('vehicle', 'driver__user', 'mission')

        if vehicle_id:
            trips_qs = trips_qs.filter(vehicle_id=vehicle_id)
        if driver_id:
            trips_qs = trips_qs.filter(driver_id=driver_id)

        writer.writerow(['=== TRAJETS ==='])
        writer.writerow(['Début', 'Fin', 'Véhicule', 'Conducteur', 'Distance (km)', 'Durée', 'Origine', 'Destination', 'Statut'])

        for trip in trips_qs:
            duration = ''
            if trip.end_time:
                delta = trip.end_time - trip.start_time
                hours, remainder = divmod(delta.total_seconds(), 3600)
                minutes = remainder // 60
                duration = f"{int(hours)}h{int(minutes)}min"

            writer.writerow([
                trip.start_time.strftime('%Y-%m-%d %H:%M'),
                trip.end_time.strftime('%Y-%m-%d %H:%M') if trip.end_time else '',
                trip.vehicle.license_plate if trip.vehicle else '',
                f"{trip.driver.user.first_name} {trip.driver.user.last_name}" if trip.driver else '',
                trip.total_distance or '',
                duration,
                trip.mission.origin_address if trip.mission else '',
                trip.mission.destination_address if trip.mission else '',
                trip.status
            ])
        writer.writerow([])

    if export_type == 'maintenance' or export_type == 'all':
        maintenance_qs = MaintenanceRecord.objects.filter(
            organization=organization,
            scheduled_date__gte=date_start,
            scheduled_date__lte=date_end
        ).select_related('vehicle')

        if vehicle_id:
            maintenance_qs = maintenance_qs.filter(vehicle_id=vehicle_id)

        writer.writerow(['=== MAINTENANCE ==='])
        writer.writerow(['Date prévue', 'Véhicule', 'Type', 'Description', 'Coût pièces', 'Coût main d\'œuvre', 'Coût total', 'Statut'])

        for record in maintenance_qs:
            writer.writerow([
                record.scheduled_date.strftime('%Y-%m-%d'),
                record.vehicle.license_plate if record.vehicle else '',
                record.get_maintenance_type_display(),
                record.description,
                record.parts_cost,
                record.labor_cost,
                record.total_cost,
                record.get_status_display()
            ])
        writer.writerow([])

    if export_type == 'incidents' or export_type == 'all':
        incidents_qs = Incident.objects.filter(
            organization=organization,
            reported_at__date__gte=date_start,
            reported_at__date__lte=date_end
        ).select_related('vehicle', 'driver__user')

        if vehicle_id:
            incidents_qs = incidents_qs.filter(vehicle_id=vehicle_id)
        if driver_id:
            incidents_qs = incidents_qs.filter(driver_id=driver_id)

        writer.writerow(['=== INCIDENTS ==='])
        writer.writerow(['Date', 'Véhicule', 'Conducteur', 'Type', 'Sévérité', 'Description', 'Lieu', 'Résolu'])

        for incident in incidents_qs:
            writer.writerow([
                incident.reported_at.strftime('%Y-%m-%d %H:%M'),
                incident.vehicle.license_plate if incident.vehicle else '',
                f"{incident.driver.user.first_name} {incident.driver.user.last_name}" if incident.driver else '',
                incident.get_incident_type_display(),
                incident.get_severity_display(),
                incident.description,
                incident.address or '',
                'Oui' if incident.is_resolved else 'Non'
            ])

    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsOrganizationMember])
def export_json(request):
    """Export des données en JSON (pour Excel via Power Query ou traitement externe)"""
    organization = request.user.organization

    # Paramètres
    export_type = request.query_params.get('type', 'all')
    period = request.query_params.get('period', 'month')
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    vehicle_id = request.query_params.get('vehicle')
    driver_id = request.query_params.get('driver')

    date_start, date_end = get_date_range(period, start_date, end_date)

    data = {
        'period': {
            'start': date_start.strftime('%Y-%m-%d'),
            'end': date_end.strftime('%Y-%m-%d')
        },
        'exported_at': timezone.now().isoformat()
    }

    if export_type == 'fuel' or export_type == 'all':
        fuel_qs = FuelRecord.objects.filter(
            organization=organization,
            refuel_date__date__gte=date_start,
            refuel_date__date__lte=date_end
        ).select_related('vehicle', 'driver__user')

        if vehicle_id:
            fuel_qs = fuel_qs.filter(vehicle_id=vehicle_id)
        if driver_id:
            fuel_qs = fuel_qs.filter(driver_id=driver_id)

        data['fuel'] = [{
            'date': r.refuel_date.isoformat(),
            'vehicle_plate': r.vehicle.license_plate if r.vehicle else None,
            'driver_name': f"{r.driver.user.first_name} {r.driver.user.last_name}" if r.driver else None,
            'station': r.station_name,
            'fuel_type': r.fuel_type,
            'quantity': float(r.quantity),
            'unit_price': float(r.unit_price),
            'total_cost': float(r.total_cost),
            'mileage': r.mileage_at_refuel,
            'consumption': float(r.calculated_consumption) if r.calculated_consumption else None
        } for r in fuel_qs]

    if export_type == 'trips' or export_type == 'all':
        trips_qs = Trip.objects.filter(
            organization=organization,
            start_time__date__gte=date_start,
            start_time__date__lte=date_end
        ).select_related('vehicle', 'driver__user', 'mission')

        if vehicle_id:
            trips_qs = trips_qs.filter(vehicle_id=vehicle_id)
        if driver_id:
            trips_qs = trips_qs.filter(driver_id=driver_id)

        data['trips'] = [{
            'start_time': t.start_time.isoformat(),
            'end_time': t.end_time.isoformat() if t.end_time else None,
            'vehicle_plate': t.vehicle.license_plate if t.vehicle else None,
            'driver_name': f"{t.driver.user.first_name} {t.driver.user.last_name}" if t.driver else None,
            'total_distance': float(t.total_distance) if t.total_distance else None,
            'start_address': t.mission.origin_address if t.mission else None,
            'end_address': t.mission.destination_address if t.mission else None,
            'status': t.status
        } for t in trips_qs]

    if export_type == 'maintenance' or export_type == 'all':
        maintenance_qs = MaintenanceRecord.objects.filter(
            organization=organization,
            scheduled_date__gte=date_start,
            scheduled_date__lte=date_end
        ).select_related('vehicle')

        if vehicle_id:
            maintenance_qs = maintenance_qs.filter(vehicle_id=vehicle_id)

        data['maintenance'] = [{
            'date': m.scheduled_date.isoformat(),
            'vehicle_plate': m.vehicle.license_plate if m.vehicle else None,
            'type': m.maintenance_type,
            'description': m.description,
            'parts_cost': float(m.parts_cost),
            'labor_cost': float(m.labor_cost),
            'total_cost': float(m.total_cost),
            'status': m.status
        } for m in maintenance_qs]

    if export_type == 'incidents' or export_type == 'all':
        incidents_qs = Incident.objects.filter(
            organization=organization,
            reported_at__date__gte=date_start,
            reported_at__date__lte=date_end
        ).select_related('vehicle', 'driver__user')

        if vehicle_id:
            incidents_qs = incidents_qs.filter(vehicle_id=vehicle_id)
        if driver_id:
            incidents_qs = incidents_qs.filter(driver_id=driver_id)

        data['incidents'] = [{
            'date': i.reported_at.isoformat(),
            'vehicle_plate': i.vehicle.license_plate if i.vehicle else None,
            'driver_name': f"{i.driver.user.first_name} {i.driver.user.last_name}" if i.driver else None,
            'type': i.incident_type,
            'severity': i.severity,
            'description': i.description,
            'location': i.address,
            'is_resolved': i.is_resolved
        } for i in incidents_qs]

    return Response(data)
