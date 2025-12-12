from rest_framework import serializers
from .models import Staff, Attendance, Payroll, Leave, StaffDocument
from datetime import time
from django.contrib.auth import get_user_model
from Hotel.models import Hotel
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



class StaffSerializer(serializers.ModelSerializer):
    # ✅ Slug inputs
    user_slug = serializers.SlugField(write_only=True, required=True)
    hotel_slug = serializers.SlugField(write_only=True, required=False, allow_null=True)

    # ✅ Read-only related fields
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    hotel = serializers.PrimaryKeyRelatedField(read_only=True)
    user_full_name = serializers.CharField(source='user.full_name', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_phone = serializers.CharField(source='user.phone', read_only=True)
    performance_score = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    attendance_records = AttendanceSerializer(many=True, read_only=True)
    profile_image = serializers.ImageField(required=False, allow_null=True)

    # ✅ Add writable user fields for update
    full_name = serializers.CharField(write_only=True, required=False)
    email = serializers.EmailField(write_only=True, required=False)
    phone = serializers.CharField(write_only=True, required=False)
    
    documents = StaffDocumentSerializer(many=True, write_only=True, required=False)
    documents_data = StaffDocumentSerializer(source="documents", many=True, read_only=True)

    class Meta:
        model = Staff
        fields = [
            'id', 'slug', 'user_slug', 'hotel_slug', 'user', 'hotel',
            'user_full_name', 'user_email', 'user_phone',
            'full_name', 'email', 'phone',
            'designation', 'department', 'joining_date',
            'performance_score', 'status', 'shift_start', 'shift_end',
            'monthly_salary', 'profile_image', 'attendance_records',
            'created_at', 'updated_at', 'documents', 'documents_data'
        ]
        read_only_fields = [
            'slug', 'created_at', 'updated_at', 'performance_score',
            'user', 'hotel', 'documents_data'
        ]

    def validate(self, data):
        shift_start = data.get('shift_start')
        shift_end = data.get('shift_end')
        salary = data.get('monthly_salary', 0)
        if shift_start and shift_end:
            # ✅ Allow overnight shifts (e.g., 20:00 to 06:00)
            if shift_start == shift_end:
                raise serializers.ValidationError({"shift_end": "Shift end time cannot be the same as shift start time."})
            
            # For clarity, we can normalize the times to a datetime object
            today = datetime.today()
            start_dt = datetime.combine(today, shift_start)
            end_dt = datetime.combine(today, shift_end)

            # ✅ If end time is earlier than start, assume it’s the next day (overnight)
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)
                
        if salary < 0:
            raise serializers.ValidationError({"monthly_salary": "Monthly salary cannot be negative."})
        return data

    def create(self, validated_data):
        documents_data = validated_data.pop("documents", [])
        user_slug = validated_data.pop('user_slug', None)
        hotel_slug = validated_data.pop('hotel_slug', None)

        try:
            user = User.objects.get(slug=user_slug)
        except User.DoesNotExist:
            user = User.objects.create(
                slug=user_slug,
                username=user_slug,
                role='staff',
            )

        if not user.role or str(user.role).lower() != 'staff':
            raise serializers.ValidationError({"user_slug": "User does not have 'staff' role."})

        hotel = None
        if hotel_slug:
            try:
                hotel = Hotel.objects.get(slug=hotel_slug)
            except Hotel.DoesNotExist:
                raise serializers.ValidationError({"hotel_slug": "Invalid hotel slug."})

        staff = Staff.objects.create(user=user, hotel=hotel, **validated_data)
        
        for doc in documents_data:
            StaffDocument.objects.create(staff=staff, **doc)
            
        return staff

    def update(self, instance, validated_data):
        documents_data = validated_data.pop("documents", None)
        user_slug = validated_data.pop('user_slug', None)
        hotel_slug = validated_data.pop('hotel_slug', None)

        # Extract possible user fields
        full_name = validated_data.pop('full_name', None)
        email = validated_data.pop('email', None)
        phone = validated_data.pop('phone', None)

        # Get or update related user
        user = instance.user
        if user_slug:
            try:
                user = User.objects.get(slug=user_slug)
            except User.DoesNotExist:
                raise serializers.ValidationError({"user_slug": "Invalid user slug."})

        email_changed = False
        if full_name:
            user.full_name = full_name
        if phone:
            user.phone = phone
        if email and email != user.email:
            email_changed = True
            user.email = email
            if hasattr(user, 'is_email_verified'):
                user.is_email_verified = False

        user.save()

        # ✅ Send verification email if email changed
        if email_changed:
            send_mail(
                subject="Verify Your Email",
                message=f"Hi {user.full_name},\n\nPlease verify your new email address.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )

        if hotel_slug:
            try:
                instance.hotel = Hotel.objects.get(slug=hotel_slug)
            except Hotel.DoesNotExist:
                raise serializers.ValidationError({"hotel_slug": "Invalid hotel slug."})

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        if documents_data is not None:
            instance.documents.all().delete()
            for doc in documents_data:
                StaffDocument.objects.create(staff=instance, **doc)

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
