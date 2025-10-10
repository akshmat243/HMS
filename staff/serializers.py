from rest_framework import serializers
from .models import Staff, Attendance
from datetime import time


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
    user_full_name = serializers.CharField(source='user.get_full_name', read_only=True)
    performance_score = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    attendance_records = AttendanceSerializer(many=True, read_only=True)
    profile_image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = Staff
        fields = [
            'id', 'slug', 'user', 'user_full_name', 'hotel', 'designation',
            'department', 'joining_date', 'performance_score', 'status',
            'shift_start', 'shift_end', 'monthly_salary', 'profile_image',
            'attendance_records', 'created_at', 'updated_at'
        ]
        read_only_fields = ['slug', 'created_at', 'updated_at', 'performance_score']

    def validate(self, data):
        shift_start = data.get('shift_start')
        shift_end = data.get('shift_end')
        salary = data.get('monthly_salary', 0)

        if shift_start and shift_end and shift_start >= shift_end:
            raise serializers.ValidationError({"shift_end": "Shift end time must be after shift start time."})

        if salary < 0:
            raise serializers.ValidationError({"monthly_salary": "Monthly salary cannot be negative."})

        return data
