from MBP.views import ProtectedModelViewSet
from datetime import date, datetime
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Q, F, Avg, Sum
from django.utils import timezone
from rest_framework import status
from .models import Hotel, RoomCategory, Room, Booking, RoomServiceRequest, RoomMedia
from django.core.exceptions import PermissionDenied
from .serializers import (
    HotelSerializer,
    RoomCategorySerializer,
    RoomSerializer,
    BookingSerializer,
    RoomServiceRequestSerializer,
    RoomCreateUpdateSerializer,
)


class HotelViewSet(ProtectedModelViewSet):
    queryset = Hotel.objects.all()
    serializer_class = HotelSerializer
    model_name = 'Hotel'
    lookup_field = 'slug'
    
    def get_queryset(self):
        user = self.request.user

        # ✅ Superuser can see all hotels
        if user.is_superuser:
            return Hotel.objects.all()

        # ✅ Admins can see only their own hotel
        if hasattr(user, 'role') and user.role.name.lower() == 'admin':
            return Hotel.objects.filter(owner=user)

        # ✅ Staff can see their hotel (if linked)
        if hasattr(user, 'staff_profile') and user.staff_profile.hotel:
            return Hotel.objects.filter(id=user.staff_profile.hotel.id)

        return Hotel.objects.none()


class RoomCategoryViewSet(ProtectedModelViewSet):
    queryset = RoomCategory.objects.all()
    serializer_class = RoomCategorySerializer
    model_name = 'RoomCategory'
    lookup_field = 'slug'
    
    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

        if user.is_superuser:
            return qs

        if hasattr(user, 'role') and user.role.name.lower() == 'admin':
            return qs.filter(hotel__owner=user)

        if hasattr(user, 'staff_profile') and user.staff_profile.hotel:
            return qs.filter(hotel=user.staff_profile.hotel)

        return qs.none()

import uuid

def is_valid_uuid(value):
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError):
        return False


class RoomViewSet(ProtectedModelViewSet):
    """
    ViewSet for managing Rooms.
    Supports:
    - CRUD operations
    - Uploading multiple images/videos
    - Filtering available rooms
    """
    queryset = Room.objects.all().select_related('hotel', 'room_category').prefetch_related('media')
    serializer_class = RoomSerializer
    model_name = 'Room'
    lookup_field = 'slug'

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

        if user.is_superuser:
            return qs

        if hasattr(user, 'role') and user.role.name.lower() == 'admin':
            return qs.filter(hotel__owner=user)

        if hasattr(user, 'staff_profile') and user.staff_profile.hotel:
            return qs.filter(hotel=user.staff_profile.hotel)

        return qs.none()

    def perform_create(self, serializer):
        user = self.request.user

        if user.is_superuser:
            serializer.save()
            return

        if hasattr(user, 'role') and user.role.name.lower() == 'admin':
            hotel = Hotel.objects.filter(owner=user).first()
            serializer.save(hotel=hotel)
            return

        if hasattr(user, 'staff_profile') and user.staff_profile.hotel:
            serializer.save(hotel=user.staff_profile.hotel)

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return RoomCreateUpdateSerializer
        return RoomSerializer
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return RoomCreateUpdateSerializer
        return RoomSerializer

    # ✅ Custom filter for available rooms
    @action(detail=False, methods=['get'], url_path='available')
    def available_rooms(self, request):
        category_slug = request.query_params.get('category')
        queryset = self.queryset.filter(is_available=True, status='available')
        if category_slug:
            queryset = queryset.filter(room_category__slug=category_slug)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    # ✅ Upload media (images/videos) for a specific room
    @action(detail=True, methods=['post'], url_path='upload-media')
    def upload_media(self, request, slug=None):
        """
        Upload one or more media files (images/videos) for a room.
        POST /api/rooms/<slug>/upload-media/
        """
        room = self.get_object()
        files = request.FILES.getlist('files')
        media_type = request.data.get('media_type', 'image')

        if not files:
            return Response({"error": "No files uploaded."}, status=status.HTTP_400_BAD_REQUEST)

        media_objects = []
        for file in files:
            obj = RoomMedia.objects.create(room=room, file=file, media_type=media_type)
            media_objects.append(obj)

        serializer = RoomMediaSerializer(media_objects, many=True)
        return Response({
            "message": f"{len(media_objects)} media file(s) uploaded successfully.",
            "media": serializer.data
        }, status=status.HTTP_201_CREATED)
    
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
        room_category = request.query_params.get('room_category')  # ✅ new param

        if not all([check_in, check_out, guests, rooms_required]):
            return Response(
                {"error": "Missing required parameters: check_in, check_out, guests, rooms_required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            check_in = datetime.strptime(check_in, "%Y-%m-%d").date()
            check_out = datetime.strptime(check_out, "%Y-%m-%d").date()
            guests = int(guests)
            rooms_required = int(rooms_required)
        except ValueError:
            return Response({"error": "Invalid date or number format."}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Find booked rooms in that date range
        booked_room_ids = Booking.objects.filter(
            Q(check_in__lt=check_out) & Q(check_out__gt=check_in),
            status__in=['pending', 'confirmed', 'checked_in']
        ).values_list('room_id', flat=True)

        # ✅ Start with available rooms
        available_rooms = Room.objects.exclude(id__in=booked_room_ids).filter(
            is_available=True,
            status='available'
        )

        # ✅ Apply optional room_category filter
        if room_category:
            available_rooms = available_rooms.filter(category__slug=room_category)

        # ✅ Check availability
        if available_rooms.count() < rooms_required:
            return Response({
                "message": "Not enough rooms available.",
                "total_available": available_rooms.count(),
                "room_category": room_category or "all"
            }, status=status.HTTP_200_OK)

        # ✅ Serialize and respond
        serialized = RoomSerializer(available_rooms[:rooms_required], many=True)
        return Response({
            "available_rooms": serialized.data,
            "total_available": available_rooms.count(),
            "room_category": room_category or "all"
        }, status=status.HTTP_200_OK)
        
# GET /api/rooms/check-availability/?check_in=2025-07-25&check_out=2025-07-28&guests=2&rooms_required=1&room_category=deluxe


class BookingViewSet(ProtectedModelViewSet):
    queryset = Booking.objects.all().select_related('hotel', 'room', 'user').prefetch_related('guests')
    serializer_class = BookingSerializer
    model_name = 'Booking'
    lookup_field = 'slug'
    
    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

        if user.is_superuser:
            return qs

        if hasattr(user, 'role') and user.role.name.lower() == 'admin':
            return qs.filter(hotel__owner=user)

        if hasattr(user, 'staff_profile') and user.staff_profile.hotel:
            return qs.filter(hotel=user.staff_profile.hotel)

        return qs.none()
    
    @action(detail=True, methods=['post'], url_path='check-in')
    def check_in(self, request, slug=None):
        booking = self.get_object()

        if booking.status not in ['confirmed', 'pending']:
            return Response(
                {"error": "Booking cannot be checked in from the current status."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Mark room unavailable
        booking.room.is_available = False
        booking.room.save(update_fields=['is_available'])

        # Update booking
        booking.status = 'checked_in'
        booking.check_in_time = timezone.now()
        booking.save(update_fields=['status', 'check_in_time'])

        return Response(
            {
                "message": f"{booking.booking_code} checked in successfully.",
                "check_in_time": booking.check_in_time,
            },
            status=status.HTTP_200_OK
        )

    # ✅ Check Out Endpoint
    @action(detail=True, methods=['post'], url_path='check-out')
    def check_out(self, request, slug=None):
        booking = self.get_object()

        if booking.status != 'checked_in':
            return Response(
                {"error": "Only checked-in bookings can be checked out."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Mark room available again
        booking.room.is_available = True
        booking.room.save(update_fields=['is_available'])

        # Update booking
        booking.status = 'checked_out'
        booking.check_out_time = timezone.now()
        booking.save(update_fields=['status', 'check_out_time'])

        return Response(
            {
                "message": f"{booking.booking_code} checked out successfully.",
                "check_out_time": booking.check_out_time,
            },
            status=status.HTTP_200_OK
        )        
    
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
    
    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

        if user.is_superuser:
            return qs

        if hasattr(user, 'role') and user.role.name.lower() == 'admin':
            return qs.filter(hotel__owner=user)

        if hasattr(user, 'staff_profile') and user.staff_profile.hotel:
            return qs.filter(hotel=user.staff_profile.hotel)

        return qs.none()
