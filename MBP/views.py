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
from rest_framework import serializers

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
    
    def get_queryset(self):
        user = self.request.user
        
        # Superuser → Full access
        if user.is_superuser:
            return super().get_queryset()

        # Hotel admin → Can manage permissions only for roles under his hotel
        if getattr(user, "role", None) and user.role.name.lower() == "admin":
            return RoleModelPermission.objects.filter(
                role__hotel=user.hotel  # <-- Only his hotel roles
            )

        # Others: No access
        return RoleModelPermission.objects.none()
    
    def create(self, validated_data):
        user = self.context["request"].user

        if not user.is_superuser:
            if user.role.name.lower() != "admin":
                raise serializers.ValidationError("You cannot create roles.")
            validated_data["hotel"] = user.hotel  # Force hotel admin's hotel

        return super().create(validated_data)

    
    # @action(detail=False, methods=["post"], url_path="bulk-assign")
    # def bulk_assign(self, request):

        permissions = request.data.get("permissions", [])

        created = []
        duplicates = []
        errors = []

        for perm_data in permissions:
            # Check if already exists BEFORE serializer validation
            role = perm_data.get("role")
            model = perm_data.get("model")
            permission_type = perm_data.get("permission_type")

            if RoleModelPermission.objects.filter(
                role__slug=role,
                model__slug=model,
                permission_type__slug=permission_type
            ).exists():
                duplicates.append(perm_data)
                continue   # SKIP

            serializer = self.get_serializer(data=perm_data, context={"request": request})
            if serializer.is_valid():
                serializer.save()
                created.append(serializer.data)
            else:
                errors.append(serializer.errors)

        return Response({
            "created": created,
            "duplicates": duplicates,
            "errors": errors,
        })

    @action(detail=False, methods=["post"], url_path="bulk-assign")
    def bulk_assign(self, request):
        permissions = request.data.get("permissions", [])

        created = []
        skipped = []
        errors = []

        for perm_data in permissions:
            role_slug = perm_data.get("role")
            model_slug = perm_data.get("model")
            perm_slug = perm_data.get("permission_type")

            try:
                role = Role.objects.get(slug=role_slug)
                model = AppModel.objects.get(slug=model_slug)
                ptype = PermissionType.objects.get(slug=perm_slug)
            except Exception as e:
                errors.append({"input": perm_data, "error": str(e)})
                continue

            # check exists
            obj, created_flag = RoleModelPermission.objects.get_or_create(
                role=role,
                model=model,
                permission_type=ptype
            )

            if created_flag:
                created.append(RoleModelPermissionSerializer(obj).data)
            else:
                skipped.append(RoleModelPermissionSerializer(obj).data)

        return Response({
            "created": created,
            "skipped": skipped,
            "errors": errors
        })

from .serializers import RolePermissionAssignSerializer
class RoleModelPermissionBulkViewSet(ProtectedModelViewSet):
    serializer_class = RolePermissionAssignSerializer
    model_name = "RoleModelPermission"

    def get_queryset(self):
        return RoleModelPermission.objects.all()  # Bulk does not use queryset

    @action(detail=False, methods=['post'], url_path='create')
    def bulk_create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.bulk_create(serializer.validated_data)
        return Response(result)

    @action(detail=False, methods=['put'], url_path='update')
    def bulk_update(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.bulk_update(serializer.validated_data)
        return Response(result)

    @action(detail=False, methods=['delete'], url_path='delete')
    def bulk_delete(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.bulk_delete(serializer.validated_data)
        return Response(result)


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
