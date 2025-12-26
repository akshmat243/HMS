from rest_framework.routers import DefaultRouter
from .views import StaffViewSet, AttendanceViewSet, PayrollViewSet, LeaveViewSet, StaffDocumentViewSet , StaffDashboardViewSet
from django.urls import path, include

router = DefaultRouter()
router.register('staff', StaffViewSet, basename='staff')
router.register('attendance', AttendanceViewSet, basename='attendance')
router.register('payroll', PayrollViewSet, basename='payroll')
router.register('leave', LeaveViewSet, basename='leave')
router.register('staff-document', StaffDocumentViewSet, basename='staff-document')
router.register('staff-dashboard', StaffDashboardViewSet, basename='staff-dashboard')



urlpatterns = [
    path('api/', include(router.urls)),
]
