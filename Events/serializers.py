# events/serializers.py
from rest_framework import serializers
from .models import Venue, Event, EventType # Event_Booking as Booking
from django.utils import timezone
from django.db import models
from decimal import Decimal


class VenueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Venue
        fields = [
            "id", "name", "slug", "kind", "capacity", "hourly_rate", "features",
            "is_active", "created_by", "created_at"
        ]
        read_only_fields = ["created_by", "created_at"]

    def validate_capacity(self, value):
        if value < 0:
            raise serializers.ValidationError("Capacity cannot be negative.")
        return value

    def validate_hourly_rate(self, value):
        if value < 0:
            raise serializers.ValidationError("Hourly rate cannot be negative.")
        return value

    def validate_features(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Features must be a list.")
        return value

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Venue name cannot be empty.")
        return value


class EventTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventType
        fields = ["id", "name", "slug"]

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Event type name cannot be empty.")
        return value


class EventListSerializer(serializers.ModelSerializer):
    # venue = VenueSerializer(read_only=True)
    event_type = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=EventType.objects.all()
    )
    created_by = serializers.SerializerMethodField()


    venue = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=Venue.objects.all()
    )

    
    # capacity_percent = serializers.FloatField(source="capacity_percent", read_only=True)
    capacity_percent = serializers.FloatField(read_only=True)
    payment_percent = serializers.FloatField(read_only=True)

    # payment_percent = serializers.FloatField(source="payment_percent", read_only=True)
    # bookings_count = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id", "title", "slug", "description","event_type", "venue",
            "start_datetime", "end_datetime", "expected_guests", "venue_capacity",
            "capacity_percent", "payment_percent", "deposit_amount", "total_price",
            "contact_name", "contact_phone", "tags", "status", 
            "created_by", "created_at"  #"bookings_count",
        ]
        read_only_fields = ["created_by", "created_at"]


    def get_created_by(self, obj):
        if obj.created_by:
            return obj.created_by.full_name
        return None

    # def get_bookings_count(self, obj):
    #     return obj.bookings.aggregate(total=models.Sum("guests"))["total"] or 0

     # VALIDATION SECTION
    # -----------------------

    def validate_expected_guests(self, value):
        if value < 0:
            raise serializers.ValidationError("Expected guests cannot be negative.")
        return value

    def validate(self, attrs):
        venue = attrs.get("venue")
        expected_guests = attrs.get("expected_guests")
        start = attrs.get("start_datetime")
        end = attrs.get("end_datetime")
        deposit_amount = attrs.get("deposit_amount", Decimal("0"))
        total_price = attrs.get("total_price", Decimal("0"))
        
        now = timezone.now()
        if start and start < now:
            raise serializers.ValidationError({
                "start_datetime": "You cannot create an event in the past."
            })

        if start and end and start >= end:
            raise serializers.ValidationError({
                "end_datetime": "End datetime must be after start datetime."
            })

        # Prevent Overlapping Events
        if venue and start and end:
            # Look for overlapping events at the same venue
            overlapping = Event.objects.filter(
                venue=venue,
                start_datetime__lt=end,
                end_datetime__gt=start,
            )

        # Exclude current event if updating
        if self.instance:
            overlapping = overlapping.exclude(id=self.instance.id)

        if overlapping.exists():
            raise serializers.ValidationError({
                "venue": "This venue already has an event scheduled during this time."
            })

        #  Validate expected guests <= venue capacity
        if venue and expected_guests:
            if expected_guests > venue.capacity:
                raise serializers.ValidationError({
                    "expected_guests": f"Guests ({expected_guests}) exceed venue capacity ({venue.capacity})."
                })

        #  Validate deposit
        if deposit_amount < 0:
            raise serializers.ValidationError({
                "deposit_amount": "Deposit cannot be negative."
            })

        if total_price < 0:
            raise serializers.ValidationError({
                "total_price": "Total price cannot be negative."
            })

        if deposit_amount > total_price:
            raise serializers.ValidationError({
                "deposit_amount": "Deposit cannot be more than total price."
            })

        return attrs


class EventDetailSerializer(EventListSerializer):
    # same fields + maybe event timeline or bookings nested
    # bookings = serializers.SerializerMethodField()

    class Meta(EventListSerializer.Meta):
        fields = EventListSerializer.Meta.fields

    # def get_bookings(self, obj):
    #     qs = obj.bookings.all().order_by("-created_at")[:10]
    #     return [{"user": getattr(b.user, "id", None), "guests": b.guests, "created_at": b.created_at} for b in qs]


# class EventBookingSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Booking
#         fields = ["id", "event", "user", "guests", "created_at"]
#         read_only_fields = ["created_at"]
