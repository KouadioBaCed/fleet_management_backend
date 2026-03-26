from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from django.utils import timezone

from apps.fleet.models.notification import DriverNotification, UserNotification
from apps.fleet.serializers.notification import (
    DriverNotificationSerializer,
    UserNotificationSerializer,
    NotificationListSerializer,
    MarkNotificationsReadSerializer
)
from apps.accounts.permissions import IsOrganizationMember


class UserNotificationViewSet(viewsets.ModelViewSet):
    """ViewSet pour gerer les notifications des utilisateurs (admin/superviseur)"""
    serializer_class = UserNotificationSerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]
    http_method_names = ['get', 'post', 'delete']

    def get_queryset(self):
        """Retourner uniquement les notifications de l'utilisateur connecte"""
        return UserNotification.objects.filter(
            user=self.request.user
        ).select_related('incident', 'vehicle', 'driver', 'maintenance', 'mission')

    def get_serializer_class(self):
        if self.action == 'list':
            return NotificationListSerializer
        return UserNotificationSerializer

    def list(self, request, *args, **kwargs):
        """Liste des notifications avec statistiques"""
        queryset = self.get_queryset()

        # Filtres
        is_read = request.query_params.get('is_read')
        if is_read is not None:
            queryset = queryset.filter(is_read=is_read.lower() == 'true')

        notification_type = request.query_params.get('type')
        if notification_type:
            queryset = queryset.filter(notification_type=notification_type)

        priority = request.query_params.get('priority')
        if priority:
            queryset = queryset.filter(priority=priority)

        # Tri et limite
        queryset = queryset.order_by('-created_at')
        limit = request.query_params.get('limit')
        if limit:
            try:
                queryset = queryset[:int(limit)]
            except ValueError:
                pass

        # Stats
        all_notifications = self.get_queryset()
        stats = {
            'total': all_notifications.count(),
            'unread': all_notifications.filter(is_read=False).count(),
            'by_priority': {
                'urgent': all_notifications.filter(priority='urgent', is_read=False).count(),
                'high': all_notifications.filter(priority='high', is_read=False).count(),
                'normal': all_notifications.filter(priority='normal', is_read=False).count(),
                'low': all_notifications.filter(priority='low', is_read=False).count(),
            }
        }

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'count': len(serializer.data),
            'stats': stats
        })

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Marquer une notification comme lue"""
        notification = self.get_object()
        notification.mark_as_read()
        return Response({
            'message': 'Notification marquee comme lue',
            'notification': UserNotificationSerializer(notification).data
        })

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Marquer toutes les notifications comme lues"""
        serializer = MarkNotificationsReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        notification_ids = serializer.validated_data.get('notification_ids')

        queryset = self.get_queryset().filter(is_read=False)
        if notification_ids:
            queryset = queryset.filter(id__in=notification_ids)

        count = queryset.count()
        queryset.update(is_read=True, read_at=timezone.now())

        return Response({
            'message': f'{count} notification(s) marquee(s) comme lue(s)',
            'count': count
        })

    @action(detail=False, methods=['delete'])
    def delete_read(self, request):
        """Supprimer toutes les notifications lues"""
        count = self.get_queryset().filter(is_read=True).delete()[0]
        return Response({
            'message': f'{count} notification(s) supprimee(s)',
            'count': count
        })

    @action(detail=False, methods=['get'])
    def unread(self, request):
        """Recuperer uniquement les notifications non lues"""
        queryset = self.get_queryset().filter(is_read=False).order_by('-created_at')

        limit = request.query_params.get('limit', 10)
        try:
            queryset = queryset[:int(limit)]
        except ValueError:
            queryset = queryset[:10]

        serializer = NotificationListSerializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'count': len(serializer.data)
        })

    @action(detail=False, methods=['get'])
    def count(self, request):
        """Compter les notifications non lues"""
        queryset = self.get_queryset()
        return Response({
            'total': queryset.count(),
            'unread': queryset.filter(is_read=False).count(),
            'urgent': queryset.filter(is_read=False, priority='urgent').count(),
            'high': queryset.filter(is_read=False, priority='high').count(),
        })


class DriverNotificationViewSet(viewsets.ModelViewSet):
    """ViewSet pour gerer les notifications des conducteurs"""
    serializer_class = DriverNotificationSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'delete']

    def get_queryset(self):
        """Retourner les notifications du conducteur associe a l'utilisateur"""
        user = self.request.user

        # Verifier si l'utilisateur est un conducteur
        from apps.fleet.models import Driver
        try:
            driver = Driver.objects.get(user=user)
            return DriverNotification.objects.filter(
                driver=driver
            ).select_related('mission', 'created_by')
        except Driver.DoesNotExist:
            return DriverNotification.objects.none()

    def list(self, request, *args, **kwargs):
        """Liste des notifications du conducteur"""
        queryset = self.get_queryset()

        # Filtres
        is_read = request.query_params.get('is_read')
        if is_read is not None:
            queryset = queryset.filter(is_read=is_read.lower() == 'true')

        notification_type = request.query_params.get('type')
        if notification_type:
            queryset = queryset.filter(notification_type=notification_type)

        queryset = queryset.order_by('-created_at')

        # Stats
        all_notifications = self.get_queryset()
        stats = {
            'total': all_notifications.count(),
            'unread': all_notifications.filter(is_read=False).count(),
        }

        serializer = DriverNotificationSerializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'count': len(serializer.data),
            'stats': stats
        })

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Marquer une notification comme lue"""
        notification = self.get_object()
        notification.mark_as_read()
        return Response({
            'message': 'Notification marquee comme lue',
            'notification': DriverNotificationSerializer(notification).data
        })

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Marquer toutes les notifications comme lues"""
        queryset = self.get_queryset().filter(is_read=False)
        count = queryset.count()
        queryset.update(is_read=True, read_at=timezone.now())

        return Response({
            'message': f'{count} notification(s) marquee(s) comme lue(s)',
            'count': count
        })

    @action(detail=False, methods=['get'])
    def unread(self, request):
        """Recuperer uniquement les notifications non lues"""
        queryset = self.get_queryset().filter(is_read=False).order_by('-created_at')[:20]
        serializer = DriverNotificationSerializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'count': len(serializer.data)
        })

    @action(detail=False, methods=['get'])
    def count(self, request):
        """Compter les notifications non lues"""
        queryset = self.get_queryset()
        return Response({
            'total': queryset.count(),
            'unread': queryset.filter(is_read=False).count(),
        })
