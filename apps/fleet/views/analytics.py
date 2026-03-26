from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Avg, Count, Min, Max, F
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from apps.fleet.models import Vehicle, FuelRecord, MaintenanceRecord, Trip, Incident, Driver
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

    incidents_qs = Incident.objects.filter(organization=organization)

    # Filtrer par période
    fuel_period = fuel_qs.filter(refuel_date__date__gte=date_start, refuel_date__date__lte=date_end)
    fuel_prev = fuel_qs.filter(refuel_date__date__gte=prev_start, refuel_date__date__lte=prev_end)
    maintenance_period = maintenance_qs.filter(scheduled_date__gte=date_start, scheduled_date__lte=date_end)
    maintenance_prev = maintenance_qs.filter(scheduled_date__gte=prev_start, scheduled_date__lte=prev_end)
    trips_period = trips_qs.filter(start_time__date__gte=date_start, start_time__date__lte=date_end)
    incidents_period = incidents_qs.filter(reported_at__date__gte=date_start, reported_at__date__lte=date_end)
    incidents_prev = incidents_qs.filter(reported_at__date__gte=prev_start, reported_at__date__lte=prev_end)

    # ===== COÛTS TOTAUX =====
    fuel_cost = fuel_period.aggregate(total=Sum('total_cost'))['total'] or Decimal('0')
    fuel_cost_prev = fuel_prev.aggregate(total=Sum('total_cost'))['total'] or Decimal('0')

    maintenance_cost = maintenance_period.aggregate(total=Sum('total_cost'))['total'] or Decimal('0')
    maintenance_cost_prev = maintenance_prev.aggregate(total=Sum('total_cost'))['total'] or Decimal('0')

    incident_cost = incidents_period.aggregate(total=Sum('repair_cost'))['total'] or Decimal('0')
    incident_cost_prev = incidents_prev.aggregate(total=Sum('repair_cost'))['total'] or Decimal('0')
    incident_count = incidents_period.count()
    incident_resolved = incidents_period.filter(is_resolved=True).count()

    total_cost = fuel_cost + maintenance_cost + incident_cost
    total_cost_prev = fuel_cost_prev + maintenance_cost_prev + incident_cost_prev
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

    # ===== TENDANCES MENSUELLES (toujours 12 derniers mois) =====
    monthly_trends = []
    today = timezone.now().date()
    trend_start = today.replace(day=1)
    # Remonter 11 mois en arriere
    if trend_start.month > 11:
        trend_start = trend_start.replace(year=trend_start.year - 1, month=trend_start.month - 11)
    else:
        trend_start = trend_start.replace(year=trend_start.year - 1, month=trend_start.month + 1)

    current = trend_start
    while current <= today:
        month_start = current.replace(day=1)
        if current.month == 12:
            month_end = current.replace(year=current.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = current.replace(month=current.month + 1, day=1) - timedelta(days=1)

        if month_end > today:
            month_end = today

        month_fuel = fuel_qs.filter(refuel_date__date__gte=month_start, refuel_date__date__lte=month_end)
        month_maintenance = maintenance_qs.filter(scheduled_date__gte=month_start, scheduled_date__lte=month_end)
        month_trips = trips_qs.filter(start_time__date__gte=month_start, start_time__date__lte=month_end)
        month_incidents = incidents_qs.filter(reported_at__date__gte=month_start, reported_at__date__lte=month_end)

        fuel_month_cost = month_fuel.aggregate(total=Sum('total_cost'))['total'] or Decimal('0')
        maintenance_month_cost = month_maintenance.aggregate(total=Sum('total_cost'))['total'] or Decimal('0')
        incident_month_cost = month_incidents.aggregate(total=Sum('repair_cost'))['total'] or Decimal('0')
        month_quantity = month_fuel.aggregate(total=Sum('quantity'))['total'] or Decimal('0')
        month_distance = month_trips.aggregate(total=Sum('total_distance'))['total'] or Decimal('0')
        month_consumption = month_fuel.aggregate(avg=Avg('calculated_consumption'))['avg'] or 0

        monthly_trends.append({
            'month': month_start.strftime('%Y-%m'),
            'label': month_start.strftime('%b %Y'),
            'fuel_cost': float(fuel_month_cost),
            'maintenance_cost': float(maintenance_month_cost),
            'incident_cost': float(incident_month_cost),
            'total_cost': float(fuel_month_cost + maintenance_month_cost + incident_month_cost),
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
        },
        'incidents': {
            'amount': float(incident_cost),
            'percentage': float(incident_cost / total_cost * 100) if total_cost else 0,
            'change': float((incident_cost - incident_cost_prev) / incident_cost_prev * 100) if incident_cost_prev else 0
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

    # ===== ANALYSE DES CHAUFFEURS =====
    from apps.fleet.models.mission import Mission
    drivers_qs = Driver.objects.filter(organization=organization)
    missions_qs = Mission.objects.filter(organization=organization)
    missions_period = missions_qs.filter(scheduled_start__date__gte=date_start, scheduled_start__date__lte=date_end)

    driver_analytics = []
    for drv in drivers_qs:
        drv_missions = missions_period.filter(driver=drv)
        drv_missions_total = drv_missions.count()
        drv_missions_completed = drv_missions.filter(status='completed').count()
        drv_missions_cancelled = drv_missions.filter(status='cancelled').count()
        drv_incidents = incidents_period.filter(driver=drv)
        drv_incident_count = drv_incidents.count()

        # Retards: missions où actual_start > scheduled_start
        drv_late = drv_missions.filter(
            actual_start__isnull=False,
            actual_start__gt=F('scheduled_start')
        ).count() if drv_missions_total else 0

        driver_analytics.append({
            'id': drv.id,
            'full_name': drv.full_name,
            'employee_id': drv.employee_id,
            'photo': drv.photo.url if drv.photo else None,
            'status': drv.status,
            'rating': float(drv.rating),
            'total_missions': drv_missions_total,
            'completed_missions': drv_missions_completed,
            'cancelled_missions': drv_missions_cancelled,
            'late_count': drv_late,
            'late_rate': round(drv_late / drv_missions_total * 100, 1) if drv_missions_total else 0,
            'incident_count': drv_incident_count,
            'incident_rate': round(drv_incident_count / drv_missions_total * 100, 1) if drv_missions_total else 0,
        })
    driver_analytics.sort(key=lambda x: x['rating'], reverse=True)

    # Driver status distribution
    driver_status_dist = {
        'available': drivers_qs.filter(status='available').count(),
        'on_mission': drivers_qs.filter(status='on_mission').count(),
        'on_break': drivers_qs.filter(status='on_break').count(),
        'off_duty': drivers_qs.filter(status='off_duty').count(),
    }

    # ===== ANALYSE DES VÉHICULES =====
    vehicle_analytics = []
    for veh in vehicles_qs:
        veh_fuel = fuel_period.filter(vehicle=veh)
        veh_maintenance = maintenance_period.filter(vehicle=veh)
        veh_incidents = incidents_period.filter(vehicle=veh)
        veh_missions = missions_period.filter(vehicle=veh)

        veh_fuel_cost = veh_fuel.aggregate(total=Sum('total_cost'))['total'] or Decimal('0')
        veh_maint_cost = veh_maintenance.aggregate(total=Sum('total_cost'))['total'] or Decimal('0')
        veh_maint_preventive = veh_maintenance.filter(maintenance_type__in=['preventive', 'oil_change', 'tire_change', 'inspection'])
        veh_maint_corrective = veh_maintenance.filter(maintenance_type__in=['repair', 'brake_service', 'other'])
        veh_avg_consumption = veh_fuel.aggregate(avg=Avg('calculated_consumption'))['avg'] or 0
        veh_total_quantity = veh_fuel.aggregate(total=Sum('quantity'))['total'] or Decimal('0')

        vehicle_analytics.append({
            'id': veh.id,
            'license_plate': veh.license_plate,
            'brand': veh.brand,
            'model': veh.model,
            'current_mileage': float(veh.current_mileage),
            'fuel_type': veh.fuel_type,
            'status': veh.status,
            'avg_consumption': float(veh_avg_consumption),
            'total_fuel_quantity': float(veh_total_quantity),
            'fuel_cost': float(veh_fuel_cost),
            'maintenance_cost': float(veh_maint_cost),
            'preventive_count': veh_maint_preventive.count(),
            'preventive_cost': float(veh_maint_preventive.aggregate(total=Sum('total_cost'))['total'] or 0),
            'corrective_count': veh_maint_corrective.count(),
            'corrective_cost': float(veh_maint_corrective.aggregate(total=Sum('total_cost'))['total'] or 0),
            'incident_count': veh_incidents.count(),
            'mission_count': veh_missions.count(),
            'total_cost': float(veh_fuel_cost + veh_maint_cost),
        })
    vehicle_analytics.sort(key=lambda x: x['total_cost'], reverse=True)

    # ===== ANALYSE DES INCIDENTS =====
    incident_type_stats = {}
    for itype in ['flat_tire', 'breakdown', 'accident', 'fuel_issue', 'traffic_violation', 'other']:
        typed = incidents_period.filter(incident_type=itype)
        type_count = typed.count()
        type_cost = typed.aggregate(total=Sum('repair_cost'))['total'] or Decimal('0')
        incident_type_stats[itype] = {
            'count': type_count,
            'cost': float(type_cost),
            'avg_cost': float(type_cost / type_count) if type_count else 0,
        }

    incident_locations = []
    for inc in incidents_period.filter(latitude__isnull=False, longitude__isnull=False)[:20]:
        incident_locations.append({
            'id': inc.id,
            'lat': float(inc.latitude),
            'lng': float(inc.longitude),
            'type': inc.incident_type,
            'severity': inc.severity,
            'title': inc.title,
            'address': inc.address or '',
        })

    avg_incident_cost = incidents_period.filter(repair_cost__isnull=False).aggregate(avg=Avg('repair_cost'))['avg'] or 0

    # ===== ANALYSE FINANCIÈRE =====
    # Coût par mission
    mission_costs = []
    for m in missions_period.filter(status='completed')[:10]:
        m_fuel = fuel_qs.filter(driver__missions=m, refuel_date__date__gte=m.actual_start.date() if m.actual_start else m.scheduled_start.date(), refuel_date__date__lte=m.actual_end.date() if m.actual_end else m.scheduled_end.date()) if m.actual_start or m.scheduled_start else fuel_qs.none()
        m_fuel_cost = m_fuel.aggregate(total=Sum('total_cost'))['total'] or Decimal('0')
        mission_costs.append({
            'mission_code': m.mission_code,
            'title': m.title,
            'driver_name': m.driver.full_name if m.driver else None,
            'vehicle_plate': m.vehicle.license_plate if m.vehicle else None,
            'fuel_cost': float(m_fuel_cost),
        })

    # Coût par chauffeur
    cost_per_driver = []
    for drv in drivers_qs:
        drv_fuel = fuel_period.filter(driver=drv).aggregate(total=Sum('total_cost'))['total'] or Decimal('0')
        drv_incidents_cost = incidents_period.filter(driver=drv).aggregate(total=Sum('repair_cost'))['total'] or Decimal('0')
        total = float(drv_fuel + drv_incidents_cost)
        if total > 0:
            cost_per_driver.append({
                'id': drv.id,
                'full_name': drv.full_name,
                'fuel_cost': float(drv_fuel),
                'incident_cost': float(drv_incidents_cost),
                'total_cost': total,
            })
    cost_per_driver.sort(key=lambda x: x['total_cost'], reverse=True)

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
            'incident_cost': {
                'value': float(incident_cost),
                'change': round(float(cost_breakdown['incidents']['change']), 1)
            },
            'incident_count': incident_count,
            'incident_resolved': incident_resolved,
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
        'top_costly': sorted(vehicle_consumption, key=lambda x: x['total_cost'], reverse=True)[:5],
        'driver_analytics': driver_analytics,
        'driver_status_distribution': driver_status_dist,
        'vehicle_analytics': vehicle_analytics,
        'incident_analytics': {
            'by_type': incident_type_stats,
            'avg_cost': float(avg_incident_cost),
            'total_count': incident_count,
            'resolved_count': incident_resolved,
            'locations': incident_locations,
        },
        'financial': {
            'cost_per_driver': cost_per_driver[:10],
            'mission_costs': mission_costs,
            'budget_summary': {
                'fuel': float(fuel_cost),
                'maintenance': float(maintenance_cost),
                'incidents': float(incident_cost),
                'total': float(total_cost),
                'maintenance_parts': float(parts_cost),
                'maintenance_labor': float(labor_cost),
            }
        }
    })
