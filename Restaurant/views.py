from MBP.views import ProtectedModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import (
    MenuCategory, MenuItem, Table, RestaurantOrder, OrderItem, TableReservation
)
from .serializers import (
    MenuCategorySerializer, MenuItemSerializer, TableSerializer,
    RestaurantOrderSerializer, OrderItemSerializer, TableReservationSerializer,
    RestaurantDashboardSerializer
)
from django.db.models import Sum, F, Avg, DurationField, ExpressionWrapper
from datetime import date
from Billing.models import Payment
from rest_framework import status


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

        # ✅ Hotel admin: Only own hotel’s data
        hotel = getattr(user, 'hotel', None) or getattr(user, 'hotel_profile', None)
        if hotel:
            # handle both if user.hotel or user.hotel_profile.hotel exists
            hotel_obj = getattr(hotel, 'hotel', hotel)
            return RestaurantOrder.objects.filter(hotel=hotel_obj).select_related('hotel', 'table')

        # ✅ Other users (no hotel assigned): Empty set
        return RestaurantOrder.objects.none()

    def get_serializer_context(self):
        """Pass request into serializer for user-hotel linking."""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
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
        active_orders = orders.filter(
            status__in=['pending', 'preparing', 'served']
        ).count()

        # ✅ 3. Today's Revenue (from order totals, not payments)
        today = date.today()
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

    