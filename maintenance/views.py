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

        return Response({"message":"Task Mark as Completed"}, status=200)


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
    

    #  CHANGE : API Room ko Available karne ke liye
class MarkRoomAvailableView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Frontend se room_id ya room_slug bhejna hoga
        room_slug = request.data.get('room_slug')
        
        if not room_slug:
            return Response({"error": "Room slug is required"}, status=400)

        try:
            # Sirf user ke hotel ka room hona chahiye
            room = Room.objects.get(slug=room_slug, hotel=request.user.hotel)
        except Room.DoesNotExist:
            return Response({"error": "Room not found or access denied"}, status=404)

        # Room status update
        room.status = 'available'
        room.save()

        return Response({
            "message": f"Room {room.room_number} is now marked as Available.",
            "status": "clean"
        }, status=200)


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


            final_status = "Clean" # Default fallback
            
            if room.status == 'maintenance':
                final_status = "maintenance"
            elif room.status == 'reserved':
                final_status = "reserved" # Frontend pe isse filter out kar lena ya alag color dena
            elif room.status == 'occupied':
                final_status = "occupied"
            elif issues:
                # Agar room available hai par chhota mota issue hai (like bulb change)
                final_status = "maintenance"
            else:
                final_status = "clean" # Matlab available and clean


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

        # Agar Cleaning schedule update kiya hai to room available kar do
        # (Agar tumhara cleaning workflow 'Maintenance' status use karta hai)
        room = Room.objects.get(id=room_id)
        if room.status == 'maintenance':
            room.status = 'available'
            room.save()

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
