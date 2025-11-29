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
from django.utils import timezone


class MaintenanceCategoryViewSet(ProtectedModelViewSet):
    queryset = MaintenanceCategory.objects.all()
    serializer_class = MaintenanceCategorySerializer
    model_name = "MaintenanceCategory"
    lookup_field = "slug"

    def get_queryset(self):
        return self.queryset.filter(hotel=self.request.user.hotel)

    def perform_create(self, serializer):
        serializer.save(hotel=self.request.user.hotel)


class FacilityViewSet(ProtectedModelViewSet):
    queryset = Facility.objects.all()
    serializer_class = FacilitySerializer
    model_name = "Facility"
    lookup_field = "slug"

    def get_queryset(self):
        return self.queryset.filter(hotel=self.request.user.hotel)

    def perform_create(self, serializer):
        serializer.save(hotel=self.request.user.hotel)


class EquipmentViewSet(ProtectedModelViewSet):
    queryset = Equipment.objects.all()
    serializer_class = EquipmentSerializer
    model_name = "Equipment"
    lookup_field = "slug"

    def get_queryset(self):
        return self.queryset.filter(hotel=self.request.user.hotel)

    def perform_create(self, serializer):
        serializer.save(hotel=self.request.user.hotel)


class MaintenanceTaskViewSet(ProtectedModelViewSet):
    queryset = MaintenanceTask.objects.select_related('room', 'facility', 'equipment', 'guest', 'hotel').all()
    serializer_class = MaintenanceTaskSerializer
    model_name = "MaintenanceTask"
    lookup_field = "slug"

    def get_queryset(self):
        user = self.request.user

        # ADMIN → show all tasks of HIS hotel
        if hasattr(user, 'hotel') and user.hotel:
            return MaintenanceTask.objects.filter(hotel=user.hotel)

        # STAFF → show only tasks assigned to HIM
        return MaintenanceTask.objects.filter(assigned_to=user)

    # Assign task to staff (accept staff id or slug)
    @action(detail=True, methods=["post"])
    def assign(self, request, slug=None):
        task = self.get_object()
        staff_slug = request.data.get("assigned_to")
        if not staff_slug:
            return Response({"error": "assigned_to required"}, status=400)

        # Accept UUID or slug; try to set assigned_to_id directly
        try:
            staff = User.objects.get(slug=staff_slug)
        except User.DoesNotExist:
            return Response({"error": "Invalid staff slug"}, status=400)

        task.assigned_to = staff
        task.status = "in_progress"
        task.save()

        return Response({"message": "Task assigned successfully"}, status=200)

    @action(detail=True, methods=["post"])
    def complete(self, request, slug=None):
        task = self.get_object()
        task.status = "completed"
        task.save()
        return Response({"message": "Task marked as completed"}, status=200)

    @action(detail=False, methods=["get"], url_path="dashboard")
    def dashboard(self, request):
        hotel = request.user.hotel
        qs = MaintenanceTask.objects.filter(hotel=hotel)

        data = {
            "total_tasks": qs.count(),
            "completed_tasks": qs.filter(status="completed").count(),
            "in_progress_tasks": qs.filter(status="in_progress").count(),
            "urgent_tasks": qs.filter(priority="high").count(),
        }
        return Response(data, status=200)


class RoomStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        hotel = request.user.hotel

        rooms = Room.objects.filter(hotel=hotel)

        data = []

        for room in rooms:
            # cleaning status
            try:
                clean = room.cleaning_status
            except RoomCleaningSchedule.DoesNotExist:
                clean = None

            # active issues
            issues = MaintenanceTask.objects.filter(
                room=room,
                status__in=["pending", "in_progress"]
            ).values_list("title", flat=True)

            data.append({
                "room_number": room.room_number,
                "floor": room.floor,
                "category": room.room_category.name if room.room_category else None,
                "last_cleaned": clean.last_cleaned if clean else None,
                "next_cleaning": clean.next_cleaning if clean else None,
                "active_issues": list(issues),
                "status": "maintenance" if issues else "clean"
            })

        return Response(data, status=200)

    @staticmethod
    def post(request):
        room_id = request.data.get("room")
        last_cleaned = request.data.get("last_cleaned")
        next_cleaning = request.data.get("next_cleaning")

        schedule, created = RoomCleaningSchedule.objects.get_or_create(
            room_id=room_id,
            hotel=request.user.hotel
        )

        schedule.last_cleaned = last_cleaned
        schedule.next_cleaning = next_cleaning
        schedule.save()

        return Response({"message": "Cleaning schedule updated"}, status=200)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def maintenance_reports(request):
    hotel = request.user.hotel
    tasks = MaintenanceTask.objects.filter(hotel=hotel)

    # ---- Date Filter ----
    start = request.GET.get("start_date")
    end = request.GET.get("end_date")

    filtered = tasks
    if start:
        filtered = filtered.filter(created_at__date__gte=parse_date(start))
    if end:
        filtered = filtered.filter(created_at__date__lte=parse_date(end))

    # ---- Summary ----
    summary = {
        "total": tasks.count(),
        "pending": tasks.filter(status="pending").count(),
        "in_progress": tasks.filter(status="in_progress").count(),
        "completed": tasks.filter(status="completed").count(),
        "high_priority": tasks.filter(priority="high").count(),
    }

    # ---- Status ----
    by_status = tasks.values("status").annotate(count=Count("id"))

    # ---- Priority ----
    by_priority = tasks.values("priority").annotate(count=Count("id"))

    # ---- Category ----
    by_category = (
        tasks.values("category__name")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    # ---- Filtered tasks list ----
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
