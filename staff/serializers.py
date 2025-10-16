from rest_framework import serializers
from .models import Staff, Attendance, Payroll, Leave
from datetime import time
from django.contrib.auth import get_user_model
from Hotel.models import Hotel
User = get_user_model()


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


class StaffSerializer(serializers.ModelSerializer):
    # ✅ Slug inputs (only these shown in POST)
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

    class Meta:
        model = Staff
        fields = [
            'id', 'slug', 'user_slug', 'hotel_slug', 'user', 'hotel',
            'user_full_name', 'user_email', 'user_phone',
            'designation', 'department', 'joining_date',
            'performance_score', 'status', 'shift_start', 'shift_end',
            'monthly_salary', 'profile_image', 'attendance_records',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'slug', 'created_at', 'updated_at', 'performance_score',
            'user', 'hotel'
        ]

    # ✅ Validation logic
    def validate(self, data):
        shift_start = data.get('shift_start')
        shift_end = data.get('shift_end')
        salary = data.get('monthly_salary', 0)

        if shift_start and shift_end and shift_start >= shift_end:
            raise serializers.ValidationError({"shift_end": "Shift end time must be after shift start time."})

        if salary < 0:
            raise serializers.ValidationError({"monthly_salary": "Monthly salary cannot be negative."})

        return data

    # ✅ Main Create Logic (Handles user creation + staff creation)
    def create(self, validated_data):
        user_slug = validated_data.pop('user_slug', None)
        hotel_slug = validated_data.pop('hotel_slug', None)

        # Try to get or create user
        try:
            user = User.objects.get(slug=user_slug)
        except User.DoesNotExist:
            # 🧠 If not found, auto-create user with minimal info (frontend can send same slug again)
            user = User.objects.create(
                slug=user_slug,
                username=user_slug,
                role='staff',  # or assign proper Role object if you have Role model
            )

        # Ensure user has 'staff' role
        if not user.role or str(user.role).lower() != 'staff':
            raise serializers.ValidationError({"user_slug": "User does not have 'staff' role."})

        # Get hotel
        hotel = None
        if hotel_slug:
            try:
                hotel = Hotel.objects.get(slug=hotel_slug)
            except Hotel.DoesNotExist:
                raise serializers.ValidationError({"hotel_slug": "Invalid hotel slug."})

        # Create staff profile
        staff = Staff.objects.create(user=user, hotel=hotel, **validated_data)
        return staff

    # ✅ Update logic
    def update(self, instance, validated_data):
        user_slug = validated_data.pop('user_slug', None)
        hotel_slug = validated_data.pop('hotel_slug', None)

        if user_slug:
            try:
                user = User.objects.get(slug=user_slug)
            except User.DoesNotExist:
                raise serializers.ValidationError({"user_slug": "Invalid user slug."})

            if not user.role or str(user.role).lower() != 'staff':
                raise serializers.ValidationError({"user_slug": "User does not have 'staff' role."})
            instance.user = user

        if hotel_slug:
            try:
                hotel = Hotel.objects.get(slug=hotel_slug)
                instance.hotel = hotel
            except Hotel.DoesNotExist:
                raise serializers.ValidationError({"hotel_slug": "Invalid hotel slug."})

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

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
