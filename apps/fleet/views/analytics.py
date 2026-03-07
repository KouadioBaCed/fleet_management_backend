from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Avg, Count, Min, Max, F
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from apps.fleet.models import Vehicle, FuelRecord, MaintenanceRecord, Trip
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


def get_previous_period_range(start_date, end_date):
    """Calcule la période précédente pour comparaison"""
    delta = end_date - start_date
    prev_end = start_date - timedelta(days=1)
    prev_start = prev_end - delta
    return prev_start, prev_end


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsOrganizationMember])
def fleet_analytics(request):
    """Analyse complète de la flotte avec période, consommation par véhicule et coûts"""
    organization = request.user.organization

    # Paramètres
    period = request.query_params.get('period', 'month')
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')

    # Calcul des dates
    date_start, date_end = get_date_range(period, start_date, end_date)
    prev_start, prev_end = get_previous_period_range(date_start, date_end)

    # Base querysets
    vehicles_qs = Vehicle.objects.filter(organization=organization)
    fuel_qs = FuelRecord.objects.filter(organization=organization)
    maintenance_qs = MaintenanceRecord.objects.filter(organization=organization)
    trips_qs = Trip.objects.filter(organization=organization)

    # Filtrer par période
    fuel_period = fuel_qs.filter(refuel_date__date__gte=date_start, refuel_date__date__lte=date_end)
    fuel_prev = fuel_qs.filter(refuel_date__date__gte=prev_start, refuel_date__date__lte=prev_end)
    maintenance_period = maintenance_qs.filter(scheduled_date__gte=date_start, scheduled_date__lte=date_end)
    maintenance_prev = maintenance_qs.filter(scheduled_date__gte=prev_start, scheduled_date__lte=prev_end)
    trips_period = trips_qs.filter(start_time__date__gte=date_start, start_time__date__lte=date_end)

    # ===== COÛTS TOTAUX =====
    fuel_cost = fuel_period.aggregate(total=Sum('total_cost'))['total'] or Decimal('0')
    fuel_cost_prev = fuel_prev.aggregate(total=Sum('total_cost'))['total'] or Decimal('0')

    maintenance_cost = maintenance_period.aggregate(total=Sum('total_cost'))['total'] or Decimal('0')
    maintenance_cost_prev = maintenance_prev.aggregate(total=Sum('total_cost'))['total'] or Decimal('0')

    total_cost = fuel_cost + maintenance_cost
    total_cost_prev = fuel_cost_prev + maintenance_cost_prev
    cost_change = ((total_cost - total_cost_prev) / total_cost_prev * 100) if total_cost_prev else 0

    # Total distance
    total_distance = trips_period.aggregate(total=Sum('total_distance'))['total'] or Decimal('0')
    total_distance_prev = trips_qs.filter(
        start_time__date__gte=prev_start,
        start_time__date__lte=prev_end
    ).aggregate(total=Sum('total_distance'))['total'] or Decimal('0')

    # Cost per km
    cost_per_km = (total_cost / total_distance) if total_distance else Decimal('0')
    cost_per_km_prev = (total_cost_prev / total_distance_prev) if total_distance_prev else Decimal('0')
    cost_per_km_change = ((cost_per_km - cost_per_km_prev) / cost_per_km_prev * 100) if cost_per_km_prev else 0

    # ===== CONSOMMATION PAR VÉHICULE =====
    vehicle_consumption = []
    for vehicle in vehicles_qs:
        v_fuel = fuel_period.filter(vehicle=vehicle)
        v_fuel_prev = fuel_prev.filter(vehicle=vehicle)
        v_trips = trips_period.filter(vehicle=vehicle)
        v_maintenance = maintenance_period.filter(vehicle=vehicle)

        # Stats carburant
        fuel_stats = v_fuel.aggregate(
            total_quantity=Sum('quantity'),
            total_cost=Sum('total_cost'),
            avg_consumption=Avg('calculated_consumption'),
            avg_price=Avg('unit_price'),
            refuel_count=Count('id')
        )

        fuel_stats_prev = v_fuel_prev.aggregate(
            total_cost=Sum('total_cost'),
            avg_consumption=Avg('calculated_consumption')
        )

        # Distance
        v_distance = v_trips.aggregate(total=Sum('total_distance'))['total'] or Decimal('0')

        # Coûts maintenance
        v_maintenance_cost = v_maintenance.aggregate(total=Sum('total_cost'))['total'] or Decimal('0')

        # Total cost for vehicle
        v_total_cost = (fuel_stats['total_cost'] or Decimal('0')) + v_maintenance_cost
        v_total_cost_prev = (fuel_stats_prev['total_cost'] or Decimal('0'))

        # Cost change
        v_cost_change = 0
        if v_total_cost_prev:
            v_cost_change = float((v_total_cost - v_total_cost_prev) / v_total_cost_prev * 100)

        # Consumption change
        v_consumption_change = 0
        if fuel_stats_prev['avg_consumption'] and fuel_stats['avg_consumption']:
            v_consumption_change = float(
                (fuel_stats['avg_consumption'] - fuel_stats_prev['avg_consumption']) /
                fuel_stats_prev['avg_consumption'] * 100
            )

        # Cost per km
        v_cost_per_km = float(v_total_cost / v_distance) if v_distance else 0

        # Expected consumption
        expected_consumption = getattr(vehicle, 'expected_fuel_consumption', None) or 10.0

        # Efficiency
        avg_consumption = fuel_stats['avg_consumption'] or 0
        efficiency_ratio = (expected_consumption / float(avg_consumption) * 100) if avg_consumption else 100

        # Status
        if efficiency_ratio >= 100:
            status = 'efficient'
        elif efficiency_ratio >= 85:
            status = 'warning'
        else:
            status = 'critical'

        vehicle_consumption.append({
            'vehicle_id': vehicle.id,
            'plate': vehicle.license_plate,
            'brand': vehicle.brand,
            'model': vehicle.model,
            'vehicle_type': vehicle.vehicle_type,
            'fuel_type': vehicle.fuel_type,
            'total_quantity': float(fuel_stats['total_quantity'] or 0),
            'fuel_cost': float(fuel_stats['total_cost'] or 0),
            'maintenance_cost': float(v_maintenance_cost),
            'total_cost': float(v_total_cost),
            'cost_change': round(v_cost_change, 1),
            'avg_consumption': float(avg_consumption),
            'consumption_change': round(v_consumption_change, 1),
            'expected_consumption': float(expected_consumption),
            'efficiency_ratio': round(efficiency_ratio, 1),
            'distance': float(v_distance),
            'cost_per_km': round(v_cost_per_km, 3),
            'refuel_count': fuel_stats['refuel_count'] or 0,
            'avg_price': float(fuel_stats['avg_price'] or 0),
            'status': status
        })

    # Sort by consumption
    vehicle_consumption.sort(key=lambda x: x['avg_consumption'] if x['avg_consumption'] else 999)

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

        month_fuel = fuel_period.filter(refuel_date__date__gte=month_start, refuel_date__date__lte=month_end)
        month_maintenance = maintenance_period.filter(scheduled_date__gte=month_start, scheduled_date__lte=month_end)
        month_trips = trips_period.filter(start_time__date__gte=month_start, start_time__date__lte=month_end)

        fuel_month_cost = month_fuel.aggregate(total=Sum('total_cost'))['total'] or Decimal('0')
        maintenance_month_cost = month_maintenance.aggregate(total=Sum('total_cost'))['total'] or Decimal('0')
        month_quantity = month_fuel.aggregate(total=Sum('quantity'))['total'] or Decimal('0')
        month_distance = month_trips.aggregate(total=Sum('total_distance'))['total'] or Decimal('0')
        month_consumption = month_fuel.aggregate(avg=Avg('calculated_consumption'))['avg'] or 0

        monthly_trends.append({
            'month': month_start.strftime('%Y-%m'),
            'label': month_start.strftime('%b %Y'),
            'fuel_cost': float(fuel_month_cost),
            'maintenance_cost': float(maintenance_month_cost),
            'total_cost': float(fuel_month_cost + maintenance_month_cost),
            'quantity': float(month_quantity),
            'distance': float(month_distance),
            'avg_consumption': float(month_consumption)
        })

        # Next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1, day=1)
        else:
            current = current.replace(month=current.month + 1, day=1)

    # ===== RÉPARTITION DES COÛTS =====
    cost_breakdown = {
        'fuel': {
            'amount': float(fuel_cost),
            'percentage': float(fuel_cost / total_cost * 100) if total_cost else 0,
            'change': float((fuel_cost - fuel_cost_prev) / fuel_cost_prev * 100) if fuel_cost_prev else 0
        },
        'maintenance': {
            'amount': float(maintenance_cost),
            'percentage': float(maintenance_cost / total_cost * 100) if total_cost else 0,
            'change': float((maintenance_cost - maintenance_cost_prev) / maintenance_cost_prev * 100) if maintenance_cost_prev else 0
        }
    }

    # Parts cost and labor cost breakdown
    parts_cost = maintenance_period.aggregate(total=Sum('parts_cost'))['total'] or Decimal('0')
    labor_cost = maintenance_period.aggregate(total=Sum('labor_cost'))['total'] or Decimal('0')

    # ===== STATISTIQUES GLOBALES =====
    total_quantity = fuel_period.aggregate(total=Sum('quantity'))['total'] or Decimal('0')
    total_quantity_prev = fuel_prev.aggregate(total=Sum('quantity'))['total'] or Decimal('0')
    quantity_change = ((total_quantity - total_quantity_prev) / total_quantity_prev * 100) if total_quantity_prev else 0

    avg_consumption = fuel_period.aggregate(avg=Avg('calculated_consumption'))['avg'] or 0
    avg_consumption_prev = fuel_prev.aggregate(avg=Avg('calculated_consumption'))['avg'] or 0
    consumption_change = ((avg_consumption - avg_consumption_prev) / avg_consumption_prev * 100) if avg_consumption_prev else 0

    # Efficiency distribution
    efficiency_dist = {'efficient': 0, 'warning': 0, 'critical': 0}
    for vc in vehicle_consumption:
        efficiency_dist[vc['status']] += 1

    return Response({
        'period': {
            'start': date_start.strftime('%Y-%m-%d'),
            'end': date_end.strftime('%Y-%m-%d'),
            'label': period
        },
        'summary': {
            'total_cost': {
                'value': float(total_cost),
                'change': round(float(cost_change), 1)
            },
            'fuel_cost': {
                'value': float(fuel_cost),
                'change': round(float(cost_breakdown['fuel']['change']), 1)
            },
            'maintenance_cost': {
                'value': float(maintenance_cost),
                'change': round(float(cost_breakdown['maintenance']['change']), 1)
            },
            'total_distance': {
                'value': float(total_distance),
                'change': round(float((total_distance - total_distance_prev) / total_distance_prev * 100) if total_distance_prev else 0, 1)
            },
            'total_quantity': {
                'value': float(total_quantity),
                'change': round(float(quantity_change), 1)
            },
            'avg_consumption': {
                'value': round(float(avg_consumption), 2),
                'change': round(float(consumption_change), 1)
            },
            'cost_per_km': {
                'value': round(float(cost_per_km), 3),
                'change': round(float(cost_per_km_change), 1)
            },
            'vehicles_count': vehicles_qs.count(),
            'efficiency_distribution': efficiency_dist
        },
        'cost_breakdown': {
            'by_category': cost_breakdown,
            'maintenance_detail': {
                'parts': float(parts_cost),
                'labor': float(labor_cost)
            }
        },
        'vehicle_consumption': vehicle_consumption,
        'monthly_trends': monthly_trends,
        'top_consumers': sorted(vehicle_consumption, key=lambda x: x['avg_consumption'], reverse=True)[:5],
        'top_costly': sorted(vehicle_consumption, key=lambda x: x['total_cost'], reverse=True)[:5]
    })
