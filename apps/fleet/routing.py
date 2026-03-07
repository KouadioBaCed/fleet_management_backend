from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/tracking/(?P<trip_id>\d+)/$', consumers.TripTrackingConsumer.as_asgi()),
    re_path(r'ws/live-map/$', consumers.LiveTrackingConsumer.as_asgi()),
]
