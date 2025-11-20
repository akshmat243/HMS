# events/serializers.py
from rest_framework import serializers
from .models import Venue, Event, EventType, Event_Booking as Booking
from django.utils import timezone
from django.db import models



class VenueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Venue
        fields = [
            "id", "name", "slug", "kind", "capacity", "hourly_rate", "features",
            "is_active", "created_by", "created_at"
        ]
        read_only_fields = ["created_by", "created_at"]


class EventTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventType
        fields = ["id", "name", "slug"]


class EventListSerializer(serializers.ModelSerializer):
    # venue = VenueSerializer(read_only=True)
    # event_type = EventTypeSerializer(read_only=True)
    event_type = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=EventType.objects.all()
    )

    venue = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=Venue.objects.all()
    )

    
    # capacity_percent = serializers.FloatField(source="capacity_percent", read_only=True)
    capacity_percent = serializers.FloatField(read_only=True)
    payment_percent = serializers.FloatField(read_only=True)

    # payment_percent = serializers.FloatField(source="payment_percent", read_only=True)
    bookings_count = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id", "title", "slug", "description","event_type", "venue",
            "start_datetime", "end_datetime", "expected_guests", "venue_capacity",
            "capacity_percent", "payment_percent", "deposit_amount", "total_price",
            "contact_name", "contact_phone", "tags", "status", "bookings_count",
            "created_by", "created_at"
        ]
        read_only_fields = ["created_by", "created_at"]

    def get_bookings_count(self, obj):
        return obj.bookings.aggregate(total=models.Sum("guests"))["total"] or 0


class EventDetailSerializer(EventListSerializer):
    # same fields + maybe event timeline or bookings nested
    bookings = serializers.SerializerMethodField()

    class Meta(EventListSerializer.Meta):
        fields = EventListSerializer.Meta.fields + ["bookings"]

    def get_bookings(self, obj):
        qs = obj.bookings.all().order_by("-created_at")[:10]
        return [{"user": getattr(b.user, "id", None), "guests": b.guests, "created_at": b.created_at} for b in qs]


class EventBookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = ["id", "event", "user", "guests", "created_at"]
        read_only_fields = ["created_at"]
