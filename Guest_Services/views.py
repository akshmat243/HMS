from MBP.views import ProtectedModelViewSet
from .models import *
from .serializers import *
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from Hotel.models import Booking
from django.db.models import Count, Sum, Avg
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError


# =================================================
# SERVICE CATEGORY VIEWSET
# =================================================
class ServiceCategoryViewSet(ProtectedModelViewSet):
    queryset = ServiceCategory.objects.all()
    serializer_class = ServiceCategorySerializer
    model_name = "ServiceCategory"
    lookup_field = "slug"

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

        if user.is_superuser:
            return qs

        role = getattr(user.role, "name", "").lower()

        if role == "admin":
            return qs.filter(hotel__owner=user)

        if role == "vendor" and hasattr(user, "supplier_profile"):
            return qs.filter(hotel=user.supplier_profile.hotel)

        if role == "staff" and hasattr(user, "staff_profile"):
            return qs.filter(hotel=user.staff_profile.hotel)

        # Customers cannot view service categories
        return qs.none()


# =================================================
# GUEST SERVICE VIEWSET
# =================================================
class GuestServiceViewSet(ProtectedModelViewSet):
    queryset = GuestService.objects.select_related("category").all()
    serializer_class = GuestServiceSerializer
    model_name = "GuestService"
    lookup_field = "slug"

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

        if user.is_superuser:
            return qs

        role = getattr(user.role, "name", "").lower()

        if role == "admin":
            return qs.filter(hotel__owner=user)

        if role == "vendor" and hasattr(user, "supplier_profile"):
            return qs.filter(hotel=user.supplier_profile.hotel)

        if role == "staff" and hasattr(user, "staff_profile"):
            return qs.filter(hotel=user.staff_profile.hotel)

        # Customers cannot view guest services list
        return qs.none()


# =================================================
# SERVICE REQUEST VIEWSET
# =================================================
class ServiceRequestViewSet(ProtectedModelViewSet):
    queryset = ServiceRequest.objects.all()
    serializer_class = ServiceRequestSerializer
    model_name = "ServiceRequest"
    lookup_field = "slug"

    def get_queryset(self):
        user = self.request.user
        qs = self.queryset.order_by("-created_at")

        if user.is_superuser:
            return qs

        role = getattr(user.role, "name", "").lower()

        if role == "admin":
            return qs.filter(hotel__owner=user)

        if role == "vendor" and hasattr(user, "supplier_profile"):
            return qs.filter(hotel=user.supplier_profile.hotel)

        if role == "staff" and hasattr(user, "staff_profile"):
            return qs.filter(hotel=user.staff_profile.hotel)

        if role == "customer":
            return qs.filter(
                booking__guests__user=user,
                booking__status__in=["confirmed", "checked_in"]
            ).distinct()

        return qs.none()

    @action(detail=True, methods=["post"])
    def assign(self, request, slug=None):
        instance = self.get_object()
        staff_email = request.data.get("assigned_to")

        if not staff_email:
            return Response({"error": "assigned_to is required"}, status=400)

        staff = get_user_model().objects.filter(email=staff_email).first()
        if not staff:
            return Response({"error": "User not found"}, status=404)

        instance.assigned_to = staff
        instance.status = "in_progress"
        instance.save()

        return Response(ServiceRequestSerializer(instance).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, slug=None):
        instance = self.get_object()
        instance.status = "completed"
        instance.save()
        return Response(ServiceRequestSerializer(instance).data)

    def perform_create(self, serializer):
        booking = serializer.validated_data["booking"]

        if booking.status not in ["checked_in", "confirmed"]:
            raise ValidationError({"booking": "Guest stay is not active. Cannot create service request."})

        guest_obj = booking.guests.first()
        guest_name = f"{guest_obj.first_name} {guest_obj.last_name or ''}".strip() if guest_obj else "Guest"

        serializer.save(
            guest_name=guest_name,
            guest_room=str(booking.room.room_number),
            status="pending",
            assigned_to=None,
            created_by=self.request.user
        )


# =================================================
# GUEST PROFILE API
# =================================================
class GuestProfileListAPIView(APIView):
    def get(self, request):
        user = request.user
        role = getattr(user.role, "name", "").lower()

        if user.is_superuser:
            bookings = Booking.objects.filter(status__in=["confirmed", "checked_in"])
        elif role == "admin":
            bookings = Booking.objects.filter(
                status__in=["confirmed", "checked_in"],
                room__hotel__owner=user
            )
        elif role == "vendor" and hasattr(user, "supplier_profile"):
            bookings = Booking.objects.filter(
                status__in=["confirmed", "checked_in"],
                room__hotel=user.supplier_profile.hotel
            )
        elif role == "staff" and hasattr(user, "staff_profile"):
            bookings = Booking.objects.filter(
                status__in=["confirmed", "checked_in"],
                room__hotel=user.staff_profile.hotel
            )
        else:
            return Response([], status=200)  # Customers can't see dashboard

        profiles = []

        for booking in bookings:
            guest = booking.guests.first()
            if not guest:
                continue

            service_requests = booking.service_requests.select_related("category")
            preferences = set()

            for req in service_requests:
                if req.category and req.category.preference_tags:
                    preferences.update(req.category.preference_tags)

            ratings = [req.rating for req in service_requests if req.rating]
            satisfaction = round(sum(ratings) / len(ratings), 2) if ratings else 0

            profiles.append({
                "guest_name": f"{guest.first_name} {guest.last_name or ''}".strip(),
                "room_number": booking.room.room_number,
                "check_in": booking.check_in,
                "check_out": booking.check_out,
                "total_spent": sum(req.cost for req in service_requests),
                "satisfaction": satisfaction,
                "preferences": list(preferences),
                "booking_code": booking.booking_code,
                "booking_slug": booking.slug,
            })

        return Response(GuestProfileSerializer(profiles, many=True).data)


# =================================================
# ANALYTICS + SUMMARY API
# =================================================
class ServiceAnalyticsAPIView(APIView):
    def get(self, request):
        user = request.user

        if user.is_superuser:
            qs = ServiceRequest.objects.all()
        else:
            qs = ServiceRequest.objects.filter(created_by=user)

        total = qs.count() or 1

        analytics = {
            "request_types": list(qs.values("category__name").annotate(count=Count("id"))),
            "status_distribution": [
                {"status": st, "count": qs.filter(status=st).count()}
                for st in ["pending", "in_progress", "completed", "cancelled"]
            ],
            "revenue": {
                "total_revenue": (qs.aggregate(Sum("cost"))["cost__sum"] or 0),
                "avg_per_request": round((qs.aggregate(Sum("cost"))["cost__sum"] or 1) / total, 2)
            }
        }

        return Response(analytics)


class ServiceSummaryAPIView(APIView):
    def get(self, request):
        user = request.user
        qs = ServiceRequest.objects.all() if user.is_superuser else ServiceRequest.objects.filter(created_by=user)

        data = {
            "total_requests": qs.count(),
            "pending": qs.filter(status="pending").count(),
            "completed": qs.filter(status="completed").count(),
            "total_revenue": qs.aggregate(Sum("cost"))["cost__sum"] or 0,
        }
        return Response(data)
