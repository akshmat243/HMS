from rest_framework import serializers
from .models import *
import datetime


class ServiceCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceCategory
        fields = "__all__"
        lookup_field = "slug"


class GuestServiceSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=ServiceCategory.objects.all()
    )

    
    class Meta:
        model = GuestService
        fields = "__all__"
        lookup_field = "slug"

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than zero.")
        return value

    def validate_duration_minutes(self, value):
        if value <= 0:
            raise serializers.ValidationError("Duration must be greater than zero.")
        return value


class ServiceRequestSerializer(serializers.ModelSerializer):

    booking = serializers.SlugRelatedField(
        slug_field="booking_code",
        queryset=Booking.objects.all()
    )

    assigned_to = serializers.SlugRelatedField(
        slug_field="email",
        queryset=User.objects.all(),
        required=False,
        allow_null=True
    )

    # category = serializers.SlugRelatedField(
    #     slug_field="slug",
    #     queryset=ServiceCategory.objects.all()
    # )
    category = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=ServiceCategory.objects.all(),
        write_only=True
    )

    # READ ONLY FULL OBJECT
    category_detail = ServiceCategorySerializer(
        source="category",
        read_only=True
    )

    class Meta:
        model = ServiceRequest
        fields = "__all__"
        # lookup_field = "slug"
        read_only_fields = ["guest_name", "guest_room", "slug", "status"]

    def validate_cost(self, value):
        if value < 0:
            raise serializers.ValidationError("Cost cannot be negative.")
        return value
    
    def validate(self, data):
        booking = data.get("booking")


        if booking is None and self.instance is not None:
            booking = self.instance.booking

        # 3) If still None → this request is invalid
        if booking is None:
            raise serializers.ValidationError({
                "booking": "Booking is required."
            })

        # ----- Your existing validations -----

        # Guest must be checked-in / confirmed
        if booking.status not in ["confirmed", "checked_in"]:
            raise serializers.ValidationError(
                {"booking": "Guest is not checked in or confirmed. Cannot request services."}
            )

        # Stay date validation
        today = datetime.date.today()
        if not (booking.check_in <= today <= booking.check_out):
            raise serializers.ValidationError(
                {"booking": "Guest stay is not active. Cannot create service request."}
            )

        return data



class GuestProfileSerializer(serializers.Serializer):
    guest_name = serializers.CharField()
    room_number = serializers.CharField()
    check_in = serializers.DateField()
    check_out = serializers.DateField()
    total_spent = serializers.DecimalField(max_digits=10, decimal_places=2)
    satisfaction = serializers.FloatField()
    preferences = serializers.ListField(child=serializers.CharField(), allow_empty=True)
    booking_code = serializers.CharField()
    booking_slug = serializers.CharField()
