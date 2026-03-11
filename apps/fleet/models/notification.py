from django.db import models
from django.conf import settings
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import json


class DriverNotification(models.Model):
    """Modele representant une notification pour un conducteur"""

    NOTIFICATION_TYPE_CHOICES = [
        ('mission_assigned', 'Mission assignee'),
        ('mission_updated', 'Mission modifiee'),
        ('mission_cancelled', 'Mission annulee'),
        ('mission_started', 'Mission demarree'),
        ('mission_completed', 'Mission terminee'),
        ('alert', 'Alerte'),
        ('reminder', 'Rappel'),
        ('system', 'Systeme'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Basse'),
        ('normal', 'Normale'),
        ('high', 'Haute'),
        ('urgent', 'Urgente'),
    ]

    driver = models.ForeignKey(
        'fleet.Driver',
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='Conducteur'
    )

    notification_type = models.CharField(
        max_length=30,
        choices=NOTIFICATION_TYPE_CHOICES,
        verbose_name='Type de notification'
    )

    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default='normal',
        verbose_name='Priorite'
    )

    title = models.CharField(max_length=200, verbose_name='Titre')
    message = models.TextField(verbose_name='Message')

    # Reference optionnelle a une mission
    mission = models.ForeignKey(
        'fleet.Mission',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
        verbose_name='Mission'
    )

    # Donnees supplementaires (JSON)
    data = models.JSONField(
        null=True,
        blank=True,
        verbose_name='Donnees supplementaires'
    )

    # Statut de lecture
    is_read = models.BooleanField(
        default=False,
        verbose_name='Lu'
    )
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Lu a'
    )

    # Envoi push
    push_sent = models.BooleanField(
        default=False,
        verbose_name='Push envoye'
    )
    push_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Push envoye a'
    )

    # Metadata
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_driver_notifications',
        verbose_name='Cree par'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Date de creation')

    class Meta:
        db_table = 'driver_notifications'
        verbose_name = 'Notification conducteur'
        verbose_name_plural = 'Notifications conducteur'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['driver', 'is_read']),
            models.Index(fields=['notification_type', 'created_at']),
        ]

    def __str__(self):
        return f"{self.get_notification_type_display()} - {self.driver}"

    def mark_as_read(self):
        """Marquer la notification comme lue"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])


class UserNotification(models.Model):
    """Modele representant une notification pour un utilisateur (admin, superviseur, etc.)"""

    NOTIFICATION_TYPE_CHOICES = [
        # Incidents
        ('incident_reported', 'Incident signale'),
        ('incident_updated', 'Incident mis a jour'),
        ('incident_resolved', 'Incident resolu'),
        # Maintenance
        ('maintenance_due', 'Maintenance a prevoir'),
        ('maintenance_overdue', 'Maintenance en retard'),
        ('maintenance_completed', 'Maintenance terminee'),
        # Fuel
        ('fuel_low', 'Niveau carburant bas'),
        ('fuel_anomaly', 'Anomalie carburant'),
        # Missions
        ('mission_completed', 'Mission terminee'),
        ('mission_delayed', 'Mission en retard'),
        # Drivers
        ('driver_license_expiring', 'Permis conducteur expire bientot'),
        ('driver_document_expiring', 'Document conducteur expire bientot'),
        # Vehicles
        ('vehicle_insurance_expiring', 'Assurance vehicule expire bientot'),
        ('vehicle_inspection_due', 'Controle technique a prevoir'),
        # System
        ('alert', 'Alerte'),
        ('reminder', 'Rappel'),
        ('system', 'Systeme'),
        ('report_ready', 'Rapport disponible'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Basse'),
        ('normal', 'Normale'),
        ('high', 'Haute'),
        ('urgent', 'Urgente'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='Utilisateur'
    )

    notification_type = models.CharField(
        max_length=30,
        choices=NOTIFICATION_TYPE_CHOICES,
        verbose_name='Type de notification'
    )

    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default='normal',
        verbose_name='Priorite'
    )

    title = models.CharField(max_length=200, verbose_name='Titre')
    message = models.TextField(verbose_name='Message')

    # References optionnelles
    incident = models.ForeignKey(
        'fleet.Incident',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='user_notifications',
        verbose_name='Incident'
    )

    vehicle = models.ForeignKey(
        'fleet.Vehicle',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='user_notifications',
        verbose_name='Vehicule'
    )

    driver = models.ForeignKey(
        'fleet.Driver',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='user_notifications',
        verbose_name='Conducteur'
    )

    maintenance = models.ForeignKey(
        'fleet.MaintenanceRecord',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='user_notifications',
        verbose_name='Maintenance'
    )

    mission = models.ForeignKey(
        'fleet.Mission',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='user_notifications',
        verbose_name='Mission'
    )

    # Donnees supplementaires (JSON)
    data = models.JSONField(
        null=True,
        blank=True,
        verbose_name='Donnees supplementaires'
    )

    # Statut de lecture
    is_read = models.BooleanField(
        default=False,
        verbose_name='Lu'
    )
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Lu a'
    )

    # Email/SMS sent
    email_sent = models.BooleanField(default=False, verbose_name='Email envoye')
    sms_sent = models.BooleanField(default=False, verbose_name='SMS envoye')
    push_sent = models.BooleanField(default=False, verbose_name='Push envoye')

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Date de creation')

    class Meta:
        db_table = 'user_notifications'
        verbose_name = 'Notification utilisateur'
        verbose_name_plural = 'Notifications utilisateur'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['notification_type', 'created_at']),
            models.Index(fields=['user', 'notification_type', 'is_read']),
        ]

    def __str__(self):
        return f"{self.get_notification_type_display()} - {self.user}"

    def mark_as_read(self):
        """Marquer la notification comme lue"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

    def to_dict(self):
        """Convertir en dictionnaire pour WebSocket"""
        return {
            'id': self.id,
            'type': self.notification_type,
            'priority': self.priority,
            'title': self.title,
            'message': self.message,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat(),
            'data': self.data,
            'incident_id': self.incident_id,
            'vehicle_id': self.vehicle_id,
            'driver_id': self.driver_id,
            'maintenance_id': self.maintenance_id,
            'mission_id': self.mission_id,
        }


class NotificationService:
    """Service pour gerer l'envoi des notifications"""

    @staticmethod
    def _send_realtime_notification(user_id, notification_data):
        """Envoyer une notification en temps reel via WebSocket"""
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f'notifications_{user_id}',
                    {
                        'type': 'notification_message',
                        'notification': notification_data
                    }
                )
        except Exception as e:
            print(f"Error sending realtime notification: {e}")

    @staticmethod
    def notify_mission_assigned(mission, created_by=None):
        """Notifier le conducteur qu'une mission lui a ete assignee"""
        notification = DriverNotification.objects.create(
            driver=mission.driver,
            notification_type='mission_assigned',
            priority='high',
            title='Nouvelle mission assignee',
            message=f"La mission '{mission.title}' ({mission.mission_code}) vous a ete assignee. "
                    f"Depart prevu: {mission.scheduled_start.strftime('%d/%m/%Y a %H:%M')}.",
            mission=mission,
            data={
                'mission_id': mission.id,
                'mission_code': mission.mission_code,
                'origin': mission.origin_address,
                'destination': mission.destination_address,
                'scheduled_start': mission.scheduled_start.isoformat(),
                'vehicle_plate': mission.vehicle.license_plate if mission.vehicle else None,
            },
            created_by=created_by,
        )
        return notification

    @staticmethod
    def notify_mission_updated(mission, changes, created_by=None):
        """Notifier le conducteur que sa mission a ete modifiee"""
        changes_text = ', '.join(changes) if changes else 'des informations'
        return DriverNotification.objects.create(
            driver=mission.driver,
            notification_type='mission_updated',
            priority='normal',
            title='Mission modifiee',
            message=f"La mission '{mission.title}' ({mission.mission_code}) a ete modifiee. "
                    f"Changements: {changes_text}.",
            mission=mission,
            data={
                'mission_id': mission.id,
                'mission_code': mission.mission_code,
                'changes': changes,
            },
            created_by=created_by,
        )

    @staticmethod
    def notify_mission_cancelled(mission, reason, created_by=None):
        """Notifier le conducteur que sa mission a ete annulee"""
        return DriverNotification.objects.create(
            driver=mission.driver,
            notification_type='mission_cancelled',
            priority='urgent',
            title='Mission annulee',
            message=f"La mission '{mission.title}' ({mission.mission_code}) a ete annulee. "
                    f"Motif: {reason}.",
            mission=mission,
            data={
                'mission_id': mission.id,
                'mission_code': mission.mission_code,
                'cancellation_reason': reason,
            },
            created_by=created_by,
        )

    @staticmethod
    def notify_mission_reminder(mission, minutes_before, created_by=None):
        """Rappel avant le debut de la mission"""
        return DriverNotification.objects.create(
            driver=mission.driver,
            notification_type='reminder',
            priority='high',
            title='Rappel de mission',
            message=f"La mission '{mission.title}' ({mission.mission_code}) commence dans {minutes_before} minutes. "
                    f"Origine: {mission.origin_address}.",
            mission=mission,
            data={
                'mission_id': mission.id,
                'mission_code': mission.mission_code,
                'minutes_before': minutes_before,
            },
            created_by=created_by,
        )

    # === Notifications pour les admins/superviseurs ===

    @staticmethod
    def _send_incident_email(users_emails, incident):
        """Envoyer un email d'alerte incident aux admins"""
        from django.core.mail import send_mail
        from django.conf import settings

        if not users_emails:
            return

        severity_labels = {
            'minor': 'Mineur',
            'moderate': 'Modere',
            'major': 'Majeur',
            'critical': 'Critique',
        }
        severity_label = severity_labels.get(incident.severity, incident.severity)
        vehicle_plate = incident.vehicle.license_plate if incident.vehicle else 'N/A'
        driver_name = str(incident.driver) if incident.driver else 'N/A'
        incident_type = incident.get_incident_type_display()
        location = incident.address or f"{incident.latitude}, {incident.longitude}" if incident.latitude else 'Non specifie'

        subject = f"[ALERTE] Incident {severity_label} - {incident_type} - {vehicle_plate}"

        message = (
            f"Un nouvel incident a ete signale.\n\n"
            f"--- Details de l'incident ---\n"
            f"Type : {incident_type}\n"
            f"Gravite : {severity_label}\n"
            f"Titre : {incident.title}\n"
            f"Description : {incident.description}\n\n"
            f"--- Vehicule & Conducteur ---\n"
            f"Vehicule : {vehicle_plate}\n"
            f"Conducteur : {driver_name}\n\n"
            f"--- Localisation ---\n"
            f"Adresse : {location}\n\n"
            f"--- Date ---\n"
            f"Signale le : {incident.reported_at.strftime('%d/%m/%Y a %H:%M') if incident.reported_at else 'N/A'}\n\n"
            f"Connectez-vous a la plateforme pour plus de details et pour traiter cet incident."
        )

        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=users_emails,
                fail_silently=True,
            )
        except Exception as e:
            print(f"Erreur envoi email incident: {e}")

    @staticmethod
    def notify_incident_reported(incident, users=None):
        """Notifier les admins qu'un incident a ete signale (notification + email)"""
        from apps.accounts.models import User

        # Si pas d'utilisateurs specifies, notifier tous les admins de l'organisation
        if users is None:
            users = User.objects.filter(
                organization=incident.vehicle.organization if incident.vehicle else None,
                role__in=['admin', 'supervisor'],
                is_active=True
            )

        notifications = []
        emails_to_notify = []

        for user in users:
            # Verifier les preferences de l'utilisateur
            prefs = getattr(user, 'preferences', None)
            if prefs and not prefs.incident_alerts:
                continue

            notification = UserNotification.objects.create(
                user=user,
                notification_type='incident_reported',
                priority='high' if incident.severity in ['major', 'critical'] else 'normal',
                title=f'Nouvel incident signale',
                message=f"Un incident de type '{incident.get_incident_type_display()}' "
                        f"a ete signale pour le vehicule {incident.vehicle.license_plate if incident.vehicle else 'N/A'}.",
                incident=incident,
                vehicle=incident.vehicle,
                driver=incident.driver,
                data={
                    'incident_id': incident.id,
                    'incident_type': incident.incident_type,
                    'severity': incident.severity,
                    'vehicle_plate': incident.vehicle.license_plate if incident.vehicle else None,
                    'driver_name': str(incident.driver) if incident.driver else None,
                    'location': incident.location,
                },
            )
            notifications.append(notification)

            # Collecter les emails des admins
            if user.email:
                emails_to_notify.append(user.email)

            # Envoyer en temps reel via WebSocket
            NotificationService._send_realtime_notification(user.id, notification.to_dict())

        # Envoyer l'email d'alerte a tous les admins concernes
        NotificationService._send_incident_email(emails_to_notify, incident)

        return notifications

    @staticmethod
    def notify_incident_resolved(incident, users=None):
        """Notifier les admins qu'un incident a ete resolu"""
        from apps.accounts.models import User

        if users is None:
            users = User.objects.filter(
                organization=incident.vehicle.organization if incident.vehicle else None,
                role__in=['admin', 'supervisor'],
                is_active=True
            )

        notifications = []
        for user in users:
            prefs = getattr(user, 'preferences', None)
            if prefs and not prefs.incident_alerts:
                continue

            notification = UserNotification.objects.create(
                user=user,
                notification_type='incident_resolved',
                priority='low',
                title=f'Incident resolu',
                message=f"L'incident '{incident.get_incident_type_display()}' "
                        f"pour le vehicule {incident.vehicle.license_plate if incident.vehicle else 'N/A'} a ete resolu.",
                incident=incident,
                vehicle=incident.vehicle,
                data={
                    'incident_id': incident.id,
                    'incident_type': incident.incident_type,
                    'resolution_notes': incident.resolution_notes,
                    'estimated_cost': float(incident.estimated_cost) if incident.estimated_cost else None,
                },
            )
            notifications.append(notification)
            NotificationService._send_realtime_notification(user.id, notification.to_dict())

        return notifications

    @staticmethod
    def notify_maintenance_due(maintenance, users=None):
        """Notifier les admins qu'une maintenance est a prevoir"""
        from apps.accounts.models import User

        if users is None:
            users = User.objects.filter(
                organization=maintenance.vehicle.organization if maintenance.vehicle else None,
                role__in=['admin', 'supervisor'],
                is_active=True
            )

        notifications = []
        for user in users:
            prefs = getattr(user, 'preferences', None)
            if prefs and not prefs.maintenance_alerts:
                continue

            notification = UserNotification.objects.create(
                user=user,
                notification_type='maintenance_due',
                priority='normal',
                title=f'Maintenance a prevoir',
                message=f"Une maintenance '{maintenance.get_maintenance_type_display()}' "
                        f"est prevue pour le vehicule {maintenance.vehicle.license_plate}.",
                maintenance=maintenance,
                vehicle=maintenance.vehicle,
                data={
                    'maintenance_id': maintenance.id,
                    'maintenance_type': maintenance.maintenance_type,
                    'vehicle_plate': maintenance.vehicle.license_plate,
                    'scheduled_date': maintenance.scheduled_date.isoformat() if maintenance.scheduled_date else None,
                },
            )
            notifications.append(notification)
            NotificationService._send_realtime_notification(user.id, notification.to_dict())

        return notifications

    @staticmethod
    def notify_fuel_alert(vehicle, alert_type, message, users=None):
        """Notifier les admins d'une alerte carburant"""
        from apps.accounts.models import User

        if users is None:
            users = User.objects.filter(
                organization=vehicle.organization,
                role__in=['admin', 'supervisor'],
                is_active=True
            )

        notifications = []
        for user in users:
            prefs = getattr(user, 'preferences', None)
            if prefs and not prefs.fuel_alerts:
                continue

            notification = UserNotification.objects.create(
                user=user,
                notification_type=alert_type,
                priority='high',
                title=f'Alerte carburant',
                message=message,
                vehicle=vehicle,
                data={
                    'vehicle_id': vehicle.id,
                    'vehicle_plate': vehicle.license_plate,
                    'alert_type': alert_type,
                },
            )
            notifications.append(notification)
            NotificationService._send_realtime_notification(user.id, notification.to_dict())

        return notifications

    @staticmethod
    def notify_system(user, title, message, priority='normal', data=None):
        """Envoyer une notification systeme a un utilisateur"""
        notification = UserNotification.objects.create(
            user=user,
            notification_type='system',
            priority=priority,
            title=title,
            message=message,
            data=data,
        )
        NotificationService._send_realtime_notification(user.id, notification.to_dict())
        return notification

    @staticmethod
    def notify_all_admins(organization, title, message, notification_type='alert', priority='normal', data=None):
        """Envoyer une notification a tous les admins d'une organisation"""
        from apps.accounts.models import User

        users = User.objects.filter(
            organization=organization,
            role__in=['admin', 'supervisor'],
            is_active=True
        )

        notifications = []
        for user in users:
            notification = UserNotification.objects.create(
                user=user,
                notification_type=notification_type,
                priority=priority,
                title=title,
                message=message,
                data=data,
            )
            notifications.append(notification)
            NotificationService._send_realtime_notification(user.id, notification.to_dict())

        return notifications
