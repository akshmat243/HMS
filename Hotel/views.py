from MBP.views import ProtectedModelViewSet
from datetime import date, datetime
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Q, F, Avg, Sum
from django.utils import timezone
from rest_framework import status
from .models import Hotel, RoomCategory, Room, Booking, RoomServiceRequest, RoomMedia
from django.core.exceptions import PermissionDenied
from django.utils.text import slugify
from .serializers import (
    HotelSerializer,
    RoomCategorySerializer,
    RoomSerializer,
    BookingSerializer,
    RoomServiceRequestSerializer,
    RoomCreateUpdateSerializer,
    RoomMediaSerializer
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
    
    @action(detail=False, methods=['get'], url_path='stats')
    def hotel_stats(self, request):
        """
        Custom endpoint to show hotel statistics.
        Example: /api/hotels/stats/
        """
        qs = self.get_queryset()

        # Aggregate counts by status
        total_hotels = qs.count()
        status_counts = qs.values('status').annotate(total=Count('status'))

        stats = {
            'total_hotels': total_hotels,
            'available': 0,
            'maintenance': 0,
            'closed': 0
        }

        for entry in status_counts:
            stats[entry['status']] = entry['total']

        return Response(stats, status=status.HTTP_200_OK)

    def perform_create(self, serializer):
        # Auto-generate slug if not provided
        name = serializer.validated_data.get('name')
        slug = slugify(name)

        # Ensure only one hotel per admin
        owner = serializer.validated_data.get('owner')
        if owner and Hotel.objects.filter(owner=owner).exists():
            return Response(
                {"error": f"Admin {owner.full_name} already owns a hotel."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer.save(slug=slug)


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
    queryset = Room.objects.all().select_related('hotel', 'room_category').prefetch_related('media')
    serializer_class = RoomSerializer
    model_name = 'Room'
    lookup_field = 'slug'

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

        # Superuser → sees all rooms
        if user.is_superuser:
            return qs

        # Admin → rooms only from their hotel
        if hasattr(user, 'role') and user.role.name.lower() == 'admin':
            return qs.filter(hotel=user.hotel)

        # Staff → rooms only from their hotel
        if hasattr(user, 'staff_profile') and user.staff_profile.hotel:
            return qs.filter(hotel=user.staff_profile.hotel)

        return qs.none()


    def perform_create(self, serializer):
        user = self.request.user

        # Superuser → choose hotel manually in POST
        if user.is_superuser:
            serializer.save()
            return

        # Admin → forced to their hotel
        if hasattr(user, 'role') and user.role.name.lower() == 'admin':
            serializer.save(hotel=user.hotel)
            return

        # Staff → forced to their hotel
        if hasattr(user, 'staff_profile') and user.staff_profile.hotel:
            serializer.save(hotel=user.staff_profile.hotel)
            return

        raise PermissionDenied("You cannot create rooms.")


    def perform_update(self, serializer):
        user = self.request.user

        instance = self.get_object()

        # Superuser → can update anything
        if user.is_superuser:
            serializer.save()
            return

        # Admin → must belong to same hotel
        if hasattr(user, 'role') and user.role.name.lower() == 'admin':
            if instance.hotel != user.hotel:
                raise PermissionDenied("You cannot update rooms for another hotel.")
            serializer.save(hotel=user.hotel)
            return

        # Staff
        if hasattr(user, 'staff_profile') and user.staff_profile.hotel:
            if instance.hotel != user.staff_profile.hotel:
                raise PermissionDenied("You cannot update rooms for another hotel.")
            serializer.save(hotel=user.staff_profile.hotel)
            return

        raise PermissionDenied("You cannot update rooms.")


    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return RoomCreateUpdateSerializer
        return RoomSerializer

    @action(detail=False, methods=['get'], url_path='available')
    def available_rooms(self, request):
        """
        Returns a list of available rooms.
        - Superuser can filter with ?hotel=<hotel_id>
        - Hotel admin sees only their hotel’s available rooms
        - Optional: ?category=<category_slug>
        """
        user = request.user
        category_slug = request.query_params.get('category')

        # Superuser can specify hotel id
        if user.is_superuser:
            hotel_id = request.query_params.get('hotel')
            if hotel_id:
                queryset = self.queryset.filter(hotel_id=hotel_id)
            else:
                queryset = self.queryset.all()
        else:
            # Regular hotel admin: only their own hotel
            if hasattr(user, 'hotel'):
                queryset = self.queryset.filter(hotel=user.hotel)
            else:
                return Response(
                    {"error": "No hotel assigned to your account."},
                    status=status.HTTP_403_FORBIDDEN
                )

        # Filter for available rooms
        queryset = queryset.filter(is_available=True, status='available')

        # Optional category filter
        if category_slug:
            queryset = queryset.filter(room_category__slug=category_slug)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


    @action(detail=True, methods=['post'], url_path='upload-media')
    def upload_media(self, request, slug=None):
        """
        Upload one or more media files (images/videos) for a room.
        Only allowed for the room’s hotel admin or superuser.
        """
        room = self.get_object()
        user = request.user

        # 🔒 Ensure user belongs to the same hotel (unless superuser)
        if not user.is_superuser:
            if not hasattr(user, 'hotel') or room.hotel != user.hotel:
                return Response(
                    {"error": "You do not have permission to upload media for this room."},
                    status=status.HTTP_403_FORBIDDEN
                )

        files = request.FILES.getlist('files')
        media_type = request.data.get('media_type', 'image')

        if not files:
            return Response({"error": "No files uploaded."}, status=status.HTTP_400_BAD_REQUEST)

        media_objects = [
            RoomMedia.objects.create(room=room, file=file, media_type=media_type)
            for file in files
        ]

        serializer = RoomMediaSerializer(media_objects, many=True)
        return Response({
            "message": f"{len(media_objects)} media file(s) uploaded successfully.",
            "media": serializer.data
        }, status=status.HTTP_201_CREATED)

    
    @action(detail=False, methods=['get'], url_path='dashboard-summary')
    def dashboard_summary(self, request):
        """
        Returns total count of rooms by status for dashboard cards,
        but limited to the logged-in admin’s hotel.
        Superuser can still filter by ?hotel=<hotel_id>.
        """

        user = request.user

        # Superuser can query any hotel via ?hotel=<id>
        if user.is_superuser:
            hotel_id = request.query_params.get('hotel')
            if hotel_id:
                rooms = Room.objects.filter(hotel_id=hotel_id)
            else:
                rooms = Room.objects.all()
        else:
            # Normal admin: only their own hotel
            if hasattr(user, 'hotel'):
                rooms = Room.objects.filter(hotel=user.hotel)
            else:
                return Response(
                    {"error": "No hotel assigned to your account."},
                    status=status.HTTP_403_FORBIDDEN
                )

        # Count per status
        status_counts = rooms.values('status').annotate(total=Count('id'))

        data = {status['status']: status['total'] for status in status_counts}

        # Ensure all statuses are present (even if 0)
        for key in ['available', 'occupied', 'reserved', 'maintenance']:
            data.setdefault(key, 0)

        data['total_rooms'] = sum(data.values())

        return Response(data)

    @action(detail=False, methods=['get'], url_path='occupancy-summary')
    def occupancy_summary(self, request):
        user = request.user
        hotel_id = request.query_params.get('hotel')

        # 🔒 Enforce hotel scope
        if not user.is_superuser:
            # if your user has a foreign key like user.hotel
            if hasattr(user, 'hotel') and user.hotel:
                hotel_id = user.hotel.id
            else:
                return Response({"error": "You are not associated with any hotel."},
                                status=status.HTTP_403_FORBIDDEN)

        if not hotel_id:
            return Response({"error": "Hotel ID is required."}, status=400)

        # ✅ Use aggregation for performance
        rooms = Room.objects.filter(hotel_id=hotel_id)
        total_rooms = rooms.count()
        occupied_rooms = rooms.filter(status='occupied').count()

        if total_rooms == 0:
            return Response({
                'occupancy_percentage': 0,
                'total_rooms': 0,
                'occupied_rooms': 0
            }, status=200)

        occupancy_percentage = round((occupied_rooms / total_rooms) * 100, 2)

        return Response({
            'total_rooms': total_rooms,
            'occupied_rooms': occupied_rooms,
            'occupancy_percentage': occupancy_percentage
        }, status=200)

    
    @action(detail=False, methods=['get'], url_path='status-summary')
    def status_summary(self, request):
        user = request.user
        hotel_id = request.query_params.get('hotel')

        # 🔒 Restrict hotel scope
        if not user.is_superuser:
            if hasattr(user, 'hotel') and user.hotel:
                hotel_id = user.hotel.id
            else:
                return Response(
                    {"error": "You are not associated with any hotel."},
                    status=status.HTTP_403_FORBIDDEN
                )

        if not hotel_id or not is_valid_uuid(hotel_id):
            return Response({"error": "Valid hotel ID is required."}, status=400)

        # ✅ Filter by hotel
        queryset = Room.objects.filter(hotel_id=hotel_id)

        # ✅ Aggregate status counts
        summary = (
            queryset
            .values('status')
            .annotate(total=Count('id'))
            .order_by('status')
        )

        data = {item['status']: item['total'] for item in summary}

        # ✅ Ensure all statuses appear even if 0
        for key in ['available', 'occupied', 'reserved', 'maintenance']:
            data.setdefault(key, 0)

        data['total_rooms'] = sum(data.values())

        return Response(data, status=200)
    
    @action(detail=False, methods=['get'], url_path='check-availability')
    def check_availability(self, request):
        """
        Check available rooms for a given date range and optional category.
        Restricts data to the logged-in user's assigned hotel (unless superuser).
        """
        user = request.user
        hotel = None

        # 🔒 Limit hotel scope for admin users
        if not user.is_superuser:
            if hasattr(user, 'hotel') and user.hotel:
                hotel = user.hotel
            else:
                return Response({"error": "You are not assigned to any hotel."},
                                status=status.HTTP_403_FORBIDDEN)

        check_in = request.query_params.get('check_in')
        check_out = request.query_params.get('check_out')
        guests = request.query_params.get('guests')
        rooms_required = request.query_params.get('rooms_required')
        room_category = request.query_params.get('room_category')

        # ✅ Validate required fields
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

        if check_in >= check_out:
            return Response({"error": "Check-out date must be after check-in date."},
                            status=status.HTTP_400_BAD_REQUEST)

        # ✅ Filter bookings for the same hotel and date overlap
        bookings = Booking.objects.filter(
            Q(check_in__lt=check_out) & Q(check_out__gt=check_in),
            status__in=['pending', 'confirmed', 'checked_in']
        )
        if hotel:
            bookings = bookings.filter(room__hotel=hotel)

        booked_room_ids = bookings.values_list('room_id', flat=True)

        # ✅ Available rooms (scoped by hotel)
        rooms = Room.objects.exclude(id__in=booked_room_ids).filter(
            is_available=True,
            status='available'
        )
        if hotel:
            rooms = rooms.filter(hotel=hotel)

        # ✅ Optional category filter
        if room_category:
            rooms = rooms.filter(room_category__slug=room_category)

        total_available = rooms.count()

        if total_available < rooms_required:
            return Response({
                "message": "Not enough rooms available.",
                "available_count": total_available,
                "room_category": room_category or "all"
            }, status=status.HTTP_200_OK)

        serializer = RoomSerializer(rooms[:rooms_required], many=True)
        return Response({
            "message": "Rooms available.",
            "available_rooms": serializer.data,
            "available_count": total_available,
            "room_category": room_category or "all"
        }, status=status.HTTP_200_OK)
        
# GET /api/rooms/check-availability/?check_in=2025-07-25&check_out=2025-07-28&guests=2&rooms_required=1&room_category=deluxe


class BookingViewSet(ProtectedModelViewSet):
    """
    ViewSet for managing bookings.
    Ensures hotel admins and staff only access their assigned hotel's bookings.
    """
    queryset = Booking.objects.all().select_related('hotel', 'room', 'user').prefetch_related('guests')
    serializer_class = BookingSerializer
    model_name = 'Booking'
    lookup_field = 'slug'

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

        # 🔒 Superuser can see everything
        if user.is_superuser:
            return qs

        # ✅ Admin role — sees only their own hotel
        if hasattr(user, 'role') and user.role and user.role.name.lower() == 'admin':
            return qs.filter(hotel__owner=user)

        # ✅ Staff profile — sees only bookings for their assigned hotel
        staff_profile = getattr(user, 'staff_profile', None)
        if staff_profile and getattr(staff_profile, 'hotel', None):
            return qs.filter(hotel=staff_profile.hotel)

        # ❌ Others — no access
        return qs.none()
    
    # ✅ Check-In Endpoint
    @action(detail=True, methods=['post'], url_path='check-in')
    def check_in(self, request, slug=None):
        booking = self.get_object()

        # ✅ Validation
        if booking.status not in ['confirmed', 'pending']:
            return Response(
                {"error": "Only confirmed or pending bookings can be checked in."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not booking.room:
            return Response({"error": "No room assigned to this booking."}, status=status.HTTP_400_BAD_REQUEST)

        if not booking.room.status == "reserved":
            return Response({"error": "Room is already occupied or unavailable."}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Update room and booking
        booking.room.status = "occupied"
        booking.room.save(update_fields=['status'])

        booking.status = 'checked_in'
        booking.check_in_time = timezone.now()
        booking.save(update_fields=['status', 'check_in_time'])

        return Response(
            {
                "message": f"Booking {booking.booking_code} checked in successfully.",
                "check_in_time": booking.check_in_time,
            },
            status=status.HTTP_200_OK
        )

    # ✅ Check-Out Endpoint
    @action(detail=True, methods=['post'], url_path='check-out')
    def check_out(self, request, slug=None):
        booking = self.get_object()

        # ✅ Validation
        if booking.status != 'checked_in':
            return Response(
                {"error": "Only checked-in bookings can be checked out."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not booking.room:
            return Response({"error": "No room assigned to this booking."}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Update room and booking
        # booking.room.is_available = True
        # booking.room.save(update_fields=['is_available'])

        booking.status = 'checked_out'
        booking.check_out_time = timezone.now()
        booking.save(update_fields=['status', 'check_out_time'])

        return Response(
            {
                "message": f"Booking {booking.booking_code} checked out successfully.",
                "check_out_time": booking.check_out_time,
            },
            status=status.HTTP_200_OK
        )        
    
    # ✅ Today Summary Endpoint
    @action(detail=False, methods=['get'], url_path='today-summary')
    def today_summary(self, request):
        today = timezone.localdate()

        queryset = self.get_queryset()

        # Filtered data
        today_checkins = queryset.filter(check_in=today, status='checked_in')
        today_checkouts = queryset.filter(check_out=today, status='checked_out')
        current_guests = queryset.filter(
            Q(check_in__lte=today) & Q(check_out__gte=today),
            status='checked_in'
        )

        # Use aggregation for efficiency
        total_guests = current_guests.aggregate(total=Sum('guests_count'))['total'] or 0

        return Response({
            "date": today,
            "today_checkins": today_checkins.count(),
            "today_checkouts": today_checkouts.count(),
            "total_guests_in_hotel": total_guests
        }, status=status.HTTP_200_OK)


class RoomServiceRequestViewSet(ProtectedModelViewSet):
    queryset = RoomServiceRequest.objects.select_related('room', 'room__hotel', 'user')
    serializer_class = RoomServiceRequestSerializer
    lookup_field = 'slug'
    model_name = 'RoomServiceRequest'

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        if user.is_superuser:
            return qs
        # Hotel admin access: only data for hotels user owns
        if hasattr(user, 'role') and user.role and user.role.name.lower() == 'admin':
            return qs.filter(room__hotel__owner=user)
        # Staff: only their assigned hotel
        if hasattr(user, 'staff_profile') and getattr(user.staff_profile, 'hotel', None):
            return qs.filter(room__hotel=user.staff_profile.hotel)
        return qs.none()

    # List API (with optional filters for dashboard, e.g. status, date)
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        # Dashboard filter examples (by status, priority, date)
        status_param = request.query_params.get('status')
        priority = request.query_params.get('priority')
        if status_param:
            queryset = queryset.filter(status=status_param)
        if priority:
            queryset = queryset.filter(priority=priority)
        # Today’s orders filter
        today_param = request.query_params.get('today')
        if today_param == '1':
            today = timezone.localdate()
            queryset = queryset.filter(requested_at__date=today)
        # Search query
        search = request.query_params.get('q')
        if search:
            queryset = queryset.filter(Q(service_code__icontains=search) | Q(room__room_number__icontains=search))
        # Usual paginated response
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    # Retrieve API for single request (by slug)
    def retrieve(self, request, slug=None):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    # Create API (from modal/form: validates via serializer)
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # Update API (status, description, etc.)
    def update(self, request, slug=None, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    # PATCH endpoint for status change ("Deliver" button, etc.)
    @action(detail=True, methods=['post'])
    def deliver(self, request, slug=None):
        instance = self.get_object()
        instance.status = 'delivered'
        instance.is_resolved = True
        instance.delivery_time = timezone.now().time()
        instance.save()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    # Summary/stat API for dashboard widgets
    @action(detail=False, methods=['get'])
    def stats(self, request):
        qs = self.get_queryset()
        today = timezone.localdate()
        orders_today = qs.filter(requested_at__date=today).count()
        in_progress = qs.filter(status='in_progress').count()
        ready = qs.filter(status='ready').count()
        express = qs.filter(priority='express').count()
        return Response({
            'orders_today': orders_today,
            'in_progress': in_progress,
            'ready_for_delivery': ready,
            'express_orders': express
        })

    # Progress tracking API (for timeline/status steps)
    @action(detail=True, methods=['get'])
    def progress(self, request, slug=None):
        instance = self.get_object()
        progress_data = self._build_progress(instance)
        return Response(progress_data)

    def _build_progress(self, instance):
        # Example: timeline for laundry service request
        steps = []
        if instance.status == 'pending':
            steps.append({'step': 'Collection', 'done': False, 'timestamp': None})
        if instance.status in ['in_progress', 'ready', 'delivered']:
            steps.append({'step': 'Collection', 'done': True, 'timestamp': str(instance.pickup_time)})
        if instance.status in ['ready', 'delivered']:
            steps.append({'step': 'Ready for Delivery', 'done': True, 'timestamp': str(instance.delivery_time)})
        if instance.status == 'delivered':
            steps.append({'step': 'Delivered', 'done': True, 'timestamp': str(instance.delivery_time)})
        return steps
    
    # @action(detail=False, methods=['get'], url_path='status-summary')
    # def status_summary(self, request):
    #     """
    #     Returns a summary count of service requests by status.
    #     """
    #     queryset = self.get_queryset()
    #     summary = (
    #         queryset.values('status')
    #         .annotate(total=Count('id'))
    #         .order_by('status')
    #     )
    #     return Response({item['status']: item['total'] for item in summary}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        user = request.user
        today = date.today()

        # Base QuerySet for Laundry services
        laundry_qs = RoomServiceRequest.objects.filter(service_type='laundry')

        # ✅ Role-based filtering
        if not user.is_superuser:
            if hasattr(user, 'role') and user.role and user.role.name.lower() == 'admin':
                laundry_qs = laundry_qs.filter(room__hotel__owner=user)
            elif hasattr(user, 'staff_profile') and user.staff_profile.hotel:
                laundry_qs = laundry_qs.filter(room__hotel=user.staff_profile.hotel)
            else:
                return Response(
                    {"error": "You are not associated with any hotel."},
                    status=status.HTTP_403_FORBIDDEN
                )

        # ✅ Optional filter by hotel slug
        hotel_slug = request.query_params.get("hotel")
        if hotel_slug:
            laundry_qs = laundry_qs.filter(room__hotel__slug=hotel_slug)

        # ✅ Filter today’s orders
        todays_orders = laundry_qs.filter(requested_at__date=today)

        total_today = todays_orders.count()
        in_progress = todays_orders.filter(status='in_progress').count()
        ready_for_delivery = todays_orders.filter(status='ready').count()
        express_orders = todays_orders.filter(priority='express').count()

        # ✅ Calculate growth % (vs yesterday)
        from datetime import timedelta
        yesterday_orders = laundry_qs.filter(requested_at__date=today - timedelta(days=1)).count()

        def growth(today, yesterday):
            if yesterday == 0:
                return "+0%"
            change = ((today - yesterday) / yesterday) * 100
            sign = "+" if change >= 0 else "-"
            return f"{sign}{abs(round(change, 1))}%"

        return Response({
            "orders_today": {
                "count": total_today,
                "growth": growth(total_today, yesterday_orders)
            },
            "in_progress": {
                "count": in_progress,
                "growth": growth(in_progress, 0)  # Can later compute by comparing historic data
            },
            "ready_for_delivery": {
                "count": ready_for_delivery,
                "growth": growth(ready_for_delivery, 0)
            },
            "express_orders": {
                "count": express_orders,
                "growth": growth(express_orders, 0)
            },
        })

    @action(detail=True, methods=['get'], url_path='timeline')
    def timeline(self, request, slug=None):
        service = self.get_object()

        data = [
            {
                "stage": stage.get_stage_display(),
                "time": stage.timestamp.strftime("%I:%M %p"),
                "timestamp": stage.timestamp
            }
            for stage in service.stages.all()
        ]

        return Response(data)

