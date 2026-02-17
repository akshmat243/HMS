from rest_framework import serializers

from Restaurant.models import Restaurant
from .models import Staff, Attendance, Payroll, Leave, StaffDocument, StaffAssignment
from django.utils.crypto import get_random_string
from accounts.signals import user_created_with_password
from datetime import time
from django.contrib.auth import get_user_model
from Hotel.models import Hotel
from MBP.models import Role
User = get_user_model()
from django.core.mail import send_mail
from datetime import date
from django.conf import settings
from accounts.signals import user_created_with_password
from django.db import transaction



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
        read_only_fields = ["id", "created_at"]

    def get_document_file_url(self, obj):
        return obj.document_file.url if obj.document_file else None

    def validate(self, data):
        staff = self.context.get("staff")
        doc_type = data.get("document_type")

        if staff and StaffDocument.objects.filter(
            staff=staff, document_type=doc_type
        ).exists():
            raise serializers.ValidationError(
                {"document_type": "This document type already exists for this staff."}
            )
        return data

class StaffAssignmentHistorySerializer(serializers.ModelSerializer):
    hotel_name = serializers.CharField(source="hotel.name", read_only=True)
    restaurant_name = serializers.CharField(source="restaurant.name", read_only=True)

    class Meta:
        model = StaffAssignment
        fields = [
            "id",
            "assignment_type",
            "hotel_name",
            "restaurant_name",
            "start_date",
            "end_date",
            "is_active",
        ]


class StaffSerializer(serializers.ModelSerializer):

    # -------- incoming helpers --------
    hotel_slug = serializers.SlugField(write_only=True, required=False)
    restaurant_slug = serializers.SlugField(write_only=True, required=False)
    role_slug = serializers.SlugField(write_only=True, required=False)

    full_name = serializers.CharField(write_only=True)
    email = serializers.EmailField(write_only=True)
    phone = serializers.CharField(write_only=True, required=False)

    documents = serializers.ListField(write_only=True, required=False)

    # -------- outgoing --------
    user = serializers.PrimaryKeyRelatedField(read_only=True)

    user_full_name = serializers.CharField(source="user.full_name", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_phone = serializers.CharField(source="user.phone", read_only=True)
    current_assignment = serializers.SerializerMethodField()

    documents_data = StaffDocumentSerializer(
        source="documents",
        many=True,
        read_only=True
    )

    class Meta:
        model = Staff
        fields = [
            "id", "slug",

            # user
            "user",
            "user_full_name", "user_email", "user_phone", "current_assignment",

            # input
            "full_name", "email", "phone",

            # staff
            "designation", "department", "joining_date",
            "status", "shift_start", "shift_end",
            "monthly_salary", "profile_image",

            # helpers
            "hotel_slug", "restaurant_slug", "role_slug",
            "documents", "documents_data",

            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "slug", "user",
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

    def get_current_assignment(self, obj):
        assignment = obj.assignments.filter(is_active=True).select_related(
            "hotel", "restaurant"
        ).first()

        if not assignment:
            return None

        return {
            "assignment_type": assignment.assignment_type,
            "hotel": assignment.hotel.name if assignment.hotel else None,
            "restaurant": assignment.restaurant.name if assignment.restaurant else None,
            "start_date": assignment.start_date,
        }

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]

        validated_data.pop("documents", None)
        hotel_slug = validated_data.pop("hotel_slug", None)
        restaurant_slug = validated_data.pop("restaurant_slug", None)
        role_slug = validated_data.pop("role_slug", None)

        full_name = validated_data.pop("full_name")
        email = validated_data.pop("email")
        phone = validated_data.pop("phone", None)

        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError({"email": "Email already exists."})

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

        if role_slug:
            user.role = Role.objects.get(slug=role_slug)

        user.save()

        user_created_with_password.send(
            sender=User,
            user=user,
            raw_password=raw_password
        )

        staff = Staff.objects.create(
            user=user,
            **validated_data
        )

        # ---------------- ASSIGNMENT ----------------
        if hotel_slug:
            hotel = Hotel.objects.get(slug=hotel_slug)
            StaffAssignment.objects.create(
                staff=staff,
                assignment_type="hotel",
                hotel=hotel,
                start_date=date.today(),
                is_active=True
            )

        if restaurant_slug:
            restaurant = Restaurant.objects.get(slug=restaurant_slug)
            StaffAssignment.objects.create(
                staff=staff,
                assignment_type="restaurant",
                restaurant=restaurant,
                start_date=date.today(),
                is_active=True
            )

        # ---------------- DOCUMENTS ----------------
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
    # UPDATE STAFF
    # -------------------------------------------------
    @transaction.atomic
    def update(self, instance, validated_data):
        documents = validated_data.pop("documents", None)
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

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        if documents is not None:
            instance.documents.all().delete()
            for doc in documents:
                serializer = StaffDocumentSerializer(
                    data=doc,
                    context={"staff": instance}
                )
                serializer.is_valid(raise_exception=True)
                serializer.save(staff=instance)

        return instance


class StaffAssignmentSerializer(serializers.ModelSerializer):
    hotel_name = serializers.CharField(source="hotel.name", read_only=True)
    restaurant_name = serializers.CharField(source="restaurant.name", read_only=True)

    class Meta:
        model = StaffAssignment
        fields = [
            "id",
            "assignment_type",
            "hotel",
            "hotel_name",
            "restaurant",
            "restaurant_name",
            "start_date",
            "end_date",
            "is_active",
        ]
        read_only_fields = ["id"]

    def validate(self, data):
        assignment_type = data.get("assignment_type")
        hotel = data.get("hotel")
        restaurant = data.get("restaurant")

        if assignment_type == "hotel" and not hotel:
            raise serializers.ValidationError(
                {"hotel": "Hotel is required for hotel assignment."}
            )

        if assignment_type == "restaurant" and not restaurant:
            raise serializers.ValidationError(
                {"restaurant": "Restaurant is required for restaurant assignment."}
            )

        if hotel and restaurant:
            raise serializers.ValidationError(
                "Assignment cannot have both hotel and restaurant."
            )

        return data


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












class StaffUserSerializer(serializers.Serializer):
    name = serializers.CharField()
    email = serializers.EmailField()


class StaffDashboardCardsSerializer(serializers.Serializer):
    assigned_tasks = serializers.IntegerField()
    pending_work = serializers.IntegerField()
    daily_activity = serializers.FloatField()
    notifications = serializers.IntegerField()


class StaffDashboardOverviewSerializer(serializers.Serializer):
    user = StaffUserSerializer()
    cards = StaffDashboardCardsSerializer()
    recent_notifications = serializers.ListField(child=serializers.DictField())