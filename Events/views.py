# events/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Sum, Count
from django.utils import timezone
from .models import Venue, Event, EventType #Event_Booking as Booking
from .serializers import VenueSerializer, EventListSerializer, EventDetailSerializer, EventTypeSerializer #EventBookingSerializer as BookingSerializer
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
        qs = self.queryset
        user = self.request.user

        if not user.is_authenticated:
            return qs.none()

        if user.is_superuser:
            return qs
        
        if hasattr(user, "role") and user.role and user.role.name.lower() == "admin":
            return qs.filter(hotel__owner=user)

        if hasattr(user, "role") and user.role and user.role.name.lower() == "vendor":
            if hasattr(user, "supplier_profile"):
                return qs.filter(hotel=user.supplier_profile.hotel)

        if hasattr(user, "role") and user.role and user.role.name.lower() == "staff":
            if hasattr(user, "staff_profile"):
                return qs.filter(hotel=user.staff_profile.hotel)

        # NORMAL USERS → OPTIONAL RULE
        return qs.filter(is_active=True)
    

    @action(detail=True, methods=["get"], url_path="schedule")
    def schedule(self, request, slug=None):
        """
        Sirf UPCOMING (future) events dikhane ke liye.
        URL: /api/venues/<slug>/schedule/
        """
        venue = self.get_object()
        
        #current time
        now = timezone.now()

        events = Event.objects.filter(
            venue=venue, 
            start_datetime__gte=now
        ).order_by('start_datetime')

        data = [
            {
                "id": e.id,
                "title": e.title,
                "start": e.start_datetime,
                "end": e.end_datetime,
                "status": e.status,
                "customer": e.contact_name,
            } for e in events
        ]
        return Response(data, status=status.HTTP_200_OK)


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
        qs = self.queryset
        user = self.request.user

        if not user.is_authenticated:
            return qs.none()

        if user.is_superuser:
            return qs
        
        if hasattr(user, "role") and user.role and user.role.name.lower() == "admin":
            return qs.filter(hotel__owner=user)

        if hasattr(user, "role") and user.role and user.role.name.lower() == "vendor":
            if hasattr(user, "supplier_profile"):
                return qs.filter(hotel=user.supplier_profile.hotel)

        if hasattr(user, "role") and user.role and user.role.name.lower() == "staff":
            if hasattr(user, "staff_profile"):
                return qs.filter(hotel=user.staff_profile.hotel)
        
        # NORMAL USERS → ONLY EVENTS RELATED TO THEM
        return qs.filter(created_by=user)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=["get"], url_path="calendar")
    def calendar(self, request):
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

    @action(detail=False, methods=["get"], url_path="analytical_data")
    def analytics(self, request):
        qs = self.get_queryset()

        total_revenue = qs.aggregate(total=Sum("total_price"))["total"] or 0
        pending_revenue = qs.filter(status="pending").aggregate(total=Sum("total_price"))["total"] or 0
        expected_total = total_revenue + pending_revenue

        types = qs.values("event_type__name").annotate(count=Count("id")).order_by("-count")
        venues = qs.values("venue__name").annotate(count=Count("id")).order_by("-count")
        statuses = qs.values("status").annotate(count=Count("id"))

        return Response({
            "total_revenue": total_revenue,
            "pending_revenue": pending_revenue,
            "expected_total": expected_total,
            "event_types": [{"type": t["event_type__name"] or "Unknown", "count": t["count"]} for t in types],
            "venue_utilization": [{"venue": v["venue__name"] or "Unknown", "count": v["count"]} for v in venues],
            "status_overview": {s["status"]: s["count"] for s in statuses},
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="add-deposit")
    def add_deposit(self, request, slug=None):
        event = self.get_object()

        amount = request.data.get("amount")
        if not amount:
            return Response({"detail": "Amount is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amt = Decimal(str(amount))
        except:
            return Response({"detail": "Invalid amount format"}, status=status.HTTP_400_BAD_REQUEST)

        if amt < 0:
            return Response({"detail": "Deposit amount cannot be negative."}, status=status.HTTP_400_BAD_REQUEST)

        new_total_deposit = (event.deposit_amount or Decimal("0")) + amt

        if new_total_deposit > event.total_price:
            return Response(
                {"detail": f"Deposit cannot exceed total price of {event.total_price}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        event.deposit_amount = new_total_deposit
        event.save()

        return Response({
            "deposit_amount": str(event.deposit_amount),
            "payment_percent": event.payment_percent,
            "status": event.status, 
        }, status=status.HTTP_200_OK)
    

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
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


class EventTypeViewSet(ProtectedModelViewSet):
    """
    Simple viewset for EventType (Conference, Wedding, Meeting ...)
    Uses ProtectedModelViewSet so your HasModelPermission + RBAC stays consistent.
    """
    queryset = EventType.objects.all()
    serializer_class = EventTypeSerializer
    model_name = "EventType"
    lookup_field = "slug"

    def get_queryset(self):
        qs = self.queryset
        user = self.request.user

        if user.is_superuser:
            return qs

        if hasattr(user, "role") and user.role and user.role.name.lower() == "admin":
            return qs.filter(hotel__owner=user)

        if hasattr(user, "role") and user.role and user.role.name.lower() == "vendor":
            if hasattr(user, "supplier_profile"):
                return qs.filter(hotel=user.supplier_profile.hotel)

        if hasattr(user, "role") and user.role and user.role.name.lower() == "staff":
            if hasattr(user, "staff_profile"):
                return qs.filter(hotel=user.staff_profile.hotel)

        return qs.none()
