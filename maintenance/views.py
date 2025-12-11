from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from MBP.views import ProtectedModelViewSet
from .models import *
from .serializers import *
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from Hotel.models import Room
from rest_framework.decorators import api_view, permission_classes
from django.db.models import Count
from django.utils.dateparse import parse_date


# =========================================================
# CATEGORY
# =========================================================

class MaintenanceCategoryViewSet(ProtectedModelViewSet):
    queryset = MaintenanceCategory.objects.all()
    serializer_class = MaintenanceCategorySerializer
    model_name = "MaintenanceCategory"
    lookup_field = "slug"

    def get_queryset(self):
        user = self.request.user

        if user.is_superuser:
            return self.queryset

        if hasattr(user, "hotel") and user.hotel:
            return self.queryset.filter(hotel=user.hotel)

        return self.queryset.none()

    def perform_create(self, serializer):
        serializer.save(hotel=self.request.user.hotel)


# =========================================================
# FACILITY
# =========================================================

class FacilityViewSet(ProtectedModelViewSet):
    queryset = Facility.objects.all()
    serializer_class = FacilitySerializer
    model_name = "Facility"
    lookup_field = "slug"

    def get_queryset(self):
        user = self.request.user

        if user.is_superuser:
            return self.queryset

        if hasattr(user, "hotel") and user.hotel:
            return self.queryset.filter(hotel=user.hotel)

        return self.queryset.none()

    def perform_create(self, serializer):
        serializer.save(hotel=self.request.user.hotel)


# =========================================================
# EQUIPMENT
# =========================================================

class EquipmentViewSet(ProtectedModelViewSet):
    queryset = Equipment.objects.all()
    serializer_class = EquipmentSerializer
    model_name = "Equipment"
    lookup_field = "slug"

    def get_queryset(self):
        user = self.request.user

        if user.is_superuser:
            return self.queryset

        if hasattr(user, "hotel") and user.hotel:
            return self.queryset.filter(hotel=user.hotel)

        return self.queryset.none()

    def perform_create(self, serializer):
        serializer.save(hotel=self.request.user.hotel)


# =========================================================
# MAINTENANCE TASK
# =========================================================

class MaintenanceTaskViewSet(ProtectedModelViewSet):
    queryset = MaintenanceTask.objects.select_related(
        'room', 'facility', 'equipment', 'guest', 'hotel'
    ).all()
    serializer_class = MaintenanceTaskSerializer
    model_name = "MaintenanceTask"
    lookup_field = "slug"

    def get_queryset(self):
        user = self.request.user
        base_qs = self.queryset.order_by("-created_at")

        # 1️⃣ Superuser → can see all hotels
        if user.is_superuser:
            return base_qs

        # 2️⃣ Admin → only his hotel
        if hasattr(user, "role") and user.role.name.lower() == "admin":
            if hasattr(user, "hotel") and user.hotel:
                return base_qs.filter(hotel=user.hotel)
            return base_qs.none()

        # 3️⃣ Staff → only assigned tasks
        return base_qs.filter(assigned_to=user)

    # --------------------------
    # Assign task
    # --------------------------
    @action(detail=True, methods=["post"])
    def assign(self, request, slug=None):
        task = self.get_object()
        staff_slug = request.data.get("assigned_to")

        if not staff_slug:
            return Response({"error": "assigned_to required"}, status=400)

        try:
            staff = User.objects.get(slug=staff_slug)
        except User.DoesNotExist:
            return Response({"error": "Invalid staff slug"}, status=400)

        task.assigned_to = staff
        task.status = "in_progress"
        task.save()

        return Response({"message": "Task assigned successfully"}, status=200)

    # --------------------------
    # Complete Task
    # --------------------------
    @action(detail=True, methods=["post"])
    def complete(self, request, slug=None):
        task = self.get_object()
        task.status = "completed"
        task.save()

        return Response({"message": "Task marked as completed"}, status=200)

    # --------------------------
    # Dashboard Data
    # --------------------------
    @action(detail=False, methods=["get"], url_path="dashboard")
    def dashboard(self, request):
        user = request.user

        if user.is_superuser:
            qs = MaintenanceTask.objects.all()
        else:
            qs = MaintenanceTask.objects.filter(hotel=user.hotel)

        data = {
            "total_tasks": qs.count(),
            "completed_tasks": qs.filter(status="completed").count(),
            "in_progress_tasks": qs.filter(status="in_progress").count(),
            "urgent_tasks": qs.filter(priority="high").count(),
        }
        return Response(data, status=200)


# =========================================================
# MARK ROOM AVAILABLE
# =========================================================

class MarkRoomAvailableView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        room_slug = request.data.get('room_slug')

        if not room_slug:
            return Response({"error": "Room slug is required"}, status=400)

        try:
            room = Room.objects.get(slug=room_slug, hotel=request.user.hotel)
        except Room.DoesNotExist:
            return Response({"error": "Room not found or access denied"}, status=404)

        room.status = 'available'
        room.save()

        return Response({
            "message": f"Room {room.room_number} is now marked as Available.",
            "status": "clean"
        }, status=200)


# =========================================================
# ROOM STATUS VIEW
# =========================================================

class RoomStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        hotel = request.user.hotel
        rooms = Room.objects.filter(hotel=hotel, status='maintenance')

        data = []

        for room in rooms:
            try:
                clean = room.cleaning_status
            except RoomCleaningSchedule.DoesNotExist:
                clean = None

            issues = MaintenanceTask.objects.filter(
                room=room, status__in=["pending", "in_progress"]
            ).values_list("title", flat=True)

            final_status = "maintenance" if issues else "clean"

            data.append({
                "room_number": room.room_number,
                "floor": room.floor,
                "category": room.room_category.name if room.room_category else None,
                "last_cleaned": clean.last_cleaned if clean else None,
                "next_cleaning": clean.next_cleaning if clean else None,
                "active_issues": list(issues),
                "status": final_status,
                "room_slug": room.slug
            })

        return Response(data, status=200)


# =========================================================
# MAINTENANCE REPORTS
# =========================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def maintenance_reports(request):
    user = request.user

    if user.is_superuser:
        tasks = MaintenanceTask.objects.all()
    else:
        tasks = MaintenanceTask.objects.filter(hotel=user.hotel)

    start = request.GET.get("start_date")
    end = request.GET.get("end_date")

    filtered = tasks
    if start:
        filtered = filtered.filter(created_at__date__gte=parse_date(start))
    if end:
        filtered = filtered.filter(created_at__date__lte=parse_date(end))

    summary = {
        "total": tasks.count(),
        "pending": tasks.filter(status="pending").count(),
        "in_progress": tasks.filter(status="in_progress").count(),
        "completed": tasks.filter(status="completed").count(),
        "high_priority": tasks.filter(priority="high").count(),
    }

    by_status = tasks.values("status").annotate(count=Count("id"))
    by_priority = tasks.values("priority").annotate(count=Count("id"))
    by_category = (
        tasks.values("category__name")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    filtered_list = filtered.values(
        "title",
        "status",
        "priority",
        "category__name",
        "room__room_number",
        "facility__name",
        "equipment__name",
        "created_at",
        "updated_at"
    )

    return Response({
        "summary": summary,
        "by_status": list(by_status),
        "by_priority": list(by_priority),
        "by_category": [
            {"category": c["category__name"], "count": c["count"]}
            for c in by_category
        ],
        "filtered_tasks": list(filtered_list)
    })