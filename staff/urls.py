from rest_framework.routers import DefaultRouter
from .views import StaffViewSet, AttendanceViewSet, PayrollViewSet
from django.urls import path, include

router = DefaultRouter()
router.register('staff', StaffViewSet, basename='staff')
router.register('attendance', AttendanceViewSet, basename='attendance')
router.register('payroll', PayrollViewSet, basename='payroll')


urlpatterns = [
    path('api/', include(router.urls)),
]
