from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from datetime import timedelta


@shared_task
def check_maintenance_alerts():
    """
    Verifie tous les vehicules et envoie des alertes (notification + email)
    quand une maintenance est due (par km ou par date).
    A executer quotidiennement via Celery Beat.
    """
    from apps.fleet.models import Vehicle
    from apps.fleet.models.notification import UserNotification, NotificationService
    from apps.accounts.models import User

    today = timezone.now().date()
    alerts_sent = 0

    for vehicle in Vehicle.objects.filter(status__in=['available', 'in_use']):
        alert_type = None
        alert_message = ''
        priority = 'normal'

        # Check mileage-based maintenance
        if vehicle.next_maintenance_mileage and vehicle.current_mileage:
            remaining_km = float(vehicle.next_maintenance_mileage - vehicle.current_mileage)
            if remaining_km <= 0:
                alert_type = 'maintenance_overdue'
                alert_message = (
                    f"Le vehicule {vehicle.license_plate} ({vehicle.brand} {vehicle.model}) "
                    f"a depasse le kilometrage de maintenance prevu de {abs(remaining_km):.0f} km."
                )
                priority = 'high'
            elif remaining_km <= 500:
                alert_type = 'maintenance_due'
                alert_message = (
                    f"Le vehicule {vehicle.license_plate} ({vehicle.brand} {vehicle.model}) "
                    f"atteindra son kilometrage de maintenance dans {remaining_km:.0f} km."
                )
                priority = 'high'

        # Check date-based maintenance
        if not alert_type and vehicle.last_maintenance_date and vehicle.maintenance_frequency_months:
            next_date = vehicle.next_maintenance_date
            if next_date:
                days_remaining = (next_date - today).days
                if days_remaining <= 0:
                    alert_type = 'maintenance_overdue'
                    alert_message = (
                        f"Le vehicule {vehicle.license_plate} ({vehicle.brand} {vehicle.model}) "
                        f"a depasse sa date de maintenance prevue du {next_date.strftime('%d/%m/%Y')}."
                    )
                    priority = 'urgent'
                elif days_remaining <= 14:
                    alert_type = 'maintenance_due'
                    alert_message = (
                        f"Le vehicule {vehicle.license_plate} ({vehicle.brand} {vehicle.model}) "
                        f"doit etre maintenu avant le {next_date.strftime('%d/%m/%Y')} "
                        f"(dans {days_remaining} jour{'s' if days_remaining > 1 else ''})."
                    )
                    priority = 'normal'

        if not alert_type:
            continue

        # Don't send duplicate alerts (check last 24h)
        recent_alert = UserNotification.objects.filter(
            vehicle=vehicle,
            notification_type__in=['maintenance_due', 'maintenance_overdue'],
            created_at__gte=timezone.now() - timedelta(hours=24),
        ).exists()

        if recent_alert:
            continue

        # Get admins/supervisors for this vehicle's organization
        users = User.objects.filter(
            organization=vehicle.organization,
            role__in=['admin', 'supervisor'],
            is_active=True,
        )

        title = (
            'Maintenance en retard' if alert_type == 'maintenance_overdue'
            else 'Maintenance a prevoir'
        )

        emails_to_send = []

        for user in users:
            prefs = getattr(user, 'preferences', None)
            if prefs and not prefs.maintenance_alerts:
                continue

            # Create in-app notification
            notification = UserNotification.objects.create(
                user=user,
                notification_type=alert_type,
                priority=priority,
                title=title,
                message=alert_message,
                vehicle=vehicle,
                data={
                    'vehicle_id': vehicle.id,
                    'vehicle_plate': vehicle.license_plate,
                    'alert_type': alert_type,
                },
            )

            # Send real-time via WebSocket
            try:
                NotificationService._send_realtime_notification(user.id, notification.to_dict())
            except Exception:
                pass

            if user.email:
                emails_to_send.append(user.email)

        # Send email
        if emails_to_send:
            try:
                send_mail(
                    subject=f'[YaswaCar] {title} - {vehicle.license_plate}',
                    message=(
                        f"Bonjour,\n\n{alert_message}\n\n"
                        f"Veuillez planifier une maintenance pour ce vehicule.\n\n"
                        f"-- YaswaCar"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=emails_to_send,
                    fail_silently=True,
                )
            except Exception as e:
                print(f"Erreur envoi email maintenance: {e}")

        alerts_sent += 1

    return f"{alerts_sent} alerte(s) de maintenance envoyee(s)"
