from rest_framework import viewsets
from .permissions import HasModelPermission
from .models import Role, AppModel, PermissionType, RoleModelPermission, AuditLog
from .serializers import (
    RoleSerializer,
    AppModelSerializer,
    PermissionTypeSerializer,
    RoleModelPermissionSerializer,
    AuditLogSerializer
)
from .utils import serialize_instance
from django.db.models.signals import post_save
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
import psutil
from django.utils.timesince import timesince
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()


class ProtectedModelViewSet(viewsets.ModelViewSet):
    model_name = None
    permission_code = 'r'
    permission_classes = [HasModelPermission]

    def get_permissions(self):
        if self.action == 'create':
            self.permission_code = 'c'
        elif self.action in ['update', 'partial_update']:
            self.permission_code = 'u'
        elif self.action == 'destroy':
            self.permission_code = 'd'
        else:
            self.permission_code = 'r'
        return [permission() for permission in self.permission_classes]

    def perform_create(self, serializer):
        serializer.context['request'] = self.request
        instance = serializer.save()
        instance._request_user = self.request.user
        post_save.send(sender=instance.__class__, instance=instance, created=True)
        # instance.save()

    def perform_update(self, serializer):
        instance = self.get_object()
        instance._old_data = serialize_instance(instance)
        instance._request_user = self.request.user
        updated_instance = serializer.save()
        updated_instance._request_user = self.request.user
        updated_instance._old_data = instance._old_data
        updated_instance.save()

    def perform_destroy(self, instance):
        instance._request_user = self.request.user
        instance.delete()


class RoleViewSet(ProtectedModelViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    model_name = 'Role'
    lookup_field = 'slug'


class AppModelViewSet(ProtectedModelViewSet):
    queryset = AppModel.objects.all()
    serializer_class = AppModelSerializer
    model_name = 'AppModel'
    lookup_field = 'slug'


class PermissionTypeViewSet(ProtectedModelViewSet):
    queryset = PermissionType.objects.all()
    serializer_class = PermissionTypeSerializer
    model_name = 'PermissionType'
    lookup_field = 'slug'


class RoleModelPermissionViewSet(ProtectedModelViewSet):
    queryset = RoleModelPermission.objects.select_related('role', 'model', 'permission_type').all()
    serializer_class = RoleModelPermissionSerializer
    model_name = 'RoleModelPermission'
    lookup_field = 'slug'


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only audit logs view with role-based data filtering.
    - Superusers → all logs
    - Admins → logs of users they created
    - Others → only their own logs
    Supports filters: ?user=email&action=create
    """
    queryset = AuditLog.objects.all().order_by('-timestamp')
    serializer_class = AuditLogSerializer
    model_name = 'AuditLog'
    permission_classes = [HasModelPermission]
    permission_code = 'r'

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()

        if not user.is_authenticated:
            return queryset.none()

        # Superusers see everything
        if user.is_superuser:
            return queryset

        # Normal users see their own logs and logs of users they created
        created_users = user.created_users.all()
        queryset = queryset.filter(Q(user=user) | Q(user__in=created_users))

        # Optional filters
        user_email = self.request.query_params.get("user")
        action = self.request.query_params.get("action")

        if user_email:
            queryset = queryset.filter(user__email__icontains=user_email)
        if action:
            queryset = queryset.filter(action__iexact=action)

        return queryset

    @action(detail=False, methods=["get"], url_path="recent")
    def recent_logs(self, request):
        """
        Returns 5 most recent activities with "time ago" format.
        """
        logs = self.get_queryset()[:5]
        data = [
            {
                "action": log.action,
                "details": log.details or "",
                "time_ago": timesince(log.timestamp, timezone.now()) + " ago",
                "user": log.user.full_name if log.user else None,
            }
            for log in logs
        ]
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="system-health", permission_classes=[])
    def system_health(self, request):
        """
        Returns current system health information for dashboard display.
        """
        cpu_usage = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        health_data = {
            "server_status": "Online" if cpu_usage < 90 else "High Load",
            "database": "Healthy",  # Optionally, add a DB connection check
            "ai_services": "Active",  # For AI/ML modules, can be checked via API ping
            "uptime": timesince(timezone.now() - timezone.timedelta(seconds=psutil.boot_time())),
            "cpu_usage": f"{cpu_usage}%",
            "memory_usage": f"{memory.percent}%",
            "disk_usage": f"{disk.percent}%",
        }
        return Response(health_data, status=status.HTTP_200_OK)
