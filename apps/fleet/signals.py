"""
Signaux Django pour le suivi des activités de la flotte
"""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Mission, Trip, Incident, Vehicle, Driver, Activity


# ============================================
# MISSIONS
# ============================================

@receiver(post_save, sender=Mission)
def track_mission_activity(sender, instance, created, **kwargs):
    """Suivi des activités liées aux missions"""
    if created:
        # Nouvelle mission créée
        Activity.log(
            activity_type='mission_created',
            title=f'Mission "{instance.title}" créée',
            description=f'Mission {instance.mission_code} assignée à {instance.driver.user.get_full_name()}',
            organization=instance.organization,
            severity='info',
            mission=instance,
            vehicle=instance.vehicle,
            driver=instance.driver,
            user=instance.created_by,
            metadata={
                'mission_code': instance.mission_code,
                'destination': instance.destination_address,
            }
        )


@receiver(pre_save, sender=Mission)
def track_mission_status_change(sender, instance, **kwargs):
    """Détecter les changements de statut de mission"""
    if not instance.pk:
        return  # Nouvelle instance, pas de changement

    try:
        old_instance = Mission.objects.get(pk=instance.pk)
    except Mission.DoesNotExist:
        return

    if old_instance.status != instance.status:
        # Statut a changé
        if instance.status == 'in_progress' and old_instance.status != 'in_progress':
            # Mission démarrée
            Activity.log(
                activity_type='mission_started',
                title=f'Mission "{instance.title}" démarrée',
                description=f'{instance.driver.user.get_full_name()} a démarré la mission {instance.mission_code}',
                organization=instance.organization,
                severity='success',
                mission=instance,
                vehicle=instance.vehicle,
                driver=instance.driver,
                metadata={
                    'mission_code': instance.mission_code,
                    'started_at': timezone.now().isoformat(),
                }
            )
        elif instance.status == 'completed':
            # Mission terminée
            Activity.log(
                activity_type='mission_completed',
                title=f'Mission "{instance.title}" terminée',
                description=f'{instance.driver.user.get_full_name()} a terminé la mission {instance.mission_code}',
                organization=instance.organization,
                severity='success',
                mission=instance,
                vehicle=instance.vehicle,
                driver=instance.driver,
                metadata={
                    'mission_code': instance.mission_code,
                    'completed_at': timezone.now().isoformat(),
                }
            )
        elif instance.status == 'cancelled':
            # Mission annulée
            Activity.log(
                activity_type='mission_cancelled',
                title=f'Mission "{instance.title}" annulée',
                description=f'La mission {instance.mission_code} a été annulée',
                organization=instance.organization,
                severity='warning',
                mission=instance,
                vehicle=instance.vehicle,
                driver=instance.driver,
                metadata={
                    'mission_code': instance.mission_code,
                    'cancelled_at': timezone.now().isoformat(),
                }
            )

        # Recalculer la note du chauffeur quand une mission est terminée ou annulée
        if instance.status in ('completed', 'cancelled'):
            from apps.fleet.services.driver_performance import DriverPerformanceService
            DriverPerformanceService.update_driver_rating(instance.driver)


# ============================================
# TRAJETS
# ============================================

@receiver(pre_save, sender=Trip)
def track_trip_status_change(sender, instance, **kwargs):
    """Détecter les changements de statut de trajet"""
    if not instance.pk:
        return

    try:
        old_instance = Trip.objects.get(pk=instance.pk)
    except Trip.DoesNotExist:
        return

    if old_instance.status != instance.status:
        mission = instance.mission
        driver = mission.driver if mission else None
        vehicle = mission.vehicle if mission else None
        org = mission.organization if mission else None

        if instance.status == 'in_progress' and old_instance.status == 'pending':
            Activity.log(
                activity_type='trip_started',
                title='Trajet démarré',
                description=f'{driver.user.get_full_name() if driver else "Chauffeur"} a démarré le trajet',
                organization=org,
                severity='info',
                mission=mission,
                vehicle=vehicle,
                driver=driver,
                metadata={
                    'trip_id': instance.id,
                }
            )
        elif instance.status == 'paused':
            Activity.log(
                activity_type='trip_paused',
                title='Trajet en pause',
                description=f'{driver.user.get_full_name() if driver else "Chauffeur"} a mis le trajet en pause',
                organization=org,
                severity='warning',
                mission=mission,
                vehicle=vehicle,
                driver=driver,
                metadata={
                    'trip_id': instance.id,
                }
            )
        elif instance.status == 'in_progress' and old_instance.status == 'paused':
            Activity.log(
                activity_type='trip_resumed',
                title='Trajet repris',
                description=f'{driver.user.get_full_name() if driver else "Chauffeur"} a repris le trajet',
                organization=org,
                severity='info',
                mission=mission,
                vehicle=vehicle,
                driver=driver,
                metadata={
                    'trip_id': instance.id,
                }
            )
        elif instance.status == 'completed':
            Activity.log(
                activity_type='trip_completed',
                title='Trajet terminé',
                description=f'{driver.user.get_full_name() if driver else "Chauffeur"} a terminé le trajet',
                organization=org,
                severity='success',
                mission=mission,
                vehicle=vehicle,
                driver=driver,
                metadata={
                    'trip_id': instance.id,
                    'distance': float(instance.total_distance) if instance.total_distance else 0,
                }
            )


# ============================================
# INCIDENTS
# ============================================

@receiver(post_save, sender=Incident)
def track_incident_activity(sender, instance, created, **kwargs):
    """Suivi des activités liées aux incidents"""
    if created:
        # Nouvel incident signalé
        severity_map = {
            'minor': 'info',
            'moderate': 'warning',
            'major': 'warning',
            'critical': 'error',
        }
        Activity.log(
            activity_type='incident_reported',
            title=f'Incident signalé: {instance.title}',
            description=f'{instance.get_incident_type_display()} - {instance.get_severity_display()}',
            organization=instance.organization,
            severity=severity_map.get(instance.severity, 'warning'),
            incident=instance,
            vehicle=instance.vehicle,
            driver=instance.driver,
            metadata={
                'incident_type': instance.incident_type,
                'severity': instance.severity,
                'address': instance.address,
            }
        )

        # Recalculer la note du chauffeur (les incidents impactent la note)
        if instance.driver:
            from apps.fleet.services.driver_performance import DriverPerformanceService
            DriverPerformanceService.update_driver_rating(instance.driver)


@receiver(pre_save, sender=Incident)
def track_incident_resolution(sender, instance, **kwargs):
    """Détecter la résolution d'un incident"""
    if not instance.pk:
        return

    try:
        old_instance = Incident.objects.get(pk=instance.pk)
    except Incident.DoesNotExist:
        return

    if not old_instance.is_resolved and instance.is_resolved:
        # Incident vient d'être résolu
        Activity.log(
            activity_type='incident_resolved',
            title=f'Incident résolu: {instance.title}',
            description=instance.resolution_notes or 'Incident marqué comme résolu',
            organization=instance.organization,
            severity='success',
            incident=instance,
            vehicle=instance.vehicle,
            driver=instance.driver,
            user=instance.resolved_by,
            metadata={
                'incident_type': instance.incident_type,
                'resolution_notes': instance.resolution_notes,
            }
        )


# ============================================
# VÉHICULES
# ============================================

@receiver(post_save, sender=Vehicle)
def track_vehicle_activity(sender, instance, created, **kwargs):
    """Suivi des activités liées aux véhicules"""
    if created:
        Activity.log(
            activity_type='vehicle_created',
            title=f'Nouveau véhicule: {instance.license_plate}',
            description=f'{instance.brand} {instance.model} ({instance.year})',
            organization=instance.organization,
            severity='info',
            vehicle=instance,
            metadata={
                'brand': instance.brand,
                'model': instance.model,
                'license_plate': instance.license_plate,
            }
        )


@receiver(pre_save, sender=Vehicle)
def track_vehicle_status_change(sender, instance, **kwargs):
    """Détecter les changements de statut de véhicule"""
    if not instance.pk:
        return

    try:
        old_instance = Vehicle.objects.get(pk=instance.pk)
    except Vehicle.DoesNotExist:
        return

    if old_instance.status != instance.status:
        status_display = dict(Vehicle.STATUS_CHOICES).get(instance.status, instance.status)
        old_status_display = dict(Vehicle.STATUS_CHOICES).get(old_instance.status, old_instance.status)

        severity = 'info'
        if instance.status == 'maintenance':
            severity = 'warning'
        elif instance.status == 'out_of_service':
            severity = 'error'
        elif instance.status == 'available':
            severity = 'success'

        Activity.log(
            activity_type='vehicle_status_changed',
            title=f'Statut véhicule changé: {instance.license_plate}',
            description=f'{old_status_display} → {status_display}',
            organization=instance.organization,
            severity=severity,
            vehicle=instance,
            metadata={
                'old_status': old_instance.status,
                'new_status': instance.status,
            }
        )


# ============================================
# CHAUFFEURS
# ============================================

@receiver(post_save, sender=Driver)
def track_driver_activity(sender, instance, created, **kwargs):
    """Suivi des activités liées aux chauffeurs"""
    if created:
        Activity.log(
            activity_type='driver_created',
            title=f'Nouveau chauffeur: {instance.user.get_full_name()}',
            description=f'ID employé: {instance.employee_id}',
            organization=instance.organization,
            severity='info',
            driver=instance,
            user=instance.user,
            metadata={
                'employee_id': instance.employee_id,
            }
        )


@receiver(pre_save, sender=Driver)
def track_driver_status_change(sender, instance, **kwargs):
    """Détecter les changements de statut de chauffeur"""
    if not instance.pk:
        return

    try:
        old_instance = Driver.objects.get(pk=instance.pk)
    except Driver.DoesNotExist:
        return

    if old_instance.status != instance.status:
        status_display = dict(Driver.STATUS_CHOICES).get(instance.status, instance.status)
        old_status_display = dict(Driver.STATUS_CHOICES).get(old_instance.status, old_instance.status)

        severity = 'info'
        if instance.status == 'on_mission':
            severity = 'success'
        elif instance.status == 'off_duty':
            severity = 'warning'

        Activity.log(
            activity_type='driver_status_changed',
            title=f'Statut chauffeur changé: {instance.user.get_full_name()}',
            description=f'{old_status_display} → {status_display}',
            organization=instance.organization,
            severity=severity,
            driver=instance,
            user=instance.user,
            metadata={
                'old_status': old_instance.status,
                'new_status': instance.status,
            }
        )
