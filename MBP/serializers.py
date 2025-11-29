from rest_framework import serializers
from .models import Role, AppModel, PermissionType, RoleModelPermission, AuditLog


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['id', 'name', 'slug', 'description']
        read_only_fields = ['slug']

    def validate_name(self, value):
        qs = Role.objects.exclude(id=self.instance.id) if self.instance else Role.objects.all()
        if qs.filter(name=value).exists():
            raise serializers.ValidationError("A role with this name already exists.")
        return value


class AppModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppModel
        fields = ['id', 'name', 'slug', 'verbose_name', 'description', 'app_label']
        read_only_fields = ['slug']

    def validate_name(self, value):
        qs = AppModel.objects.exclude(id=self.instance.id) if self.instance else AppModel.objects.all()
        if qs.filter(name=value).exists():
            raise serializers.ValidationError("A model with this name already exists.")
        return value


class PermissionTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PermissionType
        fields = ['id', 'name', 'slug', 'code']
        read_only_fields = ['slug']

    def validate_code(self, value):
        allowed_codes = ['c', 'r', 'u', 'd']
        if value not in allowed_codes:
            raise serializers.ValidationError("Code must be one of 'c', 'r', 'u', 'd'.")
        return value

    def validate_name(self, value):
        qs = PermissionType.objects.exclude(id=self.instance.id) if self.instance else PermissionType.objects.all()
        if qs.filter(name=value).exists():
            raise serializers.ValidationError("Permission type with this name already exists.")
        return value


class RoleModelPermissionSerializer(serializers.ModelSerializer):
    
    role = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Role.objects.all()
    )
    model = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=AppModel.objects.all()
    )
    permission_type = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=PermissionType.objects.all()
    )
    
    role_name = serializers.CharField(source='role.name', read_only=True)
    model_name = serializers.CharField(source='model.name', read_only=True)
    permission_name = serializers.CharField(source='permission_type.name', read_only=True)

    class Meta:
        model = RoleModelPermission
        fields = [
            'id', 'role', 'model', 'permission_type',
            'role_name', 'model_name', 'permission_name', 'slug'
        ]

    def validate(self, data):
        request = self.context["request"]
        user = request.user

        role = data.get("role")
        model = data.get("model")
        permission = data.get("permission_type")

        # Prevent duplicate
        exists = RoleModelPermission.objects.filter(
            role=role, model=model, permission_type=permission
        )
        if self.instance:
            exists = exists.exclude(id=self.instance.id)

        if exists.exists():
            raise serializers.ValidationError("Permission already assigned.")

        # HOTEL ADMIN RESTRICTIONS
        if not user.is_superuser:
            # Only admin allowed
            if not hasattr(user, 'role') or user.role.name.lower() != "admin":
                raise serializers.ValidationError(
                    "You do not have permission to assign permissions."
                )

            # Role must belong to same hotel
            if role.hotel != user.hotel:
                raise serializers.ValidationError(
                    "You can assign permissions only to roles inside your hotel."
                )

            # prevent assigning dangerous permissions
            if permission.code in ["superuser", "manage_system"]:
                raise serializers.ValidationError(
                    "You cannot assign system-level permissions."
                )

            # prevent modifying models the admin does not own
            hotel_allowed_models = ["Room", "Booking", "Staff", "RestaurantOrder", "RoomServiceRequest"]
            if model.name not in hotel_allowed_models:
                raise serializers.ValidationError(
                    f"Hotel Admin cannot assign permissions for model: {model.name}"
                )

        return data

    


class AuditLogSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            'id', 'user', 'user_email', 'action', 'model_name',
            'object_id', 'details', 'old_data', 'new_data',
            'ip_address', 'user_agent', 'timestamp'
        ]
        read_only_fields = fields

from django.utils.text import slugify
class RolePermissionAssignSerializer(serializers.Serializer):
    # For CREATE and UPDATE
    role_name = serializers.CharField(required=False)
    permissions = serializers.ListField(required=False)

    # For DELETE or updating specific entries
    slugs = serializers.ListField(required=False)

    def validate(self, data):
        # Validate role (only required for create/update)
        if "role_name" in data:
            role_name = data["role_name"]

            role = Role.objects.filter(name__iexact=role_name).first()
            if not role:
                role = Role.objects.create(
                    name=role_name,
                    slug=slugify(role_name)
                )
            data["role"] = role

        return data

    # ------------------------------------------------------------
    # BULK CREATE (role_name + model_slug + permission_slugs)
    # ------------------------------------------------------------
    def bulk_create(self, validated_data):
        role = validated_data["role"]
        blocks = validated_data["permissions"]
        
        if not blocks:
            raise serializers.ValidationError({"permissions": "Permissions list cannot be empty."})

        created_slugs = []

        for block in blocks:
            model_slug = block["model_slug"]
            perm_slugs = block["permission_slugs"]

            app_model = AppModel.objects.get(slug=model_slug)
            
            if not app_model:
                raise serializers.ValidationError(
                    {"model_slug": f"Invalid model slug: {model_slug}. This model does not exist."}
                )

            for code in perm_slugs:
                perm = PermissionType.objects.get(code=code)
                
                if not perm:
                    raise serializers.ValidationError(
                        {"permission_slugs": f"Invalid permission: {code}"}
                    )

                obj, created = RoleModelPermission.objects.get_or_create(
                    role=role,
                    model=app_model,
                    permission_type=perm
                )
                if created:
                    created_slugs.append(obj.slug)

        return {"created": created_slugs}

    # ------------------------------------------------------------
    # BULK UPDATE (incremental — add/remove permissions)
    # ------------------------------------------------------------
    def bulk_update(self, validated_data):
        role = validated_data["role"]
        blocks = validated_data["permissions"]

        updated_slugs = []
        removed_slugs = []
        
        if not blocks:
            raise serializers.ValidationError({"permissions": "Permissions list cannot be empty."})

        for block in blocks:
            model_slug = block["model_slug"]
            new_codes = block["permission_slugs"]

            app_model = AppModel.objects.get(slug=model_slug)
            if not app_model:
                raise serializers.ValidationError(
                    {"model_slug": f"Invalid model slug: {model_slug}. This model does not exist."}
                )

            # Existing permissions for that role + model
            existing = RoleModelPermission.objects.filter(role=role, model=app_model)
            existing_codes = {p.permission_type.code: p for p in existing}

            # Add missing permissions
            for code in new_codes:
                if code not in existing_codes:
                    perm = PermissionType.objects.get(code=code)
                    
                    if not perm:
                        raise serializers.ValidationError(
                            {"permission_slugs": f"Invalid permission: {code}"}
                        )
                        
                    obj = RoleModelPermission.objects.create(
                        role=role, model=app_model, permission_type=perm
                    )
                    updated_slugs.append(obj.slug)

            # Remove permissions not needed anymore
            for code, obj in existing_codes.items():
                if code not in new_codes:
                    removed_slugs.append(obj.slug)
                    obj.delete()

        return {"updated": updated_slugs, "removed": removed_slugs}

    # ------------------------------------------------------------
    # BULK DELETE using slugs
    # ------------------------------------------------------------
    def bulk_delete(self, validated_data):
        slugs = validated_data["slugs"]
        removed = []
        
        if not slugs:
            raise serializers.ValidationError({"slugs": "List of slugs cannot be empty."})

        for slug in slugs:
            try:
                obj = RoleModelPermission.objects.get(slug=slug)
                obj.delete()
                removed.append(slug)
            except RoleModelPermission.DoesNotExist:
                continue

        return {"deleted": removed}
    

# {
#   "role_name": "Admin",
#   "permissions": [
#     {
#       "model_slug": "user",
#       "permission_slugs": ["c", "r", "u"]
#     },
#     {
#       "model_slug": "hotel",
#       "permission_slugs": ["r"]
#     },
#     {
#       "model_slug": "booking",
#       "permission_slugs": ["c", "r"]
#     }
#   ]
# }
