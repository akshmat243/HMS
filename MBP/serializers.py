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
            'role_name', 'model_name', 'permission_name'
        ]

    def validate(self, data):
        role = data.get('role')
        model = data.get('model')
        permission = data.get('permission_type')
        exists = RoleModelPermission.objects.filter(
            role=role, model=model, permission_type=permission
        )
        if self.instance:
            exists = exists.exclude(id=self.instance.id)
        if exists.exists():
            raise serializers.ValidationError("Permission already assigned to this role for this model.")
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
