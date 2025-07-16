from rest_framework import serializers
from .models import Role, AppModel, PermissionType, RoleModelPermission, AuditLog

class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = '__all__'

class AppModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppModel
        fields = '__all__'

class PermissionTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PermissionType
        fields = '__all__'

class RoleModelPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoleModelPermission
        fields = '__all__'

class AuditLogSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    action_display = serializers.CharField(source='get_action_display', read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            'id',
            'user_email',
            'action',
            'action_display',
            'model_name',
            'object_id',
            'details',
            'old_data',
            'new_data',
            'ip_address',
            'user_agent',
            'timestamp',
        ]