# events/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Sum, Count
from django.utils import timezone
from .models import Venue, Event, EventType, Event_Booking as Booking
from .serializers import VenueSerializer, EventListSerializer, EventDetailSerializer, EventTypeSerializer, EventBookingSerializer as BookingSerializer
from MBP.views import ProtectedModelViewSet  # reuse your ProtectedModelViewSet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db.models import Q,Sum
from django.db import models
from decimal import Decimal


class VenueViewSet(ProtectedModelViewSet):
    queryset = Venue.objects.all()
    serializer_class = VenueSerializer
    model_name = "Venue"
    lookup_field = "slug"
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["is_active", "kind"]
    search_fields = ["name", "features"]
    ordering_fields = ["capacity", "hourly_rate"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return qs.none()
        if user.is_superuser:
            return qs
        # staff/admin only see their created venues
        if user.is_staff:
            return qs.filter(created_by=user)
        # normal users: maybe only active venues or those created_by them
        return qs.filter(Q(is_active=True) | Q(created_by=user))


class EventViewSet(ProtectedModelViewSet):
    queryset = Event.objects.select_related("venue", "event_type").all()
    serializer_class = EventListSerializer
    model_name = "Event"
    lookup_field = "slug"
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "event_type__name", "venue__name"]
    search_fields = ["title", "description", "tags", "contact_name"]
    ordering_fields = ["start_datetime", "created_at"]

    def get_serializer_class(self):
        if self.action in ["retrieve", "partial_update", "update"]:
            return EventDetailSerializer
        return EventListSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return qs.none()
        if user.is_superuser:
            return qs
        # staff/admin can only see events they created
        if user.is_staff:
            return qs.filter(created_by=user)
        # regular users: see events they created or where they are contact (conservative)
        return qs.filter(Q(created_by=user) | Q(contact_name__icontains=getattr(user, "get_full_name", lambda: "")()))

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=["get"], url_path="calendar")
    def calendar(self, request):
        """
        Return events in a given date range for calendar view.
        Accepts ?start=YYYY-MM-DD&end=YYYY-MM-DD
        """
        start = request.query_params.get("start")
        end = request.query_params.get("end")
        qs = self.get_queryset()
        if start:
            qs = qs.filter(end_datetime__gte=start)
        if end:
            qs = qs.filter(start_datetime__lte=end)
        data = [
            {
                "id": e.id,
                "title": e.title,
                "start": e.start_datetime,
                "end": e.end_datetime,
                "status": e.status,
                "venue": getattr(e.venue, "name", None),
            } for e in qs
        ]
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="analytics")
    def analytics(self, request):
        """
        Return aggregated data for Reports page:
        - revenue totals
        - counts by event type
        - venue utilization (counts)
        - status overview
        """
        qs = self.get_queryset()
        total_revenue = qs.aggregate(total=Sum("total_price"))["total"] or 0
        pending_revenue = qs.filter(status="pending").aggregate(total=Sum("total_price"))["total"] or 0
        expected_total = total_revenue + pending_revenue

        # Event types
        types = qs.values("event_type__name").annotate(count=Count("id")).order_by("-count")
        types_list = [{"type": t["event_type__name"] or "Unknown", "count": t["count"]} for t in types]

        # venue utilization (count of events per venue)
        venues = qs.values("venue__name").annotate(count=Count("id")).order_by("-count")
        venues_list = [{"venue": v["venue__name"] or "Unknown", "count": v["count"]} for v in venues]

        # status overview
        statuses = qs.values("status").annotate(count=Count("id"))
        status_list = {s["status"]: s["count"] for s in statuses}

        return Response({
            "total_revenue": total_revenue,
            "pending_revenue": pending_revenue,
            "expected_total": expected_total,
            "event_types": types_list,
            "venue_utilization": venues_list,
            "status_overview": status_list,
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="add-deposit")
    def add_deposit(self, request, slug=None):
        """
        Simple endpoint to add deposit/payment for an event.
        """
        event = self.get_object()
        if not request.user.is_superuser and request.user.is_staff and event.created_by != request.user:
            return Response({"detail": "Not allowed"}, status=status.HTTP_403_FORBIDDEN)
        amount = request.data.get("amount")
        try:
            amt = Decimal(str(amount))   # <-- FIX: convert safely to Decimal
        except:
            return Response({"detail": "Invalid amount"}, status=status.HTTP_400_BAD_REQUEST)

        event.deposit_amount = (event.deposit_amount or Decimal("0")) + amt
        event.save()

        return Response({
            "deposit_amount": str(event.deposit_amount),
            "payment_percent": event.payment_percent
        }, status=status.HTTP_200_OK)
    

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """
        Dashboard summary:
        - total events
        - total revenue
        - confirmed events count
        - total attendees (expected guests)
        """
        qs = self.get_queryset()

        total_events = qs.count()

        total_revenue = qs.aggregate(total=models.Sum("total_price"))["total"] or 0

        confirmed_events = qs.filter(status="confirmed").count()

        total_attendees = qs.aggregate(total=models.Sum("expected_guests"))["total"] or 0

        return Response({
            "total_events": total_events,
            "total_revenue": total_revenue,
            "confirmed_events": confirmed_events,
            "total_attendees": total_attendees,
        })



class BookingViewSet(ProtectedModelViewSet):
    queryset = Booking.objects.select_related("event", "user").all()
    serializer_class = BookingSerializer
    model_name = "Booking"

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return qs.none()
        if user.is_superuser:
            return qs
        if user.is_staff:
            # show bookings for events this admin created
            return qs.filter(event__created_by=user)
        # regular users: their own bookings
        return qs.filter(Q(user=user))


class EventTypeViewSet(ProtectedModelViewSet):
    """
    Simple viewset for EventType (Conference, Wedding, Meeting ...)
    Uses ProtectedModelViewSet so your HasModelPermission + RBAC stays consistent.
    """
    queryset = EventType.objects.all()
    serializer_class = EventTypeSerializer
    model_name = "EventType"
    lookup_field = "slug"