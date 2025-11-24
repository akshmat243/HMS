from rest_framework import routers
from django.urls import path, include
from .views import RoleViewSet, AppModelViewSet, PermissionTypeViewSet, RoleModelPermissionViewSet, AuditLogViewSet, RoleModelPermissionBulkViewSet

router = routers.DefaultRouter()
router.register(r'roles', RoleViewSet)
router.register(r'appmodels', AppModelViewSet)
router.register(r'permission-types', PermissionTypeViewSet)
router.register(r'role-permissions', RoleModelPermissionViewSet)
router.register("role-permissions-bulk", RoleModelPermissionBulkViewSet, basename='role-permissions-bulk')
router.register('logs', AuditLogViewSet, basename='auditlog')

urlpatterns = [
    path('api/', include(router.urls)),
]