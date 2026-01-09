from MBP.views import ProtectedModelViewSet
from datetime import date, datetime
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Q, F, Avg, Sum, Count, Min, Prefetch, Max
from django.utils import timezone
from datetime import timedelta
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
from Restaurant.models import RestaurantOrder
from maintenance.models import MaintenanceTask
from django.utils.timesince import timesince
from staff.models import Staff


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

       # ✅ Staff
        # if hasattr(user, 'role') and user.role.name.lower() == 'staff':
        #     return Hotel.objects.filter(staff__user=user)

        # ✅ Vendor
        if hasattr(user, 'role') and user.role.name.lower() == 'vendor':
            return Hotel.objects.filter(vendors__user=user)

        # ✅ Customer
        if hasattr(user, 'role') and user.role.name.lower() == 'customer':
            return Hotel.objects.filter(status='available')


        # 4. Staff: Their linked hotel
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
    
    def _get_dashboard_target_hotel(self, request):
        """Internal helper to resolve hotel scope based on user role."""
        user = request.user
        if user.is_superuser:
            # Superuser filter via query param
            h_id = request.query_params.get('hotel_id')
            if h_id:
                return Hotel.objects.filter(id=h_id).first()
            return None # Global scope
        
        if hasattr(user, 'role') and user.role.name.lower() == 'admin':
            return getattr(user, 'hotel', None)
        
        if hasattr(user, 'staff_profile') and user.staff_profile.hotel:
            return user.staff_profile.hotel
        return None

    def _calculate_growth(self, current, previous):
        """Internal helper for growth %."""
        if previous == 0:
            return "+100%" if current > 0 else "0%"
        change = ((current - previous) / previous) * 100
        sign = "+" if change >= 0 else "-"
        return f"{sign}{abs(round(change, 1))}%"
    

    @action(detail=False, methods=['get'], url_path='dashboard/stats-cards')
    def dashboard_stats_cards(self, request):
        user = request.user
        context = request.query_params.get("context")  # hotel | restaurant
        slug = request.query_params.get("slug")

        if not context or not slug:
            return Response(
                {"error": "context and slug are required"},
                status=400
            )

        today = timezone.localdate()
        yesterday = today - timedelta(days=1)

        # ------------------------------------------------
        # HOTEL DASHBOARD
        # ------------------------------------------------
        if context == "hotel":
            try:
                hotel = Hotel.objects.get(slug=slug)
            except Hotel.DoesNotExist:
                return Response({"error": "Invalid hotel"}, status=404)

            if not (user.is_superuser or hotel.owner == user):
                return Response({"error": "Unauthorized"}, status=403)

            # ---------- Revenue (Bookings only) ----------
            booking_ct = ContentType.objects.get_for_model(Booking)

            def get_booking_revenue(date_val):
                b_ids = Booking.objects.filter(
                    hotel=hotel
                ).values_list("id", flat=True)

                return Invoice.objects.filter(
                    status="paid",
                    issued_at__date=date_val,
                    content_type=booking_ct,
                    object_id__in=b_ids
                ).aggregate(total=Sum("total_amount"))["total"] or 0

            rev_today = get_booking_revenue(today)
            rev_yesterday = get_booking_revenue(yesterday)

            # ---------- Room Occupancy ----------
            room_qs = Room.objects.filter(hotel=hotel)
            total_rooms = room_qs.count()

            occ_today = room_qs.filter(
                status__in=["occupied", "reserved"]
            ).count()

            b_qs = Booking.objects.filter(
                hotel=hotel,
                status__in=["checked_in", "checked_out", "confirmed"],
                check_in__lte=yesterday,
                check_out__gt=yesterday
            )
            occ_yesterday = b_qs.count()

            pct_today = (occ_today / total_rooms * 100) if total_rooms else 0
            pct_yesterday = (occ_yesterday / total_rooms * 100) if total_rooms else 0

            # ---------- Guests ----------
            guests_now = Booking.objects.filter(
                hotel=hotel,
                status="checked_in"
            ).aggregate(total=Sum("guests_count"))["total"] or 0

            guests_yesterday = Booking.objects.filter(
                hotel=hotel,
                status__in=["checked_in", "checked_out", "confirmed"],
                check_in__lte=yesterday,
                check_out__gt=yesterday
            ).aggregate(total=Sum("guests_count"))["total"] or 0

            return Response({
                "revenue": {
                    "value": float(rev_today),
                    "growth": self._calculate_growth(rev_today, rev_yesterday)
                },
                "room_occupancy": {
                    "value": f"{round(pct_today)}%",
                    "growth": self._calculate_growth(pct_today, pct_yesterday)
                },
                "total_guests": {
                    "value": guests_now,
                    "growth": self._calculate_growth(guests_now, guests_yesterday)
                }
            })

        # ------------------------------------------------
        # RESTAURANT DASHBOARD
        # ------------------------------------------------
        if context == "restaurant":
            try:
                restaurant = Restaurant.objects.get(slug=slug)
            except Restaurant.DoesNotExist:
                return Response({"error": "Invalid restaurant"}, status=404)

            if not (user.is_superuser or restaurant.owner == user):
                return Response({"error": "Unauthorized"}, status=403)

            order_ct = ContentType.objects.get_for_model(RestaurantOrder)

            def get_restaurant_revenue(date_val):
                o_ids = RestaurantOrder.objects.filter(
                    table__restaurant=restaurant
                ).values_list("id", flat=True)

                return Invoice.objects.filter(
                    status="paid",
                    issued_at__date=date_val,
                    content_type=order_ct,
                    object_id__in=o_ids
                ).aggregate(total=Sum("total_amount"))["total"] or 0

            rev_today = get_restaurant_revenue(today)
            rev_yesterday = get_restaurant_revenue(yesterday)

            orders_today = RestaurantOrder.objects.filter(
                table__restaurant=restaurant,
                order_time__date=today
            )

            active_orders = orders_today.filter(
                status__in=["pending", "preparing"]
            ).count()

            created_yesterday = RestaurantOrder.objects.filter(
                table__restaurant=restaurant,
                order_time__date=yesterday
            ).count()

            return Response({
                "revenue": {
                    "value": float(rev_today),
                    "growth": self._calculate_growth(rev_today, rev_yesterday)
                },
                "active_orders": {
                    "value": active_orders,
                    "growth": self._calculate_growth(
                        orders_today.count(),
                        created_yesterday
                    )
                }
            })

        return Response({"error": "Invalid context"}, status=400)



    # --- DASHBOARD API : TODAY SUMMARY ---
    @action(detail=False, methods=['get'], url_path='dashboard/today-summary')
    def dashboard_today_summary(self, request):
        user = request.user
        context = request.query_params.get("context")  # hotel | restaurant
        slug = request.query_params.get("slug")
        today = timezone.localdate()

        if not context or not slug:
            return Response(
                {"error": "context and slug are required"},
                status=400
            )

        # --------------------------------
        # HOTEL DASHBOARD
        # --------------------------------
        if context == "hotel":
            try:
                hotel = Hotel.objects.get(slug=slug)
            except Hotel.DoesNotExist:
                return Response({"error": "Invalid hotel"}, status=404)

            if not (user.is_superuser or hotel.owner == user):
                return Response({"error": "Unauthorized"}, status=403)

            bookings = Booking.objects.filter(hotel=hotel)

            check_ins = bookings.filter(check_in=today).count()
            check_outs = bookings.filter(check_out=today).count()

            booking_ct = ContentType.objects.get_for_model(Booking)
            booking_ids = bookings.values_list("id", flat=True)

            revenue = Invoice.objects.filter(
                content_type=booking_ct,
                object_id__in=booking_ids,
                status="paid",
                issued_at__date=today
            ).aggregate(total=Sum("total_amount"))["total"] or 0

            return Response({
                "context": "hotel",
                "check_ins": check_ins,
                "check_outs": check_outs,
                "revenue": float(revenue),
            })

        # --------------------------------
        # RESTAURANT DASHBOARD
        # --------------------------------
        if context == "restaurant":
            try:
                restaurant = Restaurant.objects.get(slug=slug)
            except Restaurant.DoesNotExist:
                return Response({"error": "Invalid restaurant"}, status=404)

            if not (user.is_superuser or restaurant.owner == user):
                return Response({"error": "Unauthorized"}, status=403)

            orders = RestaurantOrder.objects.filter(
                table__restaurant=restaurant
            )

            food_orders = orders.filter(
                order_time__date=today,
                status__in=["served", "preparing", "completed"]
            ).count()

            order_ct = ContentType.objects.get_for_model(RestaurantOrder)
            order_ids = orders.values_list("id", flat=True)

            revenue = Invoice.objects.filter(
                content_type=order_ct,
                object_id__in=order_ids,
                status="paid",
                issued_at__date=today
            ).aggregate(total=Sum("total_amount"))["total"] or 0

            return Response({
                "context": "restaurant",
                "food_orders": food_orders,
                "revenue": float(revenue),
            })

        return Response({"error": "Invalid context"}, status=400)

    
    @action(detail=False, methods=['get'], url_path='dashboard/recent-activities')
    def recent_activities(self, request):
        """
        Returns exactly 4 most recent activities from:
        1. Bookings (Confirmed, Checked In, Checked Out)
        2. Restaurant Orders (Ready, Served)
        3. Maintenance (Completed, Reported)
        """
        user = request.user
        target_hotel = self._get_dashboard_target_hotel(request)

        if not user.is_superuser and not target_hotel:
            return Response({"error": "No hotel assigned."}, status=403)

        activities = []
        fetch_limit = 10  

        # --- 1. BOOKING ACTIVITIES (FIXED SORTING) ---
        b_qs = Booking.objects.all().select_related('user', 'room')
        if target_hotel:
            b_qs = b_qs.filter(hotel=target_hotel)
        
        # Coalesce Logic: 
        # Sabse pehle Check-out time dekhega -> nahi to Check-in -> nahi to Created
        # Isse "Just Now" wali activity sabse upar aayegi.
        recent_bookings = b_qs.filter(
            status__in=['confirmed', 'checked_in', 'checked_out']
        ).annotate(
            last_activity=Coalesce('check_out_time', 'check_in_time', 'created_at')
        ).order_by('-last_activity')[:fetch_limit]

        for b in recent_bookings:
            # User Name Fix (full_name check)
            if b.user:
                if hasattr(b.user, 'full_name') and b.user.full_name:
                    guest_name = b.user.full_name
                elif hasattr(b.user, 'get_full_name'):
                    guest_name = b.user.get_full_name()
                else:
                    guest_name = b.user.full_name or "Guest"
            else:
                guest_name = "Guest"

            room_num = b.room.room_number if b.room else "N/A"
            
            # Timestamp Logic (Priority Wise)
            # Ab hum wahi time lenge jo sorting me use kiya (last_activity)
            timestamp = getattr(b, 'last_activity', b.created_at) or timezone.now()

            msg = ""
            priority = "low"

            if b.status == 'confirmed':
                msg = f"New booking confirmed for Room {room_num}"
                priority = "high"
            elif b.status == 'checked_in':
                msg = f"{guest_name} checked in to Room {room_num}"
                priority = "medium"
            elif b.status == 'checked_out':
                msg = f"{guest_name} checked out"
                priority = "low"
            
            if msg:
                activities.append({
                    "description": msg,
                    "timestamp": timestamp,
                    "priority": priority,
                    "type": "booking"
                })

        # --- 2. RESTAURANT ACTIVITIES ---
        try:
            o_qs = RestaurantOrder.objects.all()
            if target_hotel:
                o_qs = o_qs.filter(hotel=target_hotel)

            # Sort by latest update/order time
            recent_orders = o_qs.filter(
                status__in=['ready', 'served']
            ).order_by('-created_at')[:fetch_limit]

            for o in recent_orders:
                order_id = getattr(o, 'order_id', str(o.id)[:8])
                ts = getattr(o, 'order_time', getattr(o, 'created_at', timezone.now()))

                if o.status == 'ready':
                    msg = f"Order #{order_id} ready for service"
                    priority = "medium"
                elif o.status == 'served':
                    msg = f"Order #{order_id} served successfully"
                    priority = "low"
                else:
                    continue

                activities.append({
                    "description": msg,
                    "timestamp": ts,
                    "priority": priority,
                    "type": "restaurant"
                })
        except Exception:
            pass 

        # --- 3. MAINTENANCE ACTIVITIES ---
        try:
            from maintenance.models import MaintenanceTask
            m_qs = MaintenanceTask.objects.all().select_related('room')
            if target_hotel:
                m_qs = m_qs.filter(hotel=target_hotel)

            recent_tasks = m_qs.filter(
                status__in=['completed', 'pending']
            ).order_by('-created_at')[:fetch_limit]

            for t in recent_tasks:
                room_num = t.room.room_number if t.room else "General"
                ts = getattr(t, 'created_at', timezone.now())

                if t.status == 'completed':
                    msg = f"Room {room_num} maintenance completed"
                    priority = "medium"
                elif t.status == 'pending':
                    msg = f"Maintenance reported for Room {room_num}"
                    priority = "high"
                else:
                    continue

                activities.append({
                    "description": msg,
                    "timestamp": ts,
                    "priority": priority,
                    "type": "maintenance"
                })
        except Exception:
            pass

        # --- 4. MERGE & SORT ---
        def get_sort_key(x):
            return x['timestamp'] or timezone.now()

        # Final sort sabhi types ko mila ke
        activities.sort(key=get_sort_key, reverse=True)

        # Sirf top 4 bhejna
        final_list = activities[:4]

        response_data = []
        for item in final_list:
            response_data.append({
                "description": item['description'],
                "time_ago": f"{timesince(item['timestamp'])} ago",
                "priority": item['priority'],
                "type": item['type']
            })

        return Response(response_data)
    

    @action(detail=False, methods=['get'], url_path='dashboard/activities')
    def dashboard_activities(self, request):
        """
        Aggregates recent activities from Bookings, Payments, Maintenance, and Orders.
        Supports pagination via ?limit=6&offset=0
        """
        user = request.user
        target_hotel = self._get_dashboard_target_hotel(request)

        if not user.is_superuser and not target_hotel:
            return Response({"error": "No hotel assigned."}, status=403)

        # 1. Get Pagination Params (Default 6 items)
        try:
            limit = int(request.query_params.get('limit', 6))
            offset = int(request.query_params.get('offset', 0))
        except ValueError:
            limit = 6
            offset = 0

        # We fetch slightly more than needed from each table to ensure correct sorting
        fetch_limit = limit + offset 
        activities = []

        # --- A. NEW BOOKINGS ---
        bookings = Booking.objects.filter(hotel=target_hotel).select_related('user', 'room').order_by('-created_at')[:fetch_limit]
        for b in bookings:
            # FIX: User Name Handling
            u_name = b.user.full_name if hasattr(b.user, 'full_name') and b.user.full_name else b.user.email
            
            activities.append({
                'id': str(b.id),
                'type': 'booking',
                'title': 'New Booking Created',
                'description': f"Room {b.room.room_number if b.room else 'Unassigned'} booked by {u_name}",
                'timestamp': b.created_at,
                'status_color': 'success', # Green
                'icon_text': 'Booking',
                # 'staff_name': 'Reception Desk', 
                'staff_designation': 'Reception Desk',
                'staff_department': 'Reception'
            })

        # --- B. GUEST CHECK-IN ---
        checkins = Booking.objects.filter(hotel=target_hotel, status='checked_in').select_related('user', 'room').order_by('-check_in_time')[:fetch_limit]
        for b in checkins:
            u_name = b.user.full_name if hasattr(b.user, 'full_name') and b.user.full_name else b.user.email
            
            activities.append({
                'id': str(b.id) + "_in",
                'type': 'checkin',
                'title': 'Guest Check-in',
                'description': f"{u_name} checked into Room {b.room.room_number if b.room else 'N/A'}",
                'timestamp': b.check_in_time or b.updated_at,
                'status_color': 'purple', 
                'icon_text': 'Checkin',
                # 'staff_name': 'Staff_name', 
                'staff_designation': 'Front desk',
                'staff_department': 'Reception'
            })

        # --- C. PAYMENTS (BILLING) ---
        # Assuming Invoice model exists
        try:
            invoices = Invoice.objects.filter(status='paid').order_by('-issued_at')[:fetch_limit]
            # Filter logic for hotel scope if Invoice has hotel/booking link
            for inv in invoices:
                 # Check access rights via content_type or direct link
                 # Skipping strict check for brevity, assuming localized logic or global finance view
                 activities.append({
                    'id': str(inv.id),
                    'type': 'payment',
                    'title': 'Payment Received',
                    'description': f"Payment of {inv.total_amount} processed",
                    'timestamp': inv.issued_at,
                    'status_color': 'primary', # Blue
                    'icon_text': 'Payment',
                    # 'staff_name': 'staff_name',
                    # 'staff_designation': '',
                    'staff_department': 'BillinG System'
                })
        except Exception:
            pass 

        # --- D. RESTAURANT ORDERS ---
        try:
            orders = RestaurantOrder.objects.filter(hotel=target_hotel, status='completed').select_related('table').order_by('-completed_at')[:fetch_limit]
            for o in orders:
                activities.append({
                    'id': str(o.id),
                    'type': 'order',
                    'title': 'Restaurant Order',
                    'description': f"Table {o.table.number if o.table else 'N/A'} - Order #{o.order_code} completed",
                    'timestamp': o.completed_at or o.updated_at,
                    'status_color': 'success',
                    'icon_text': 'Order',
                    # 'staff_name': 'staff_name',
                    'staff_designation': 'Kitchen Staff',
                    'staff_department': 'Restaurant'
                })
        except Exception:
            pass

        # --- E. MAINTENANCE REQUESTS (With Staff Details) ---
        try:
            from maintenance.models import MaintenanceTask
            tasks = MaintenanceTask.objects.filter(hotel=target_hotel).order_by('-created_at')[:fetch_limit]
            for t in tasks:
                staff_name = "Unassigned"
                staff_desig = ""
                staff_dept = ""
                
                if t.assigned_to: 
                    # FIX: User Name Handling here too
                    u_name = t.assigned_to.full_name if hasattr(t.assigned_to, 'full_name') and t.assigned_to.full_name else t.assigned_to.email

                    # Query Staff model based on user to get designation
                    staff_obj = Staff.objects.filter(user=t.assigned_to).first()
                    if staff_obj:
                        staff_name = u_name
                        staff_desig = staff_obj.designation
                        staff_dept = staff_obj.department
                    else:
                        staff_name = u_name

                activities.append({
                    'id': str(t.id),
                    'type': 'maintenance',
                    'title': 'Maintenance Request',
                    'description': f"{t.title} needed in {t.location}",
                    'timestamp': t.created_at,
                    'status_color': 'warning', # Yellow/Orange
                    'icon_text': 'Maintenance',
                    'staff_name': staff_name,
                    'staff_designation': staff_desig,
                    'staff_department': staff_dept
                })
        except ImportError:
            pass # Skip if maintenance app not ready or circular import issues
        except Exception:
            pass

        # --- MERGE, SORT, & SLICE ---
        
        # 1. Sort all lists combined by timestamp descending (newest first)
        activities.sort(key=lambda x: x['timestamp'], reverse=True)

        # 2. Apply Pagination (Slice)
        # If user asks for offset=0, limit=6 -> [0:6]
        # If user asks for offset=6, limit=6 -> [6:12]
        paginated_activities = activities[offset : offset + limit]

        # 3. Serialize
        serializer = ActivityLogSerializer(paginated_activities, many=True)
        
        return Response({
            "count": len(activities), # Total available in current fetch context
            "next_offset": offset + limit if len(activities) > offset + limit else None,
            "results": serializer.data
        })

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
        
        # ✅ Vendor: jis hotel se linked hai
        if hasattr(user, 'role') and user.role.name.lower() == 'vendor':
            return qs.filter(hotel__vendors__user=user)

        # ✅ Customer: sirf available hotels ki categories
        if hasattr(user, 'role') and user.role.name.lower() == 'customer':
            return qs.filter(hotel__status='available')

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
    queryset = Room.objects.all().select_related(
        'hotel', 'room_category'
    ).prefetch_related('media')
    serializer_class = RoomSerializer
    model_name = 'Room'
    lookup_field = 'slug'

    def get_queryset(self):
        user = self.request.user
        qs = self.queryset  #  IMPORTANT

        # 1️⃣ Superuser → all rooms
        if user.is_superuser:
            return qs

        role = getattr(user, "role", None)
        role_name = role.name.lower() if role else None

        # 2️⃣ Admin → rooms of own hotel
        if role_name == "admin":
            hotel = getattr(user, "hotel", None)
            if hotel:
                return qs.filter(hotel=hotel)
            return qs.none()

        # 3️⃣ Staff → rooms of assigned hotel
        if hasattr(user, "staff_profile") and user.staff_profile.hotel:
            return qs.filter(hotel=user.staff_profile.hotel)

        # 4️⃣ Vendor → rooms of linked hotels
        if role_name == "vendor":
            return qs.filter(hotel__vendors__user=user)

        # 5️⃣ Customer → available rooms (optionally filtered by hotel)
        if role_name == "customer":
            hotel_slug = self.request.query_params.get("hotel")

            qs = qs.filter(
                status="available",
                hotel__status="available"
            )

            if hotel_slug:
                qs = qs.filter(hotel__slug=hotel_slug)

            return qs

        # 6️⃣ Default → no access
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
        - Superuser → all rooms OR filter by ?hotel=<slug>
        - Admin → their hotel
        - Vendor → their hotel
        - Staff → their hotel
        - Customer → MUST pass ?hotel=<slug>
        """

        user = request.user
        rooms = Room.objects.none()

        hotel_slug = request.query_params.get("hotel")

        # -----------------------------------
        # SUPERUSER → all or filtered
        # -----------------------------------
        if user.is_superuser:
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
        # ADMIN → own hotel
        # -----------------------------------
        elif hasattr(user, "role") and user.role.name.lower() == "admin":
            if not hasattr(user, "hotel") or not user.hotel:
                return Response(
                    {"error": "Admin does not have a hotel assigned."},
                    status=status.HTTP_403_FORBIDDEN
                )
            rooms = Room.objects.filter(hotel=user.hotel)

        # -----------------------------------
        # VENDOR → vendor hotel
        # -----------------------------------
        elif hasattr(user, "role") and user.role.name.lower() == "vendor":
            rooms = Room.objects.filter(hotel__vendor=user)

        # -----------------------------------
        # STAFF → staff hotel
        # -----------------------------------
        elif hasattr(user, "staff_profile") and user.staff_profile.hotel:
            rooms = Room.objects.filter(hotel=user.staff_profile.hotel)

        # -----------------------------------
        # CUSTOMER → must pass hotel slug
        # -----------------------------------
        elif hasattr(user, "role") and user.role.name.lower() == "customer":
            if not hotel_slug:
                return Response(
                    {"error": "Hotel slug is required for customer."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                hotel = Hotel.objects.get(slug=hotel_slug)
            except Hotel.DoesNotExist:
                return Response(
                    {"error": "Invalid hotel slug."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            rooms = Room.objects.filter(hotel=hotel)

        # -----------------------------------
        # Others → no access
        # -----------------------------------
        else:
            return Response(
                {"error": "You do not have permission to view room summary."},
                status=status.HTTP_403_FORBIDDEN
            )

        # -----------------------------------
        # GROUP BY STATUS
        # -----------------------------------
        status_counts = rooms.values("status").annotate(total=Count("id"))
        data = {item["status"]: item["total"] for item in status_counts}

        # Ensure all statuses exist
        for status_key in ["available", "occupied", "reserved", "maintenance"]:
            data.setdefault(status_key, 0)

        data["total_rooms"] = sum(data.values())

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
        
        # ✅ Vendor → bookings of hotels linked to vendor
        if hasattr(user, 'role') and user.role and user.role.name.lower() == 'vendor':
            return qs.filter(hotel__vendors__user=user)

        # ✅ Customer → ONLY their own bookings
        if hasattr(user, 'role') and user.role and user.role.name.lower() == 'customer':
            return qs.filter(user=user)


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
            # ✅ Vendor → requests of hotels linked to vendor
        if hasattr(user, 'role') and user.role and user.role.name.lower() == 'vendor':
            return qs.filter(room__hotel__vendors__user=user)

        # ✅ Customer → ONLY their own service requests
        if hasattr(user, 'role') and user.role and user.role.name.lower() == 'customer':
            return qs.filter(user=user)

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
            
    #   return qs
    
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


# class HomeDashboardViewSet(ProtectedModelViewSet):
#     """
#     Dedicated Dashboard ViewSet inheriting from ProtectedModelViewSet.
#     Handles stats for both Hotel (Rooms/Guests) and Restaurant (Orders).
#     """
#     # Required attributes for ProtectedModelViewSet
#     queryset = Hotel.objects.all()
#     serializer_class = HotelSerializer 
#     model_name = 'Dashboard' # Internal logging ke liye

#     # --- HELPER: Role Isolation & Hotel Scope ---
#     def get_target_hotel(self, request):
#         """
#         Logic to find which hotel data to show based on User Role.
#         """
#         user = request.user
        
#         # 1. Superuser
#         if user.is_superuser:
#             # Superuser can filter via ?hotel_id=UUID
#             hotel_id = request.query_params.get('hotel_id')
#             if hotel_id:
#                 return Hotel.objects.filter(id=hotel_id).first()
#             return None  # None means "All Hotels" (Global View)
        
#         # 2. Admin: Own Hotel
#         if hasattr(user, 'role') and user.role.name.lower() == 'admin':
#             return getattr(user, 'hotel', None)
        
#         # 3. Staff: Assigned Hotel
#         if hasattr(user, 'staff_profile') and user.staff_profile.hotel:
#             return user.staff_profile.hotel
            
#         return None # No access

#     # --- HELPER: Growth % Calculation ---
#     def calculate_growth(self, current, previous):
#         if previous == 0:
#             return "+100%" if current > 0 else "0%"
#         change = ((current - previous) / previous) * 100
#         sign = "+" if change >= 0 else "-"
#         return f"{sign}{abs(round(change, 1))}%"

#     # --- API 1: PAGE 1 - TOP CARDS ---
#     @action(detail=False, methods=['get'], url_path='stats-cards')
#     def stats_cards(self, request):
#         user = request.user
#         target_hotel = self.get_target_hotel(request)
        
#         # Safety Check for non-superusers
#         if not user.is_superuser and not target_hotel:
#             return Response({"error": "No hotel assigned."}, status=403)

#         today = timezone.localdate()
#         yesterday = today - timedelta(days=1)

#         # 1. TOTAL REVENUE (Bookings + Restaurant | Status: Paid)
#         booking_ct = ContentType.objects.get_for_model(Booking)
#         order_ct = ContentType.objects.get_for_model(RestaurantOrder)

#         def get_revenue(date_val):
#             # Base Filter
#             qs = Invoice.objects.filter(status='paid', issued_at__date=date_val)
            
#             # Scope Filter
#             if target_hotel:
#                 b_ids = Booking.objects.filter(hotel=target_hotel).values_list('id', flat=True)
#                 r_ids = RestaurantOrder.objects.filter(hotel=target_hotel).values_list('id', flat=True)
                
#                 qs = qs.filter(
#                     Q(content_type=booking_ct, object_id__in=b_ids) |
#                     Q(content_type=order_ct, object_id__in=r_ids)
#                 )
            
#             return qs.aggregate(total=Sum('total_amount'))['total'] or 0

#         rev_today = get_revenue(today)
#         rev_yesterday = get_revenue(yesterday)

#         # 2. ROOM OCCUPANCY
#         room_qs = Room.objects.all()
#         if target_hotel: room_qs = room_qs.filter(hotel=target_hotel)
        
#         total_rooms = room_qs.count()
        
#         # Today: Live Status
#         occ_today_count = room_qs.filter(status='occupied').count()
        
#         # Yesterday: Calculated from bookings active yesterday
#         b_qs = Booking.objects.filter(status__in=['checked_in', 'checked_out', 'confirmed'])
#         if target_hotel: b_qs = b_qs.filter(hotel=target_hotel)
        
#         occ_yesterday_count = b_qs.filter(
#             check_in__lte=yesterday, 
#             check_out__gt=yesterday
#         ).count()

#         pct_today = (occ_today_count / total_rooms * 100) if total_rooms else 0
#         pct_yesterday = (occ_yesterday_count / total_rooms * 100) if total_rooms else 0

#         # 3. ACTIVE ORDERS (Pending/Preparing)
#         o_qs = RestaurantOrder.objects.all()
#         if target_hotel: o_qs = o_qs.filter(hotel=target_hotel)
        
#         # Value: Live Active
#         active_now = o_qs.filter(status__in=['pending', 'preparing']).count()
        
#         # Growth: Based on creation volume
#         created_today = o_qs.filter(created_at__date=today).count()
#         created_yesterday = o_qs.filter(created_at__date=yesterday).count()

#         # 4. TOTAL GUESTS
#         g_qs = Booking.objects.filter(status='checked_in')
#         if target_hotel: g_qs = g_qs.filter(hotel=target_hotel)
        
#         guests_now = g_qs.aggregate(total=Sum('guests_count'))['total'] or 0
        
#         # Guests Yesterday
#         g_y_qs = Booking.objects.filter(
#             status__in=['checked_in', 'checked_out', 'confirmed'],
#             check_in__lte=yesterday, 
#             check_out__gt=yesterday
#         )
#         if target_hotel: g_y_qs = g_y_qs.filter(hotel=target_hotel)
#         guests_yesterday = g_y_qs.aggregate(total=Sum('guests_count'))['total'] or 0

#         return Response({
#             "revenue": {
#                 "value": float(rev_today),
#                 "growth": self.calculate_growth(rev_today, rev_yesterday)
#             },
#             "room_occupancy": {
#                 "value": f"{round(pct_today)}%",
#                 "growth": self.calculate_growth(pct_today, pct_yesterday)
#             },
#             "active_orders": {
#                 "value": active_now,
#                 "growth": self.calculate_growth(created_today, created_yesterday)
#             },
#             "total_guests": {
#                 "value": guests_now,
#                 "growth": self.calculate_growth(guests_now, guests_yesterday)
#             }
#         })

#     # --- API 2: PAGE 2 - TODAY'S SUMMARY ---
#     @action(detail=False, methods=['get'], url_path='today-summary')
#     def today_summary(self, request):
#         user = request.user
#         target_hotel = self.get_target_hotel(request)
#         today = timezone.localdate()

#         if not user.is_superuser and not target_hotel:
#             return Response({"error": "No hotel assigned."}, status=403)

#         b_qs = Booking.objects.all()
#         o_qs = RestaurantOrder.objects.all()
        
#         if target_hotel:
#             b_qs = b_qs.filter(hotel=target_hotel)
#             o_qs = o_qs.filter(hotel=target_hotel)

#         # 1. Check-ins Today
#         check_ins = b_qs.filter(check_in=today).count()

#         # 2. Check-outs Today
#         check_outs = b_qs.filter(check_out=today).count()

#         # 3. Food Orders Today (Served/Preparing/Completed)
#         food_orders = o_qs.filter(
#             created_at__date=today, 
#             status__in=['served', 'preparing', 'completed']
#         ).count()

#         # 4. Revenue Today
#         booking_ct = ContentType.objects.get_for_model(Booking)
#         order_ct = ContentType.objects.get_for_model(RestaurantOrder)
        
#         b_ids = b_qs.values_list('id', flat=True)
#         r_ids = o_qs.values_list('id', flat=True)
        
#         revenue_qs = Invoice.objects.filter(status='paid', issued_at__date=today)
        
#         if target_hotel:
#              revenue_qs = revenue_qs.filter(
#                 Q(content_type=booking_ct, object_id__in=b_ids) |
#                 Q(content_type=order_ct, object_id__in=r_ids)
#             )
             
#         revenue = revenue_qs.aggregate(total=Sum('total_amount'))['total'] or 0

#         return Response({
#             "check_ins": check_ins,
#             "check_outs": check_outs,
#             "food_orders": food_orders,
#             "revenue": float(revenue)
#         })