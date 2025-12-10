from MBP.views import ProtectedModelViewSet
from .models import *
from .serializers import *
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from Hotel.models import Booking
from django.db.models import Count, Sum, Avg
# from django.contrib.auth import get_user_model
# User= get_user_model()
# created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_maintenance_tasks')



class ServiceCategoryViewSet(ProtectedModelViewSet):
    queryset = ServiceCategory.objects.all()
    serializer_class = ServiceCategorySerializer
    model_name = "ServiceCategory"
    lookup_field = "slug"

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


    def get_queryset(self):
        user = self.request.user
        
        if user.is_superuser:
            return self.queryset

        if hasattr(user, 'role') and user.role.name.lower() == "admin":
            return self.queryset.filter(created_by=user)

        return self.queryset.none()

class GuestServiceViewSet(ProtectedModelViewSet):
    queryset = GuestService.objects.select_related("category").all()
    serializer_class = GuestServiceSerializer
    model_name = "GuestService"
    lookup_field = "slug"

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)




    def get_queryset(self):
        qs = super().get_queryset()

        # Admins see only their created services (optional)
        user = self.request.user

        if user.is_superuser:
            return qs

        if hasattr(user, 'role') and user.role and user.role.name.lower() == "admin":
            return qs.filter(created_by=user)

        return qs.none()




class ServiceRequestViewSet(ProtectedModelViewSet):
    serializer_class = ServiceRequestSerializer
    model_name = "ServiceRequest"
    lookup_field = "slug"


    def get_queryset(self):
        user = self.request.user
        base_qs = ServiceRequest.objects.all().order_by("-created_at")
        
        if user.is_superuser:
            return base_qs

        if hasattr(user, 'role') and user.role.name.lower() == "admin":
            return base_qs.filter(created_by=user)

        return base_qs.none()

    @action(detail=True, methods=["post"])
    def assign(self, request, slug=None):
        instance = self.get_object()
        staff_email = request.data.get("assigned_to")

        if not staff_email:
            return Response({"error": "assigned_to is required"}, status=400)

        user = get_user_model().objects.filter(email=staff_email).first()
        if not user:
            return Response({"error": "User not found"}, status=404)

        instance.assigned_to = user
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
            return Response(
                {"booking": ["Guest stay is not active. Cannot create service request."]},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Fetch primary guest (the first guest linked with this booking)
        guest_obj = booking.guests.first()
        guest_name = f"{guest_obj.first_name} {guest_obj.last_name or ''}".strip()

        serializer.save(
            guest_name=guest_name,
            guest_room=str(booking.room.room_number),
            status="pending",
            assigned_to=None,
            created_by=self.request.user  
        )


class GuestProfileListAPIView(APIView):
    def get(self, request):
        user = request.user

        if user.is_superuser:
            bookings = Booking.objects.filter(status__in=["confirmed", "checked_in"])
        else:
            bookings = Booking.objects.filter(
                status__in=["confirmed", "checked_in"],
                hotel=user.hotel
            )

        profiles = []

        for booking in bookings:
            guest = booking.guests.first()
            if not guest:
                continue

            #fetch all services requested by this guest
            service_requests = booking.service_requests.all()

            # Calculate preferences from categories used
            preferences = set()

            # for req in service_requests:
            #     category = ServiceCategory.objects.filter(name=req.category).first()
            #     if category:
            #         for tag in category.preference_tags:
            #             preferences.add(tag)

            for req in service_requests:
                category = req.category  # Direct FK reference

                if category and category.preference_tags:
                    for tag in category.preference_tags:
                        preferences.add(tag)

            # Total amount spent by guest
            total_spent = sum([req.cost for req in service_requests])

            # Satisfaction rating
            ratings = [req.rating for req in service_requests if req.rating]
            satisfaction = sum(ratings)/len(ratings) if ratings else 0

            profiles.append({
                "guest_name": f"{guest.first_name} {guest.last_name or ''}".strip(),
                "room_number": booking.room.room_number,
                "check_in": booking.check_in,
                "check_out": booking.check_out,
                "total_spent": total_spent,
                "satisfaction": satisfaction,
                "preferences": list(preferences),
                "booking_code": booking.booking_code,
                "booking_slug": booking.slug,
            })

        serializer = GuestProfileSerializer(profiles, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)




class ServiceAnalyticsAPIView(APIView):

    def get(self, request):
        user = request.user
        if user.is_superuser:
            requests = ServiceRequest.objects.all()
        else:
            requests = ServiceRequest.objects.filter(created_by=user)


        total_requests = requests.count() or 1  # avoid zero division


        # 1. REQUEST TYPES SUMMARY

        request_types = (
            requests.values("category")
            .annotate(count=Count("id"))
            .order_by("category")
        )

        request_type_data = []
        for obj in request_types:
            request_type_data.append({
                "category": obj["category"],
                "count": obj["count"],
                "percentage": round((obj["count"] / total_requests) * 100, 1)
            })


        # 2. STATUS DISTRIBUTION

        status_data = []
        status_types = ["pending", "in_progress", "completed", "cancelled"]

        for status_name in status_types:
            count = requests.filter(status=status_name).count()
            status_data.append({
                "status": status_name,
                "count": count,
                "percentage": round((count / total_requests) * 100, 1)
            })


        # 3. REVENUE STATISTICS

        total_revenue = requests.aggregate(total=Sum("cost"))["total"] or 0
        avg_per_request = round(total_revenue / total_requests, 2)
        completion_rate = round(
            (requests.filter(status="completed").count() / total_requests) * 100, 1
        )

        # 4. GUEST SATISFACTION

        avg_rating = requests.aggregate(avg=Avg("rating"))["avg"] or 0

        vip_guests = requests.values("booking__guests__id").distinct().count()

        total_guest_spending = total_revenue  # based on all services

        # FINAL RETURN DATA
        analytics = {
            "request_types": request_type_data,
            "status_distribution": status_data,
            "revenue": {
                "total_revenue": total_revenue,
                "average_per_request": avg_per_request,
                "completion_rate": completion_rate
            },
            "guest_satisfaction": {
                "average_rating": round(avg_rating, 2),
                "vip_guests": vip_guests,
                "total_guest_spending": total_guest_spending
            }
        }

        return Response(analytics)




class ServiceSummaryAPIView(APIView):
    """
    Summary API for Guest Services Dashboard
    Shows total requests, pending, completed, and revenue.
    """
    def get(self, request):
        user = request.user
        if user.is_superuser:
            queryset = ServiceRequest.objects.all()
        else:
            queryset = ServiceRequest.objects.filter(created_by=user)


        total_requests = queryset.count()
        pending = queryset.filter(status="pending").count()
        completed = queryset.filter(status="completed").count()

        total_revenue = queryset.aggregate(total=Sum("cost"))["total"] or 0

        data = {
            "total_requests": total_requests,
            "pending": pending,
            "completed": completed,
            "total_revenue": total_revenue,
        }

        return Response(data)
