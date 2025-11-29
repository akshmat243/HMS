from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *
router = DefaultRouter()
router.register(r'tasks', MaintenanceTaskViewSet, basename='maintenance-tasks')
router.register(r'categories', MaintenanceCategoryViewSet, basename='maintenance-categories')
router.register(r'facilities', FacilityViewSet, basename='maintenance-facilities')
router.register(r'equipment', EquipmentViewSet, basename='maintenance-equipment')


urlpatterns = [
    path('api/maintenance/', include(router.urls)),
    path("api/maintenance/room-status/", RoomStatusView.as_view(), name="room-status"),
    path("api/maintenance/reports/", maintenance_reports, name="maintenance-reports"),
]