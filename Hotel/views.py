from MBP.views import ProtectedModelViewSet
from datetime import date, datetime
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Q, F, Avg, Sum, Count, Min, Prefetch, Max
from django.utils import timezone
from rest_framework import status
from .models import Hotel, RoomCategory, Room, Booking, RoomServiceRequest, RoomMedia, Destination, MobileAppConfig, Package
from django.core.exceptions import PermissionDenied
from django.utils.text import slugify
from .serializers import *
from rest_framework.permissions import AllowAny
from django.db.models.functions import Trim, Lower
from Restaurant.models import Restaurant
import random
from rest_framework.views import APIView
import os
from django.http import FileResponse, Http404



class HotelViewSet(ProtectedModelViewSet):
    queryset = Hotel.objects.all()
    serializer_class = HotelSerializer
    model_name = 'Hotel'
    lookup_field = 'slug'
    
    def get_queryset(self):
        user = self.request.user
        qs = Hotel.objects.all()

        # 1️⃣ Superuser → all hotels
        if user.is_superuser:
            return qs

        role = getattr(user, "role", None)
        if not role:
            return qs.none()

        role_name = role.name.lower()

        # 2️⃣ Admin → hotels owned by admin
        if role_name == "admin":
            return qs.filter(owner=user)

        # 3️⃣ Vendor → hotels assigned to vendor
        if role_name == "vendor":
            return qs.filter(vendor=user)

        # 4️⃣ Staff → only their hotel
        if role_name == "staff":
            if hasattr(user, "staff_profile") and user.staff_profile.hotel:
                return qs.filter(id=user.staff_profile.hotel.id)
            return qs.none()

        # 5️⃣ Customer → ALL hotels (for booking)
        if role_name == "customer":
            return qs

        return qs.none()

    
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

    @action(detail=False, methods=['get'], permission_classes=[AllowAny], url_path='search')
    def search(self, request):
        """
        Public API to search hotels without login.
        Query Params:
        - location (string): City, State, or Hotel Name
        - check_in (YYYY-MM-DD)
        - check_out (YYYY-MM-DD)
        - guests (int): Total number of guests
        - rooms (int): Number of rooms required
        """
        location = request.query_params.get('location', '').strip()
        check_in = request.query_params.get('check_in')
        check_out = request.query_params.get('check_out')
        guests = int(request.query_params.get('guests', 1))
        rooms_required = int(request.query_params.get('rooms', 1))

        # 1. Start with all hotels (or active ones)
        queryset = Hotel.objects.filter(status='available')

        # 2. Filter by Location (City, State, or Name)
        if location:
            queryset = queryset.filter(
                Q(city__icontains=location) | 
                Q(state__icontains=location) | 
                Q(name__icontains=location) |
                Q(address__icontains=location)
            )

        # 3. Filter by Date Availability (The logic part)
        if check_in and check_out:
            try:
                check_in_date = datetime.strptime(check_in, "%Y-%m-%d").date()
                check_out_date = datetime.strptime(check_out, "%Y-%m-%d").date()
            except ValueError:
                return Response({"error": "Invalid date format. Use YYYY-MM-DD"}, status=400)

            # Find rooms that are booked during these dates
            booked_rooms_ids = Booking.objects.filter(
                status__in=['confirmed', 'checked_in', 'pending'], # Exclude cancelled/checked_out
                room__isnull=False
            ).filter(
                # Check for date overlap
                Q(check_in__lt=check_out_date) & Q(check_out__gt=check_in_date)
            ).values_list('room_id', flat=True)

            # Find Available Rooms that match Guest Capacity
            # We assume guests are distributed evenly, e.g., 4 guests in 2 rooms = 2 per room.
            guests_per_room = guests / rooms_required 

            available_rooms = Room.objects.filter(
                status='available',
                is_available=True
            ).exclude(
                id__in=booked_rooms_ids
            ).filter(
                # Ensure room category can hold the guests
                room_category__max_occupancy__gte=guests_per_room
            )

            # 4. Filter Hotels that have enough available rooms
            # We annotate the hotel queryset with the count of valid available rooms
            queryset = queryset.prefetch_related(
                Prefetch('rooms', queryset=available_rooms, to_attr='available_room_list')
            ).annotate(
                available_rooms_count=Count(
                    'rooms', 
                    filter=Q(rooms__in=available_rooms),
                    distinct=True
                )
            ).filter(available_rooms_count__gte=rooms_required)

        # Use the specific Public Serializer
        from .serializers import HotelSearchSerializer
        serializer = HotelSearchSerializer(queryset, many=True, context={'request': request})
        
        return Response({
            "count": queryset.count(),
            "results": serializer.data,
            "params": {
                "location": location,
                "dates": f"{check_in} to {check_out}" if check_in else "Any dates",
                "guests": guests
            }
        })
    
    @action(detail=False, methods=['get'], permission_classes=[AllowAny], url_path='top-destinations')
    def top_destinations(self, request):
        """
        Returns Destinations with:
        1. City-wise Counts (Hotels & Restaurants in that City)
        2. State-wise Counts (Hotels & Restaurants in that State)
        3. Rating, State Name, Country Name
        """
        all_destinations = Destination.objects.all()

        
        # CITY-WISE DATA
        
        
        # 1. Hotels grouped by City
        city_hotel_stats = (
            Hotel.objects.filter(status='available')
            .annotate(clean_city=Lower(Trim('city')))
            .values('clean_city')
            .annotate(
                total=Count('id'),
                avg_rating=Avg('reviews__rating'),
                state_name=Max('state'),   # Fetch State name to link with State counts
                country_name=Max('country')
            )
        )
        
        # Map: {'jaipur': {'total': 5, 'state': 'Rajasthan', ...}}
        city_hotel_map = {
            item['clean_city']: {
                'count': item['total'],
                'rating': round(item['avg_rating'], 1) if item['avg_rating'] else 4.5,
                'state': item['state_name'],
                'country': item['country_name']
            }
            for item in city_hotel_stats if item['clean_city']
        }

        # Restaurants grouped by City
        city_resto_stats = (
            Restaurant.objects.filter(status='open')
            .annotate(clean_city=Lower(Trim('city')))
            .values('clean_city')
            .annotate(total=Count('id'))
        )
        city_resto_map = {
            item['clean_city']: item['total']
            for item in city_resto_stats if item['clean_city']
        }

        # STATE-WISE DATA 

        # Hotels grouped by State 
        state_hotel_stats = (
            Hotel.objects.filter(status='available')
            .annotate(clean_state=Lower(Trim('state')))
            .values('clean_state')
            .annotate(total=Count('id'))
        )
        # Map: {'rajasthan': 50, 'delhi': 20}
        state_hotel_map = {
            item['clean_state']: item['total']
            for item in state_hotel_stats if item['clean_state']
        }

        #  Restaurants grouped by State
        state_resto_stats = (
            Restaurant.objects.filter(status='open')
            .annotate(clean_state=Lower(Trim('state')))
            .values('clean_state')
            .annotate(total=Count('id'))
        )
        state_resto_map = {
            item['clean_state']: item['total']
            for item in state_resto_stats if item['clean_state']
        }


        # MERGE EVERYTHING

        results = []

        for dest in all_destinations:
            # 1. Identify City
            search_city = dest.name.lower().strip()
            
            # 2. Get City Data
            h_data = city_hotel_map.get(search_city)
            r_count = city_resto_map.get(search_city, 0)

            if h_data:
                # Basic City Info
                dest.hotel_count = h_data['count']
                dest.restaurant_count = r_count
                dest.rating = h_data['rating']
                dest.state = h_data['state']
                dest.country = h_data['country']

                # 3. Identify State (from the Hotel Data we just found)
                state_name = h_data['state']
                
                # 4. Get State-wise Totals
                if state_name:
                    search_state = state_name.lower().strip()
                    dest.state_hotel_count = state_hotel_map.get(search_state, 0)
                    dest.state_restaurant_count = state_resto_map.get(search_state, 0)
                else:
                    dest.state_hotel_count = 0
                    dest.state_restaurant_count = 0

                results.append(dest)
        
        # Sort by City Hotel Count
        results.sort(key=lambda x: x.hotel_count, reverse=True)

        serializer = DestinationSerializer(results, many=True, context={'request': request})
        return Response(serializer.data)


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
            return serializer.save()
            

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
        Dashboard summary:
        - Superuser → can filter by ?hotel=<hotel_slug>
        - Admin → only their assigned hotel
        - Staff → only their assigned hotel
        """

        user = request.user

        # -----------------------------------
        # SUPERUSER → filter by hotel slug
        # -----------------------------------
        if user.is_superuser:
            hotel_slug = request.query_params.get('hotel')  # ⭐ filter by slug

            if hotel_slug:
                try:
                    hotel = Hotel.objects.get(slug=hotel_slug)
                    rooms = Room.objects.filter(hotel=hotel)
                except Hotel.DoesNotExist:
                    return Response(
                        {"error": "Invalid hotel slug."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                rooms = Room.objects.all()

        # -----------------------------------
        # ADMIN → rooms for their own hotel only
        # -----------------------------------
        elif hasattr(user, 'role') and user.role.name.lower() == 'admin':
            if not hasattr(user, 'hotel') or user.hotel is None:
                return Response(
                    {"error": "Admin does not have a hotel assigned."},
                    status=status.HTTP_403_FORBIDDEN
                )

            rooms = Room.objects.filter(hotel=user.hotel)

        # -----------------------------------
        # STAFF → only rooms of their hotel
        # -----------------------------------
        elif hasattr(user, 'staff_profile') and user.staff_profile.hotel:
            rooms = Room.objects.filter(hotel=user.staff_profile.hotel)

        # -----------------------------------
        # Others → No access
        # -----------------------------------
        else:
            return Response(
                {"error": "You do not have permission to view room summary."},
                status=status.HTTP_403_FORBIDDEN
            )

        # -----------------------------------
        # GROUP BY STATUS
        # -----------------------------------
        status_counts = rooms.values('status').annotate(total=Count('id'))
        data = {item['status']: item['total'] for item in status_counts}

        # Ensure all statuses appear even if zero
        for status_key in ['available', 'occupied', 'reserved', 'maintenance']:
            data.setdefault(status_key, 0)

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




class FeaturedListingView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        # Logic to mix 7/8 or 6/9
        # Randomly choose ek combination
        combinations = [(7, 8), (8, 7), (9, 6), (6, 9)]
        num_hotels, num_restaurants = random.choice(combinations)

        # --- Fetch Hotels ---
        # Annotate karte hue taaki DB queries kam ho (Optimization)
        # min_price: RoomCategory se sabse kam price
        # avg_rating: HotelReview se average rating
        hotels = Hotel.objects.filter(status='available').annotate(
            min_price=Min('room_categories__price_per_night'),
            avg_rating=Avg('reviews__rating'),
            total_reviews=Count('reviews')
        ).order_by('?')[:num_hotels] # order_by('?') shuffles result in DB

        # --- Fetch Restaurants ---
        restaurants = Restaurant.objects.filter(status='open').order_by('?')[:num_restaurants]

        # --- Serialize Data ---
        hotel_data = HotelListingSerializer(hotels, many=True, context={'request': request}).data
        restaurant_data = RestaurantListingSerializer(restaurants, many=True, context={'request': request}).data

        # --- Combine and Shuffle ---
        combined_data = hotel_data + restaurant_data
        random.shuffle(combined_data) # Python level pe shuffle taaki mix ho jaye

        return Response(combined_data)
    

class DownloadAndroidAppView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        # Database se latest config nikalo
        app_config = MobileAppConfig.objects.first()
        
        if app_config and app_config.android_apk:
            file_handle = app_config.android_apk.open()
            
            # 'as_attachment=True' hi file ko download karwata hai
            response = FileResponse(file_handle, as_attachment=True)
            
            # Optional: Filename set karna
            response['Content-Disposition'] = f'attachment; filename="HMS.apk"'
            return response
        else:
            return Response({"error": "APK file not found on server"}, status=404)

class DownloadIOSAppView(APIView):
    permission_classes = [AllowAny]  # Authentication hatane ke liye

    def get(self, request):
        app_config = MobileAppConfig.objects.first()
        
        if app_config and app_config.ios_ipa:
            # File open karo
            file_handle = app_config.ios_ipa.open()
            
            # FileResponse return karo
            response = FileResponse(file_handle, as_attachment=True)
            
            # Browser ko batane ke liye ki ye .ipa file h
            # 'TravelApp.ipa' wo naam h jo user ke phone me save hoga
            response['Content-Disposition'] = 'attachment; filename="HMS.ipa"'
            
            return response
        else:
            return Response({"error": "iOS IPA file not found on server"}, status=404)
        
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
class PackageViewSet(ProtectedModelViewSet):
    # 1. Base Queryset
    queryset = Package.objects.filter(is_active=True).order_by('-created_at')
    serializer_class = PackageSerializer
    model_name = 'Package'
    lookup_field = 'slug'

    # 2. Filter Backends (SearchFilter add kiya hai taaki search bar kaam kare)
    filter_backends = [DjangoFilterBackend, SearchFilter]
    
    # 3. Exact Filters (Dropdowns ke liye)
    # 'departure_city' add kiya hai taaki "From Delhi" wala filter chale
    filterset_fields = ['package_type', 'category', 'departure_city']

    # 4. Smart Search (Text typing ke liye - "To" field)
    search_fields = ['name', 'locations', 'description']

    def get_queryset(self):
        # Base queryset uthao
        qs = super().get_queryset() # ya Package.objects.filter(is_active=True).order_by('-created_at')
        
        # --- Travellers Logic (New) ---
        # Agar user bhejta hai ?travellers=4
        travellers = self.request.query_params.get('travellers')
        
        if travellers:
            try:
                count = int(travellers)
                # Check karo: Ya to seats Unlimited hon (null) YA seats count se zyada hon
                qs = qs.filter(Q(total_seats__gte=count) | Q(total_seats__isnull=True))
            except ValueError:
                pass # Agar user ne number nahi bheja to ignore karo

        return qs

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return super().get_permissions()

    # def get_queryset(self):
    #     # Public Queryset
    #     qs = Package.objects.filter(is_active=True)
        
    #     # Filter by Type (International / Domestic)
    #     # Usage: /api/packages/?type=international
    #     p_type = self.request.query_params.get('type')
    #     if p_type:
    #         qs = qs.filter(package_type__iexact=p_type)
            
        return qs
    
    # def get_permissions(self):
    #     # Public users (Bina login) sirf dekh sakte hain (GET)
    #     if self.action in ['list', 'retrieve']:
    #         return [AllowAny()]
    #     # Create/Update/Delete ke liye Login zaruri hai
    #     return [IsAuthenticated()]

    # def get_queryset(self):
    #     """
    #     Logic:
    #     1. Public User -> Dekhega SAARE Active Packages.
    #     2. Superuser -> Dekhega SAB Kuch.
    #     3. Hotel Admin -> Dekhega SIRF KHUD ke banaye hue packages.
    #     """
    #     user = self.request.user
    #     qs = Package.objects.all().order_by('-created_at')

    #     # Public User (Anonymous)
    #     if not user.is_authenticated:
    #         return qs.filter(is_active=True)

    #     # Superuser (Boss)
    #     if user.is_superuser:
    #         return qs

    #     # Hotel Admin (Khud ka maal dekhega)
    #     if hasattr(user, 'role') and user.role.name.lower() == 'admin':
    #         return qs.filter(owner=user)
        
    #     # Staff (Agar staff access hai to wo apne admin ke packages dekhega)
    #     if hasattr(user, 'staff_profile') and user.staff_profile.hotel:
    #          return qs.filter(owner=user.staff_profile.hotel.owner)

    #     # Fallback for Public active packages if user fits none above
    #     return qs.filter(is_active=True)

    # def perform_create(self, serializer):
    #     """
    #     Jab Package create ho, to Owner apne aap logged-in Admin set ho jaye.
    #     """
    #     user = self.request.user
        
    #     if user.is_superuser:
    #         # Superuser can create, but ideally should assign via serializer if needed.
    #         # Here keeping it simple: Superuser becomes owner
    #         serializer.save(owner=user)
            
    #     elif hasattr(user, 'role') and user.role.name.lower() == 'admin':
    #         # Admin becomes owner
    #         serializer.save(owner=user)
            
    #     else:
    #         # Koi aur create nahi kar sakta
    #         from rest_framework.exceptions import PermissionDenied
    #         raise PermissionDenied("Only Admins can create packages.")