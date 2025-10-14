from MBP.views import ProtectedModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import (
    MenuCategory, MenuItem, Table, RestaurantOrder, OrderItem, TableReservation
)
from .serializers import (
    MenuCategorySerializer, MenuItemSerializer, TableSerializer,
    RestaurantOrderSerializer, OrderItemSerializer, TableReservationSerializer
)
from django.db.models import Sum, F, Avg, DurationField, ExpressionWrapper
from datetime import date
from Billing.models import Payment


class MenuCategoryViewSet(ProtectedModelViewSet):
    queryset = MenuCategory.objects.all()
    serializer_class = MenuCategorySerializer
    model_name = 'MenuCategory'
    lookup_field = 'slug'


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


class RestaurantOrderViewSet(ProtectedModelViewSet):
    queryset = RestaurantOrder.objects.all().select_related('table', 'hotel')
    serializer_class = RestaurantOrderSerializer
    model_name = 'RestaurantOrder'
    lookup_field = 'slug'
    
    def get_queryset(self):
        queryset = super().get_queryset()
        hotel_id = self.request.query_params.get('hotel')
        if hotel_id:
            queryset = queryset.filter(hotel_id=hotel_id)
        return queryset
    
    @action(detail=False, methods=['get'], url_path='summary')
    def order_summary(self, request):
        total_orders = RestaurantOrder.objects.count()
        active_orders = RestaurantOrder.objects.filter(status__in=['pending', 'preparing']).count()

        return Response({
            'total_orders': total_orders,
            'active_orders': active_orders,
        })


class OrderItemViewSet(ProtectedModelViewSet):
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializer
    model_name = 'OrderItem'
    lookup_field = 'slug'

class RestaurantDashboardViewSet(ProtectedModelViewSet):
    """
    Protected dashboard API for restaurant analytics.
    Requires authentication + model-based permission.
    """

    model_name = "restaurantdashboard" 

    @action(detail=False, methods=['get'], url_path='dashboard-summary')
    def dashboard_summary(self, request):
        hotel_id = request.query_params.get('hotel')

        # 🔹 Base QuerySets
        tables = Table.objects.all()
        orders = RestaurantOrder.objects.all()
        payments = Payment.objects.all()

        # 🔹 Optional Hotel Filter
        if hotel_id:
            tables = tables.filter(hotel_id=hotel_id)
            orders = orders.filter(table__hotel_id=hotel_id)
            payments = payments.filter(invoice__hotel_id=hotel_id)

        # 1️⃣ Available Tables
        available_tables = tables.filter(status='available').count()

        # 2️⃣ Active Orders
        active_orders = orders.filter(status__in=['pending', 'preparing', 'served']).count()

        # 3️⃣ Today's Revenue
        today = date.today()
        todays_revenue = payments.filter(payment_date__date=today).aggregate(
            total=Sum('amount_paid')
        )['total'] or 0

        # 4️⃣ Average Wait Time
        avg_wait_minutes = 0
        if hasattr(RestaurantOrder, 'completed_at') and hasattr(RestaurantOrder, 'order_time'):
            avg_expr = ExpressionWrapper(
                F('completed_at') - F('order_time'),
                output_field=DurationField()
            )
            avg_wait_time = orders.filter(status='completed').aggregate(avg=Avg(avg_expr))['avg']
            if avg_wait_time:
                avg_wait_minutes = round(avg_wait_time.total_seconds() / 60, 2)

        return Response({
            "available_tables": available_tables,
            "active_orders": active_orders,
            "todays_revenue": float(todays_revenue),
            "avg_wait_time": f"{avg_wait_minutes} min",
        })

class TableReservationViewSet(ProtectedModelViewSet):
    """
    Manage Table Reservations.
    - Superadmin/Admin: can view, create, update, delete all reservations
    - Staff: can view and manage reservations for their assigned hotel tables only
    - Public: cannot access unless explicitly allowed
    """
    queryset = TableReservation.objects.all().order_by('-created_at')
    serializer_class = TableReservationSerializer
    model_name = 'TableReservation'  # required for RoleModelPermission mapping

    def get_queryset(self):
        user = self.request.user

        # 🧠 Superusers and Admins see all reservations
        if user.is_superuser or (hasattr(user, "role") and user.role.name.lower() in ["Admin"]):
            return TableReservation.objects.all().order_by('-created_at')

        # 🧠 Staff linked to a hotel can see only their hotel's table reservations
        if hasattr(user, "staff_profile") and user.staff_profile.hotel:
            hotel = user.staff_profile.hotel
            return TableReservation.objects.filter(table__hotel=hotel).order_by('-created_at')

        # 🧠 Other users (like customers) can see their own reservations
        return TableReservation.objects.filter(email=user.email).order_by('-created_at')