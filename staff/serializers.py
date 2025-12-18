from rest_framework import serializers
from .models import Staff, Attendance, Payroll, Leave, StaffDocument
from datetime import time
from django.contrib.auth import get_user_model
from Hotel.models import Hotel
from MBP.models import Role
User = get_user_model()
from django.core.mail import send_mail
from django.conf import settings
from datetime import datetime, timedelta


class AttendanceSerializer(serializers.ModelSerializer):
    staff_slug = serializers.SlugRelatedField(
        source='staff',
        slug_field='slug',
        queryset=Staff.objects.all(),
        write_only=True,
        required=False
    )

    staff_name = serializers.CharField(source='staff.user.get_full_name', read_only=True)

    class Meta:
        model = Attendance
        fields = ['id', 'staff_slug', 'staff_name', 'date', 'check_in', 'check_out', 'status']

    def create(self, validated_data):
        # ✅ If no staff is passed, use the logged-in user’s staff profile
        request = self.context.get('request')
        staff = validated_data.pop('staff', None)

        if not staff and request and hasattr(request.user, 'staff_profile'):
            staff = request.user.staff_profile
        elif not staff:
            raise serializers.ValidationError({"staff": "Staff must be provided or detected from user."})

        validated_data['staff'] = staff
        return super().create(validated_data)


class StaffDocumentSerializer(serializers.ModelSerializer):
    document_type_display = serializers.CharField(
        source="get_document_type_display", read_only=True
    )
    document_file_url = serializers.SerializerMethodField()

    class Meta:
        model = StaffDocument
        fields = [
            "id", "document_type", "document_type_display",
            "document_number", "document_file", "document_file_url",
            "issued_date", "expiry_date", "created_at"
        ]

    def get_document_file_url(self, obj):
        if obj.document_file:
            return obj.document_file.url
        return None

    def validate(self, data):
        # prevent duplicate document type for a staff
        staff = self.context.get("staff")
        doc_type = data.get("document_type")

        if staff and StaffDocument.objects.filter(staff=staff, document_type=doc_type).exists():
            raise serializers.ValidationError(
                {"document_type": "This document type is already uploaded for this staff."}
            )
        return data
from django.db import transaction
from django.utils.crypto import get_random_string

from django.db import transaction
from django.utils.crypto import get_random_string
from rest_framework import serializers


class StaffSerializer(serializers.ModelSerializer):

    # -------- incoming helpers --------
    hotel_slug = serializers.SlugField(write_only=True, required=False)
    role_slug = serializers.SlugField(write_only=True, required=False)

    full_name = serializers.CharField(write_only=True)
    email = serializers.EmailField(write_only=True)
    phone = serializers.CharField(write_only=True, required=False)

    # marker only (documents come from request.data)
    documents = serializers.ListField(write_only=True, required=False)

    # -------- outgoing --------
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    hotel = serializers.PrimaryKeyRelatedField(read_only=True)

    user_full_name = serializers.CharField(source="user.full_name", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_phone = serializers.CharField(source="user.phone", read_only=True)

    documents_data = StaffDocumentSerializer(
        source="documents",
        many=True,
        read_only=True
    )

    class Meta:
        model = Staff
        fields = [
            "id", "slug",

            # relations
            "user", "hotel",
            "user_full_name", "user_email", "user_phone",

            # user input
            "full_name", "email", "phone",

            # staff fields
            "designation", "department", "joining_date",
            "status", "shift_start", "shift_end",
            "monthly_salary", "profile_image",

            # helpers
            "hotel_slug", "role_slug",
            "documents", "documents_data",

            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "slug", "user", "hotel",
            "documents_data", "created_at", "updated_at"
        ]

    def validate(self, data):
        if data.get("monthly_salary", 0) < 0:
            raise serializers.ValidationError(
                {"monthly_salary": "Salary cannot be negative."}
            )

        ss = data.get("shift_start")
        se = data.get("shift_end")
        if ss and se and ss == se:
            raise serializers.ValidationError(
                {"shift_end": "Shift end cannot be equal to start."}
            )

        return data

    # -------------------------------------------------
    # CREATE USER + STAFF + DOCUMENTS
    # -------------------------------------------------
    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]

        # remove non-model helpers
        validated_data.pop("documents", None)
        hotel_slug = validated_data.pop("hotel_slug", None)
        role_slug = validated_data.pop("role_slug", None)

        # user fields
        full_name = validated_data.pop("full_name")
        email = validated_data.pop("email")
        phone = validated_data.pop("phone", None)

        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError({
                "email": "User with this email already exists."
            })

        raw_password = get_random_string(10)

        user = User.objects.create(
            full_name=full_name,
            email=email,
            phone=phone,
            is_active=True,
            is_email_verified=False,
            force_password_change=True
        )
        user.set_password(raw_password)

        # allow signal to send password
        user._raw_password = raw_password

        if role_slug:
            user.role = Role.objects.get(slug=role_slug)

        user.save()

        hotel = None
        if hotel_slug:
            hotel = Hotel.objects.get(slug=hotel_slug)

        staff = Staff.objects.create(
            user=user,
            hotel=hotel,
            **validated_data
        )

        # -------- create documents manually --------
        index = 0
        while True:
            prefix = f"documents[{index}]"
            if f"{prefix}[document_type]" not in request.data:
                break

            StaffDocument.objects.create(
                staff=staff,
                document_type=request.data.get(f"{prefix}[document_type]"),
                document_number=request.data.get(f"{prefix}[document_number]"),
                issued_date=request.data.get(f"{prefix}[issued_date]"),
                expiry_date=request.data.get(f"{prefix}[expiry_date]"),
                document_file=request.FILES.get(f"{prefix}[document_file]"),
            )
            index += 1

        return staff

    # -------------------------------------------------
    # UPDATE STAFF (NO DOCUMENT LOGIC HERE)
    # -------------------------------------------------
    @transaction.atomic
    def update(self, instance, validated_data):
        documents = validated_data.pop("documents", None)
        hotel_slug = validated_data.pop("hotel_slug", None)
        role_slug = validated_data.pop("role_slug", None)

        user = instance.user

        if "full_name" in validated_data:
            user.full_name = validated_data.pop("full_name")

        if "phone" in validated_data:
            user.phone = validated_data.pop("phone")

        if "email" in validated_data:
            new_email = validated_data.pop("email")
            if new_email != user.email:
                user.email = new_email
                user.is_email_verified = False

        if role_slug:
            user.role = Role.objects.get(slug=role_slug)

        user.save()

        if hotel_slug:
            instance.hotel = Hotel.objects.get(slug=hotel_slug)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        
        if documents is not None:
            instance.documents.all().delete()
            for doc in documents:
                serializer = StaffDocumentSerializer(
                    data=doc,
                    context={"staff": instance}
                )
                serializer.is_valid(raise_exception=True)
                serializer.save(staff=instance)

        instance.save()
        return instance




class PayrollSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source='staff.user.get_full_name', read_only=True)

    class Meta:
        model = Payroll
        fields = [
            'id', 'slug', 'staff', 'staff_name', 'salary_type',
            'base_salary', 'total_salary', 'month', 'year', 'created_at'
        ]
        read_only_fields = ['total_salary', 'slug', 'created_at']

    def validate(self, attrs):
        month = attrs.get('month')
        year = attrs.get('year')

        if not (1 <= month <= 12):
            raise serializers.ValidationError({"month": "Month must be between 1 and 12."})
        if year < 2000:
            raise serializers.ValidationError({"year": "Invalid year."})

        return attrs
    
class LeaveSerializer(serializers.ModelSerializer):
    staff_slug = serializers.SlugRelatedField(
        source='staff',
        slug_field='slug',
        queryset=Staff.objects.all(),
        write_only=True,
        required=False
    )
    staff_name = serializers.CharField(source='staff.user.get_full_name', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.get_full_name', read_only=True)

    class Meta:
        model = Leave
        fields = [
            'id', 'slug', 'staff_slug', 'staff_name',
            'start_date', 'end_date', 'reason',
            'status', 'approved_by_name', 'created_at'
        ]
        read_only_fields = ['slug', 'status', 'approved_by_name', 'created_at']

    def create(self, validated_data):
        request = self.context.get('request')
        staff = validated_data.pop('staff', None)
        if not staff and hasattr(request.user, 'staff_profile'):
            staff = request.user.staff_profile
        elif not staff:
            raise serializers.ValidationError({"staff": "Staff profile not found."})
        validated_data['staff'] = staff
        return super().create(validated_data)
