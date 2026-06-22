from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from datetime import timedelta


# Combien de minutes avant le depart on envoie le rappel anticipe.
REMINDER_BEFORE_MINUTES = 15
# Tolerance (en minutes) apres l'heure de depart pour rattraper le rappel
# "a l'heure" si un tick de Celery Beat a ete manque. Doit etre >= periode du
# beat (5 min) pour ne jamais rater un depart.
AT_START_GRACE_MINUTES = 10


@shared_task(bind=True, max_retries=3, default_retry_delay=30, ignore_result=True)
def send_driver_push_notification(self, notification_id):
    """Envoie (en asynchrone) le push Expo lie a une DriverNotification.

    Charge la notification puis delegue au service.
    """
    from apps.fleet.models import DriverNotification, NotificationService

    try:
        notification = DriverNotification.objects.select_related('driver').get(id=notification_id)
    except DriverNotification.DoesNotExist:
        return f"Notification {notification_id} introuvable"

    NotificationService._send_driver_push(notification)
    return f"Push traite pour notification {notification_id}"


def _send_reminder_once(mission, kind, minutes_before):
    """Envoie un rappel d'un 'kind' donne s'il n'a pas deja ete envoye.

    Retourne 1 si un rappel a ete envoye, 0 sinon.
    """
    from apps.fleet.models import DriverNotification, NotificationService

    already_sent = DriverNotification.objects.filter(
        mission=mission,
        notification_type='reminder',
        data__reminder_kind=kind,
    ).exists()
    if already_sent:
        return 0

    NotificationService.notify_mission_reminder(
        mission=mission,
        minutes_before=minutes_before,
        kind=kind,
    )
    return 1


@shared_task(ignore_result=True)
def send_mission_reminders():
    """Envoie deux rappels aux chauffeurs autour du depart de leur mission.

    - "before"   : ~REMINDER_BEFORE_MINUTES avant scheduled_start.
    - "at_start" : a l'heure exacte du depart (avec une tolerance pour rattraper
                   un tick de beat manque).

    Chaque type n'est envoye qu'une fois par mission (anti-doublon via
    data.reminder_kind). A planifier via Celery Beat (toutes les ~5 minutes).

    DESACTIVE PAR DEFAUT : les rappels de depart sont assures cote MOBILE
    (notifications locales programmees), qui fonctionnent app fermee sans
    process serveur. Activer SERVER_SIDE_MISSION_REMINDERS=True dans les settings
    seulement si l'on veut aussi un rappel push serveur (ex: couvrir le cas
    "app jamais ouverte") -- au risque de doublonner avec le rappel local.
    """
    from django.conf import settings
    from apps.fleet.models import Mission

    if not getattr(settings, 'SERVER_SIDE_MISSION_REMINDERS', False):
        return "Rappels serveur desactives (rappels locaux mobile utilises)"

    now = timezone.now()
    reminders_sent = 0

    # 1) Rappel anticipe : depart dans (now, now + REMINDER_BEFORE_MINUTES].
    before_window_end = now + timedelta(minutes=REMINDER_BEFORE_MINUTES)
    before_missions = Mission.objects.filter(
        status='assigned',
        driver__isnull=False,
        scheduled_start__gt=now,
        scheduled_start__lte=before_window_end,
    ).select_related('driver')
    for mission in before_missions:
        minutes_before = max(1, int((mission.scheduled_start - now).total_seconds() / 60))
        reminders_sent += _send_reminder_once(mission, 'before', minutes_before)

    # 2) Rappel a l'heure : depart dans (now - AT_START_GRACE_MINUTES, now].
    at_start_window_start = now - timedelta(minutes=AT_START_GRACE_MINUTES)
    at_start_missions = Mission.objects.filter(
        status='assigned',
        driver__isnull=False,
        scheduled_start__lte=now,
        scheduled_start__gt=at_start_window_start,
    ).select_related('driver')
    for mission in at_start_missions:
        reminders_sent += _send_reminder_once(mission, 'at_start', 0)

    return f"{reminders_sent} rappel(s) de mission envoye(s)"


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
