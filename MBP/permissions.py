from rest_framework.permissions import BasePermission
from .models import RoleModelPermission, AppModel, PermissionType

class HasModelPermission(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_superuser:
            return True

        role = getattr(request.user, 'role', None)
        if not role:
            return False

        model_name = getattr(view, 'model_name', None)
        permission_code = getattr(view, 'permission_code', None)

        if not model_name or not permission_code:
            return False

        try:
            model_obj = AppModel.objects.get(name=model_name)
            perm_type = PermissionType.objects.get(code=permission_code)
            return RoleModelPermission.objects.filter(
                role=role,
                model=model_obj,
                permission_type=perm_type
            ).exists()
        except (AppModel.DoesNotExist, PermissionType.DoesNotExist):
            return False