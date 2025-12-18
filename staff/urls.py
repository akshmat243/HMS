from rest_framework.routers import DefaultRouter
from .views import StaffViewSet, AttendanceViewSet, PayrollViewSet, LeaveViewSet, StaffDocumentViewSet
from django.urls import path, include

router = DefaultRouter()
router.register('staff', StaffViewSet, basename='staff')
router.register('attendance', AttendanceViewSet, basename='attendance')
router.register('payroll', PayrollViewSet, basename='payroll')
router.register('leave', LeaveViewSet, basename='leave')
router.register('staff-document', StaffDocumentViewSet, basename='staff-document')


urlpatterns = [
    path('api/', include(router.urls)),
]
