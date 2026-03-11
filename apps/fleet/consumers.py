import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async


class LiveTrackingConsumer(AsyncWebsocketConsumer):
    """Consumer pour le suivi en temps réel de tous les véhicules"""

    async def connect(self):
        # Rejoindre le groupe "live_map"
        await self.channel_layer.group_add("live_map", self.channel_name)
        await self.accept()

        # Envoyer un message de confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connecté au suivi en temps réel'
        }))

        # Envoyer les données initiales des véhicules actifs
        initial_data = await self.get_active_vehicles()
        await self.send(text_data=json.dumps({
            'type': 'initial_data',
            'vehicles': initial_data
        }))

    async def disconnect(self, close_code):
        # Quitter le groupe
        await self.channel_layer.group_discard("live_map", self.channel_name)

    async def receive(self, text_data):
        """Recevoir des messages du client"""
        data = json.loads(text_data)
        message_type = data.get('type')

        if message_type == 'request_refresh':
            # Le client demande une actualisation des données
            vehicles = await self.get_active_vehicles()
            await self.send(text_data=json.dumps({
                'type': 'refresh_data',
                'vehicles': vehicles
            }))

    async def position_update(self, event):
        """Envoyer la mise à jour de position au client"""
        await self.send(text_data=json.dumps({
            'type': 'position_update',
            **event['data']
        }))

    @database_sync_to_async
    def get_active_vehicles(self):
        """Récupérer tous les véhicules avec des missions en cours"""
        from apps.fleet.models import Mission, GPSLocationPoint
        from django.utils import timezone

        now = timezone.now()
        active_missions = Mission.objects.filter(
            status='in_progress'
        ).select_related('vehicle', 'driver', 'driver__user')

        vehicles = []
        for mission in active_missions:
            # Récupérer la dernière position GPS
            current_position = None
            last_update = None

            if hasattr(mission, 'trip') and mission.trip:
                last_point = GPSLocationPoint.objects.filter(
                    trip=mission.trip
                ).order_by('-recorded_at').first()

                if last_point:
                    current_position = {
                        'latitude': float(last_point.latitude),
                        'longitude': float(last_point.longitude),
                        'speed': float(last_point.speed),
                        'heading': float(last_point.heading) if last_point.heading else None,
                        'is_moving': last_point.is_moving,
                        'battery_level': last_point.battery_level,
                    }
                    last_update = last_point.recorded_at.isoformat()

            # Fallback: utiliser la position d'origine si pas de point GPS
            if current_position is None and mission.origin_latitude and mission.origin_longitude:
                current_position = {
                    'latitude': float(mission.origin_latitude),
                    'longitude': float(mission.origin_longitude),
                    'speed': 0,
                    'heading': None,
                    'is_moving': False,
                    'battery_level': None,
                }
                last_update = mission.actual_start.isoformat() if mission.actual_start else (
                    mission.scheduled_start.isoformat() if mission.scheduled_start else None
                )

            # Calculer le statut de retard
            delay_status = self._calculate_delay(mission, now)

            vehicles.append({
                'mission_id': mission.id,
                'mission_code': mission.mission_code,
                'title': mission.title,
                'status': mission.status,
                'priority': mission.priority,
                'driver_name': f"{mission.driver.user.first_name} {mission.driver.user.last_name}",
                'driver_phone': getattr(mission.driver, 'phone_number', None),
                'vehicle_id': mission.vehicle.id,
                'vehicle_plate': mission.vehicle.license_plate,
                'vehicle_brand': mission.vehicle.brand,
                'vehicle_model': mission.vehicle.model,
                'position': current_position,
                'last_update': last_update,
                'origin': {
                    'latitude': float(mission.origin_latitude),
                    'longitude': float(mission.origin_longitude),
                    'address': mission.origin_address,
                },
                'destination': {
                    'latitude': float(mission.destination_latitude),
                    'longitude': float(mission.destination_longitude),
                    'address': mission.destination_address,
                },
                'scheduled_start': mission.scheduled_start.isoformat() if mission.scheduled_start else None,
                'scheduled_end': mission.scheduled_end.isoformat() if mission.scheduled_end else None,
                'actual_start': mission.actual_start.isoformat() if mission.actual_start else None,
                'delay_status': delay_status,
            })

        return vehicles

    def _calculate_delay(self, mission, now):
        """Calculer le statut de retard d'une mission"""
        delay_minutes = 0
        delay_type = None
        is_delayed = False

        if mission.status == 'in_progress' and mission.scheduled_end:
            if now > mission.scheduled_end:
                delay_minutes = int((now - mission.scheduled_end).total_seconds() / 60)
                delay_type = 'arrival'
                is_delayed = True

        severity = 'none'
        if delay_minutes > 30:
            severity = 'critical'
        elif delay_minutes > 15:
            severity = 'warning'
        elif delay_minutes > 5:
            severity = 'info'

        return {
            'is_delayed': is_delayed,
            'delay_type': delay_type,
            'delay_minutes': delay_minutes,
            'severity': severity,
        }


class NotificationConsumer(AsyncWebsocketConsumer):
    """Consumer pour les notifications en temps reel des utilisateurs"""

    async def connect(self):
        user = self.scope.get('user')
        if user and user.is_authenticated:
            self.group_name = f'notifications_{user.id}'
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            await self.send(text_data=json.dumps({
                'type': 'connection_established',
                'message': 'Connecte aux notifications'
            }))

            # Envoyer le nombre de notifications non lues
            unread_count = await self.get_unread_count(user.id)
            await self.send(text_data=json.dumps({
                'type': 'unread_count',
                'count': unread_count
            }))
        else:
            await self.close()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notification_message(self, event):
        """Recevoir et transmettre une notification au client"""
        await self.send(text_data=json.dumps({
            'type': 'new_notification',
            'notification': event['notification']
        }))

    @database_sync_to_async
    def get_unread_count(self, user_id):
        from apps.fleet.models.notification import UserNotification
        return UserNotification.objects.filter(user_id=user_id, is_read=False).count()


class TripTrackingConsumer(AsyncWebsocketConsumer):
    """Consumer pour le suivi d'un trajet spécifique"""

    async def connect(self):
        self.trip_id = self.scope['url_route']['kwargs']['trip_id']
        self.room_group_name = f'trip_{self.trip_id}'

        # Rejoindre le groupe du trajet
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # Envoyer un message de confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': f'Connecté au suivi du trajet {self.trip_id}'
        }))

    async def disconnect(self, close_code):
        # Quitter le groupe
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        """Recevoir des messages du client"""
        data = json.loads(text_data)
        # Traiter les messages si nécessaire

    async def trip_update(self, event):
        """Envoyer la mise à jour du trajet au client"""
        await self.send(text_data=json.dumps(event['data']))
