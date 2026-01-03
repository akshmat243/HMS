from rest_framework import serializers
from MBP.models import Role
from .models import UserModule
from django.utils.crypto import get_random_string
from .signals import user_created_with_password, user_registered
from django.contrib.auth import get_user_model

User = get_user_model()

class RegisterUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['id', 'email', 'full_name', 'phone', 'password']
        read_only_fields = ['id']

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_phone(self, value):
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError("A user with this phone number already exists.")
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.is_active = False
        user.is_email_verified = False
        user.is_phone_verified = True
        user.role = Role.objects.get_or_create(name="Customer")[0]
        user.created_by = None
        user.save()
        
        user_registered.send(
            sender=User,
            user=user
        )
        return user


class UserSerializer(serializers.ModelSerializer):

    role_slug = serializers.SlugField(write_only=True, required=False)
    role_name = serializers.CharField(source="role.name", read_only=True)

    password = serializers.CharField(write_only=True, required=False)

    modules = serializers.ListField(
        child=serializers.ChoiceField(choices=["hotel", "restaurant"]),
        write_only=True,
        required=False
    )
    
    created_by = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "full_name", "slug", "phone",
            "password", "role_slug", "role_name", "modules",
            "is_active", "date_joined", "created_by"
        ]
        read_only_fields = ["id", "date_joined", "created_by", "role_name", "modules"]

    def get_created_by(self, obj):
        return obj.created_by.email if obj.created_by else None

    def create(self, validated_data):
        request = self.context.get("request")
        creator = getattr(request, "user", None)

        password = validated_data.pop("password", None)
        role_slug = validated_data.pop("role_slug", None)
        modules = validated_data.pop("modules", []) 
        # raw_password = get_random_string(10) if not password else password

        role = None
        if role_slug:
            try:
                role = Role.objects.get(slug=role_slug)
            except Role.DoesNotExist:
                raise serializers.ValidationError({"role_slug": "Invalid role slug."})

        user = User(**validated_data)
        if creator and creator.is_authenticated:
            user.created_by = creator

        if password:
            user.set_password(password)
        user.force_password_change = True
        user.is_email_verified = False

        if role:
            user.role = role
        user.is_active = True

        user.save()
        
        for module in modules:
            UserModule.objects.create(user=user, module=module)
        
        raw_password = password  # Store raw password for signal
        
        user_created_with_password.send(
            sender=User,
            user=user,
            raw_password=raw_password
        )
                
        return user

    def update(self, instance, validated_data):

        password = validated_data.pop("password", None)
        role_slug = validated_data.pop("role_slug", None)
        modules = validated_data.pop("modules", None) 

        # Update all normal fields including is_active
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Update password
        if password:
            instance.set_password(password)

        # Update role
        if role_slug:
            try:
                role = Role.objects.get(slug=role_slug)
                instance.role = role
            except Role.DoesNotExist:
                raise serializers.ValidationError({"role_slug": "Invalid role slug."})

        instance.save()
        

        for module in modules:
            UserModule.objects.create(
                user=instance,
                module=module
            )
                
        return instance

class VerifyEmailAndResetPasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(min_length=8, write_only=True)
    confirm_password = serializers.CharField(min_length=8, write_only=True)

    def validate(self, data):
        user = self.context.get("user")

        if not user:
            raise serializers.ValidationError("User context is missing.")

        # ✅ check old password
        if not user.check_password(data["old_password"]):
            raise serializers.ValidationError({
                "old_password": "Old password is incorrect."
            })

        # ✅ check new vs confirm
        if data["new_password"] != data["confirm_password"]:
            raise serializers.ValidationError({
                "confirm_password": "Passwords do not match."
            })

        # ❌ prevent reusing same password
        if user.check_password(data["new_password"]):
            raise serializers.ValidationError({
                "new_password": "New password cannot be same as old password."
            })

        return data

    def save(self, user):
        user.set_password(self.validated_data["new_password"])
        user.is_email_verified = True
        user.force_password_change = False
        user.save()
        return user

