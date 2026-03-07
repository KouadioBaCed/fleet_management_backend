from django.urls import path
from .views import (
    DashboardStatsView,
    ActivityListView,
    ActivityTypesView,
    DriverRankingView,
    TopPerformersView,
    DriverPerformanceDetailView,
)

urlpatterns = [
    path('dashboard/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('activities/', ActivityListView.as_view(), name='activity-list'),
    path('activities/types/', ActivityTypesView.as_view(), name='activity-types'),
    path('drivers/ranking/', DriverRankingView.as_view(), name='driver-ranking'),
    path('drivers/top/', TopPerformersView.as_view(), name='top-performers'),
    path('drivers/<int:driver_id>/performance/', DriverPerformanceDetailView.as_view(), name='driver-performance'),
]
