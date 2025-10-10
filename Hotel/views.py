from MBP.views import ProtectedModelViewSet
from datetime import date, datetime
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Q, F, Avg, Sum
from .models import Hotel, RoomCategory, Room, Booking, RoomServiceRequest
from .serializers import (
    HotelSerializer,
    RoomCategorySerializer,
    RoomSerializer,
    BookingSerializer,
    RoomServiceRequestSerializer,
)


class HotelViewSet(ProtectedModelViewSet):
    queryset = Hotel.objects.all()
    serializer_class = HotelSerializer
    model_name = 'Hotel'
    lookup_field = 'slug'


class RoomCategoryViewSet(ProtectedModelViewSet):
    queryset = RoomCategory.objects.all()
    serializer_class = RoomCategorySerializer
    model_name = 'RoomCategory'
    lookup_field = 'slug'

import uuid

def is_valid_uuid(value):
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError):
        return False


class RoomViewSet(ProtectedModelViewSet):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    model_name = 'Room'
    lookup_field = 'slug'
    
    @action(detail=False, methods=['get'], url_path='dashboard-summary')
    def dashboard_summary(self, request):
        """
        Returns total count of rooms by status for dashboard cards.
        Example:
        {
          "available": 10,
          "occupied": 5,
          "reserved": 3,
          "maintenance": 2,
          "total_rooms": 20
        }
        """

        hotel_id = request.query_params.get('hotel')
        rooms = Room.objects.all()

        if hotel_id:
            rooms = rooms.filter(hotel_id=hotel_id)

        # Count per status
        status_counts = (
            rooms.values('status')
            .annotate(total=Count('id'))
        )

        data = {status['status']: status['total'] for status in status_counts}

        # Ensure all statuses are present (even if 0)
        for key in ['available', 'occupied', 'reserved', 'maintenance']:
            data.setdefault(key, 0)

        data['total_rooms'] = sum(data.values())

        return Response(data)
    
    @action(detail=False, methods=['get'], url_path='occupancy-summary')
    def occupancy_summary(self, request):
        hotel_id = request.query_params.get('hotel')
        
        if not hotel_id:
            return Response({"error": "Hotel ID is required."}, status=400)

        total_rooms = Room.objects.filter(hotel_id=hotel_id).count()
        occupied_rooms = Room.objects.filter(hotel_id=hotel_id, status='occupied').count()

        if total_rooms == 0:
            return Response({
                'occupancy_percentage': 0,
                'total_rooms': 0,
                'occupied_rooms': 0
            })

        occupancy_percentage = round((occupied_rooms / total_rooms) * 100, 2)

        return Response({
            'total_rooms': total_rooms,
            'occupied_rooms': occupied_rooms,
            'occupancy_percentage': occupancy_percentage
        })
    
    @action(detail=False, methods=['get'], url_path='status-summary')
    def status_summary(self, request):
        hotel_id = request.query_params.get('hotel')
        queryset = Room.objects.all()

        if hotel_id and is_valid_uuid(hotel_id):
            queryset = queryset.filter(hotel_id=hotel_id)

        summary = (
            queryset
            .values('status')
            .annotate(total=Count('id'))
            .order_by('status')
        )

        return Response({item['status']: item['total'] for item in summary})
    
    @action(detail=False, methods=['get'], url_path='check-availability')
    def check_availability(self, request):
        check_in = request.query_params.get('check_in')
        check_out = request.query_params.get('check_out')
        guests = request.query_params.get('guests')
        rooms_required = request.query_params.get('rooms_required')

        if not all([check_in, check_out, guests, rooms_required]):
            return Response({"error": "Missing required parameters."}, status=400)

        try:
            check_in = datetime.strptime(check_in, "%Y-%m-%d").date()
            check_out = datetime.strptime(check_out, "%Y-%m-%d").date()
            guests = int(guests)
            rooms_required = int(rooms_required)
        except ValueError:
            return Response({"error": "Invalid date or number format."}, status=400)

        booked_room_ids = Booking.objects.filter(
            Q(check_in__lt=check_out) & Q(check_out__gt=check_in),
            status__in=['pending', 'confirmed', 'checked_in']
        ).values_list('room_id', flat=True)

        available_rooms = Room.objects.exclude(id__in=booked_room_ids).filter(
            is_available=True,
            status='available'
        )

        if available_rooms.count() < rooms_required:
            return Response({"message": "Not enough rooms available."}, status=200)

        serialized = RoomSerializer(available_rooms[:rooms_required], many=True)
        return Response({
            "available_rooms": serialized.data,
            "total_available": available_rooms.count(),
        })

# GET /api/rooms/check-availability/?check_in=2025-07-25&check_out=2025-07-28&guests=2&rooms_required=1


class BookingViewSet(ProtectedModelViewSet):
    queryset = Booking.objects.all().select_related('hotel', 'room', 'user').prefetch_related('guests')
    serializer_class = BookingSerializer
    model_name = 'Booking'
    lookup_field = 'slug'
    
    def get_queryset(self):
        if self.request.user.is_superuser:
            return Booking.objects.all()
        return Booking.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['get'], url_path='today-summary')
    def today_summary(self, request):
        today = date.today()

        # Filter bookings for today
        today_checkins = Booking.objects.filter(check_in=today, status='checked_in')
        today_checkouts = Booking.objects.filter(check_out=today, status='checked_out')
        current_guests = Booking.objects.filter(
            check_in__lte=today,
            check_out__gte=today,
            status='checked_in'
        )

        return Response({
            'today_checkins': today_checkins.count(),
            'today_checkouts': today_checkouts.count(),
            'total_guests_in_hotel': sum(b.guests_count for b in current_guests)
        })


class RoomServiceRequestViewSet(ProtectedModelViewSet):
    queryset = RoomServiceRequest.objects.all()
    serializer_class = RoomServiceRequestSerializer
    model_name = 'RoomServiceRequest'
    lookup_field = 'slug'
