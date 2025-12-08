from MBP.views import ProtectedModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from datetime import datetime
from django.utils.text import slugify

from .models import (
    MenuCategory, MenuItem, Table, RestaurantOrder, OrderItem, TableReservation, Restaurant, BookingCallback
)
from .serializers import (
    MenuCategorySerializer, MenuItemSerializer, TableSerializer,
    RestaurantOrderSerializer, OrderItemSerializer, TableReservationSerializer,
    RestaurantDashboardSerializer, RestaurantSerializer, BookingCallbackSerializer,TableSearchSerializer
)
from django.db.models import Sum, F, Avg, DurationField, ExpressionWrapper,Count,Q
from datetime import date
from Billing.models import Payment
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework import generics, filters


class RestaurantViewSet(ProtectedModelViewSet):
    queryset = Restaurant.objects.all()
    serializer_class = RestaurantSerializer
    model_name = 'Restaurant'
    lookup_field = 'slug'
    
    def get_queryset(self):
        user = self.request.user

        # ✅ Superuser can see all Restaurants
        if user.is_superuser:
            return Restaurant.objects.all()

        # ✅ Admins can see only their own Restaurant
        if hasattr(user, 'role') and user.role.name.lower() == 'admin':
            return Restaurant.objects.filter(owner=user)

        # ✅ Staff can see their Restaurant (if linked)
        if hasattr(user, 'staff_profile') and user.staff_profile.Restaurant:
            return Restaurant.objects.filter(id=user.staff_profile.Restaurant.id)

        return Restaurant.objects.none()
    
    @action(detail=False, methods=['get'], url_path='stats')
    def Restaurant_stats(self, request):
        """
        Custom endpoint to show Restaurant statistics.
        Example: /api/Restaurants/stats/
        """
        qs = self.get_queryset()

        # Aggregate counts by status
        total_Restaurants = qs.count()
        status_counts = qs.values('status').annotate(total=Count('status'))

        stats = {
            'total_Restaurants': total_Restaurants,
            'open': 0,
            # 'maintenance': 0,
            'closed': 0
        }

        for entry in status_counts:
            stats[entry['status']] = entry['total']

        return Response(stats, status=status.HTTP_200_OK)

    def perform_create(self, serializer):
        # Auto-generate slug if not provided
        name = serializer.validated_data.get('name')
        slug = slugify(name)

        # Ensure only one Restaurant per admin
        owner = serializer.validated_data.get('owner')
        if owner and Restaurant.objects.filter(owner=owner).exists():
            return Response(
                {"error": f"Admin {owner.full_name} already owns a Restaurant."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer.save(slug=slug)

class MenuCategoryViewSet(ProtectedModelViewSet):
    queryset = MenuCategory.objects.all()
    serializer_class = MenuCategorySerializer
    model_name = 'MenuCategory'
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


class MenuItemViewSet(ProtectedModelViewSet):
    queryset = MenuItem.objects.all()
    serializer_class = MenuItemSerializer
    model_name = 'MenuItem'
    lookup_field = 'slug'
    
    


class TableViewSet(ProtectedModelViewSet):
    queryset = Table.objects.all()
    serializer_class = TableSerializer
    model_name = 'Table'
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


class RestaurantOrderViewSet(ProtectedModelViewSet):
    queryset = RestaurantOrder.objects.all().select_related('table', 'hotel')
    serializer_class = RestaurantOrderSerializer
    model_name = 'RestaurantOrder'
    lookup_field = 'slug'
    
    def get_queryset(self):
        user = self.request.user

        # ✅ Superuser: Full access
        if user.is_superuser:
            return RestaurantOrder.objects.all().select_related('hotel', 'table')

        # ✅ Hotel Admin (assigned hotel)
        hotel = getattr(user, 'hotel', None) or getattr(user, 'hotel_profile', None)
        if hotel:
            hotel_obj = getattr(hotel, 'hotel', hotel)
            return RestaurantOrder.objects.filter(hotel=hotel_obj).select_related('hotel', 'table')

        # ✅ Staff assigned to a hotel
        if hasattr(user, 'staff_profile') and user.staff_profile.hotel:
            return RestaurantOrder.objects.filter(hotel=user.staff_profile.hotel).select_related('hotel', 'table')

        # ✅ Others
        return RestaurantOrder.objects.none()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
    @action(detail=False, methods=['get'], url_path='today')
    def today_orders(self, request):
        today = date.today()

        qs = self.get_queryset().filter(order_time__date=today)

        serializer = self.get_serializer(qs, many=True)
        return Response({
            "date": str(today),
            "total_orders": qs.count(),
            "orders": serializer.data
        })
    
    @action(detail=False, methods=['get'], url_path='filter-by-date')
    def filter_by_date(self, request):
        date_str = request.query_params.get('date')

        if not date_str:
            return Response({"error": "date parameter is required (YYYY-MM-DD)"}, status=400)

        try:
            filter_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return Response({"error": "Invalid date format"}, status=400)

        qs = self.get_queryset().filter(order_time__date=filter_date)

        serializer = self.get_serializer(qs, many=True)
        return Response({
            "date": date_str,
            "total_orders": qs.count(),
            "orders": serializer.data
        })

    @action(detail=False, methods=['get'], url_path='filter-by-month')
    def filter_by_month(self, request):
        year = request.query_params.get('year')
        month = request.query_params.get('month')

        if not year or not month:
            return Response({"error": "year and month parameters are required"}, status=400)

        try:
            year = int(year)
            month = int(month)
        except ValueError:
            return Response({"error": "year and month must be integers"}, status=400)

        qs = self.get_queryset().filter(
            order_time__year=year,
            order_time__month=month
        )

        serializer = self.get_serializer(qs, many=True)
        return Response({
            "year": year,
            "month": month,
            "total_orders": qs.count(),
            "orders": serializer.data
        })

    
    @action(detail=False, methods=['get'], url_path='summary')
    def order_summary(self, request):
        user = request.user
        queryset = RestaurantOrder.objects.all()

        # ✅ Restrict data visibility based on user role
        if not user.is_superuser:
            if hasattr(user, 'role') and user.role.name.lower() == 'admin':
                queryset = queryset.filter(hotel__owner=user)
            elif hasattr(user, 'staff_profile') and user.staff_profile.hotel:
                queryset = queryset.filter(hotel=user.staff_profile.hotel)
            else:
                queryset = queryset.none()

        # ✅ Compute order summary counts
        total_orders = queryset.count()
        active_orders = queryset.filter(status__in=['pending', 'preparing']).count()
        completed_orders = queryset.filter(status='completed').count()
        cancelled_orders = queryset.filter(status='cancelled').count()

        return Response({
            "total_orders": total_orders,
            "active_orders": active_orders,
            "completed_orders": completed_orders,
            "cancelled_orders": cancelled_orders,
        })


class OrderItemViewSet(ProtectedModelViewSet):
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializer
    model_name = 'OrderItem'
    lookup_field = 'slug'

class RestaurantDashboardViewSet(ProtectedModelViewSet):
    model_name = "restaurantdashboard"
    queryset = None
    http_method_names = ['get']
    serializer_class = RestaurantDashboardSerializer
    
    def get_queryset(self):
        """
        Required ONLY so Swagger stops calling default get_queryset().
        """
        if getattr(self, "swagger_fake_view", False):
            return []  # short-circuit for schema generation
        
        # This view has no queryset in real use
        return Table.objects.none()

    def get_serializer_class(self):
        """
        Swagger calls this even though we do not use serializers for response.
        """
        if getattr(self, "swagger_fake_view", False):
            return RestaurantDashboardSerializer
        return RestaurantDashboardSerializer

    @action(detail=False, methods=['get'], url_path='dashboard-summary')
    def dashboard_summary(self, request):
        user = request.user
        hotel_id = request.query_params.get('hotel')

        # Base QuerySets
        tables = Table.objects.all()
        orders = RestaurantOrder.objects.all()

        # ✅ Role-Based Filtering
        if not user.is_superuser:
            if hasattr(user, 'role') and user.role.name.lower() == 'admin':
                tables = tables.filter(hotel__owner=user)
                orders = orders.filter(hotel__owner=user)

            elif hasattr(user, 'staff_profile') and user.staff_profile.hotel:
                hotel = user.staff_profile.hotel
                tables = tables.filter(hotel=hotel)
                orders = orders.filter(hotel=hotel)

            else:
                return Response(
                    {"error": "You are not associated with any hotel."},
                    status=403
                )

        # ✅ Optional Manual Filter
        if hotel_id:
            tables = tables.filter(hotel_id=hotel_id)
            orders = orders.filter(hotel_id=hotel_id)

        # ✅ 1. Available Tables
        available_tables = tables.filter(status='available').count()

        # ✅ 2. Active Orders
        today = date.today()
        active_orders = orders.filter(
            order_time__date=today,
            status__in=['pending', 'preparing', 'served']
        ).count()

        # ✅ 3. Today's Revenue (from order totals, not payments)
        todays_revenue = (
            orders.filter(
                order_time__date=today,
                status__in=['served', 'completed'],
            ).aggregate(total=Sum('grand_total'))['total'] or 0
        )

        # ✅ 4. Average Wait Time
        avg_wait_minutes = 0
        avg_expr = ExpressionWrapper(
            F('completed_at') - F('order_time'),
            output_field=DurationField()
        )
        avg_wait_time = (
            orders.filter(
                status='completed',
                completed_at__isnull=False
            ).aggregate(avg=Avg(avg_expr))['avg']
        )
        if avg_wait_time:
            avg_wait_minutes = round(avg_wait_time.total_seconds() / 60, 2)

        # ✅ Final Response
        return Response({
            "available_tables": available_tables,
            "active_orders": active_orders,
            "todays_revenue": float(todays_revenue),
            "avg_wait_time": f"{avg_wait_minutes} min"
        })

        
        
class TableReservationViewSet(ProtectedModelViewSet):
    """
    Manage Table Reservations.
    - Superuser/Admin: full access to all reservations
    - Staff: access limited to their hotel's tables
    - Customers: only their own reservations (matched by email)
    """
    queryset = TableReservation.objects.all().order_by('-created_at')
    serializer_class = TableReservationSerializer
    model_name = 'TableReservation'  # required for RoleModelPermission mapping

    def get_queryset(self):
        user = self.request.user
        qs = TableReservation.objects.all().order_by('-created_at')

        # 🔹 Superuser: full access
        if user.is_superuser:
            return qs

        # 🔹 Admin (hotel owner): only their hotel's reservations
        if hasattr(user, 'role') and user.role.name.lower() == 'admin':
            return qs.filter(table__hotel__owner=user)

        # 🔹 Staff: only reservations for their assigned hotel
        if hasattr(user, 'staff_profile') and user.staff_profile.hotel:
            hotel = user.staff_profile.hotel
            return qs.filter(table__hotel=hotel)

        # 🔹 Customers (regular users): only their own reservations
        if user.is_authenticated and user.email:
            return qs.filter(email=user.email)

        # 🔹 Otherwise: no access
        return qs.none()

    
class BookingCallbackView(generics.CreateAPIView):
    """
    Public API to submit a callback request.
    No Authentication required.
    """
    queryset = BookingCallback.objects.all()
    serializer_class = BookingCallbackSerializer
    permission_classes = [AllowAny]


class PublicTableSearchView(generics.ListAPIView):
    """
    Public API to search available Tables based on City.
    Uses Table model but filters via connected Hotel's city.
    """
    serializer_class = TableSearchSerializer
    permission_classes = [AllowAny] # Login jaruri nahi

    def get_queryset(self):
        # Sirf wahi tables dikhayenge jo 'available' hain
        queryset = Table.objects.filter(status='available')

        # User se query params lena (Image 2 ke according)
        city_query = self.request.query_params.get('city', None)
        people_count = self.request.query_params.get('people', None)

        # 1. City Filter (Hotel model ke through)
        if city_query:
            queryset = queryset.filter(hotel__city__icontains=city_query)

        # 2. People Filter (Table Capacity ke hisaab se)
        # Agar user 4 logo ke liye table dhund rha h, to capacity >= 4 honi chahiye
        if people_count:
            try:
                queryset = queryset.filter(capacity__gte=int(people_count))
            except ValueError:
                pass # Agar user ne number nahi bheja to ignore karo

        return queryset