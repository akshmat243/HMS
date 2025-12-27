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
    queryset = MenuCategory.objects.select_related("restaurant")
    serializer_class = MenuCategorySerializer
    model_name = "MenuCategory"
    lookup_field = "slug"

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

        # 1️⃣ Superuser → all
        if user.is_superuser:
            return qs

        role = getattr(user, "role", None)
        if not role:
            return qs.none()

        role_name = role.name.lower()

        # 2️⃣ Admin → own restaurant
        if role_name == "admin":
            return qs.filter(restaurant__owner=user)

        # 3️⃣ Staff → assigned restaurant
        if role_name == "staff":
            if hasattr(user, "staff_profile") and user.staff_profile.restaurant:
                return qs.filter(
                    restaurant=user.staff_profile.restaurant
                )
            return qs.none()

        # 4️⃣ Customer → only open restaurants
        if role_name == "customer":
            return qs.filter(
                restaurant__status="open"
            )

        # 5️⃣ Others → nothing
        return qs.none()



class MenuItemViewSet(ProtectedModelViewSet):
    queryset = MenuItem.objects.select_related(
        "category",
        "category__restaurant"
    )
    serializer_class = MenuItemSerializer
    model_name = "MenuItem"
    lookup_field = "slug"

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

        # 1️⃣ Superuser → all menu items
        if user.is_superuser:
            return qs

        role = getattr(user, "role", None)
        if not role:
            return qs.none()

        role_name = role.name.lower()

        # 2️⃣ Admin → own restaurant only
        if role_name == "admin":
            return qs.filter(
                category__restaurant__owner=user
            )

        # 3️⃣ Staff → assigned restaurant only
        if role_name == "staff":
            if hasattr(user, "staff_profile") and user.staff_profile.restaurant:
                return qs.filter(
                    category__restaurant=user.staff_profile.restaurant
                )
            return qs.none()

        # 4️⃣ Customer → open restaurants only
        if role_name == "customer":
            return qs.filter(
                category__restaurant__status="open",
                is_available=True  # optional if you have this field
            )

        # 5️⃣ Others → no access
        return qs.none()

    

class TableViewSet(ProtectedModelViewSet):
    queryset = Table.objects.select_related("restaurant")
    serializer_class = TableSerializer
    model_name = "Table"
    lookup_field = "slug"

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

        # 1️⃣ Superuser → all tables
        if user.is_superuser:
            return qs

        role = getattr(user, "role", None)
        if not role:
            return qs.none()

        role_name = role.name.lower()

        # 2️⃣ Admin → own restaurant tables
        if role_name == "admin":
            return qs.filter(
                restaurant__owner=user
            )

        # 3️⃣ Staff → assigned restaurant tables
        if role_name == "staff":
            if hasattr(user, "staff_profile") and user.staff_profile.restaurant:
                return qs.filter(
                    restaurant=user.staff_profile.restaurant
                )
            return qs.none()

        # 4️⃣ Customer → tables of open restaurants
        if role_name == "customer":
            qs = qs.filter(
                restaurant__status="open"
            )

            # Optional: only show available tables
            status_param = self.request.query_params.get("status")
            if status_param:
                qs = qs.filter(status=status_param)

            return qs

        # 5️⃣ Others → no access
        return qs.none()


class RestaurantOrderViewSet(ProtectedModelViewSet):
    queryset = RestaurantOrder.objects.select_related(
        "restaurant",
        "table"
    )
    serializer_class = RestaurantOrderSerializer
    model_name = "RestaurantOrder"
    lookup_field = "slug"

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

        # 1️⃣ Superuser → all orders
        if user.is_superuser:
            return qs

        role = getattr(user, "role", None)
        if not role:
            return qs.none()

        role_name = role.name.lower()

        # 2️⃣ Admin → own restaurant orders
        if role_name == "admin":
            return qs.filter(
                restaurant__owner=user
            )

        # 3️⃣ Staff → assigned restaurant orders
        if role_name == "staff":
            if hasattr(user, "staff_profile") and user.staff_profile.restaurant:
                return qs.filter(
                    restaurant=user.staff_profile.restaurant
                )
            return qs.none()

        # 4️⃣ Customer → only their orders
        # (assuming guest_phone maps to user.phone)
        if role_name == "customer":
            return qs.filter(
                guest_phone=user.phone
            )

        # 5️⃣ Others → no access
        return qs.none()


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

    
    @action(detail=False, methods=["get"], url_path="summary")
    def order_summary(self, request):
        user = request.user
        queryset = RestaurantOrder.objects.all()

        # -----------------------------------
        # ROLE-BASED DATA SCOPING
        # -----------------------------------

        # Superuser → all orders
        if user.is_superuser:
            pass

        else:
            role = getattr(user, "role", None)
            if not role:
                queryset = queryset.none()
            else:
                role_name = role.name.lower()

                # Admin → own restaurant
                if role_name == "admin":
                    queryset = queryset.filter(
                        restaurant__owner=user
                    )

                # Staff → assigned restaurant
                elif role_name == "staff":
                    if hasattr(user, "staff_profile") and user.staff_profile.restaurant:
                        queryset = queryset.filter(
                            restaurant=user.staff_profile.restaurant
                        )
                    else:
                        queryset = queryset.none()

                # Customer → their own orders
                elif role_name == "customer":
                    queryset = queryset.filter(
                        guest_phone=user.phone
                    )

                # Others → no access
                else:
                    queryset = queryset.none()

        # -----------------------------------
        # SUMMARY COUNTS
        # -----------------------------------

        total_orders = queryset.count()
        active_orders = queryset.filter(
            status__in=["pending", "preparing"]
        ).count()
        completed_orders = queryset.filter(
            status="completed"
        ).count()
        cancelled_orders = queryset.filter(
            status="cancelled"
        ).count()

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

    @action(detail=False, methods=["get"], url_path="dashboard-summary")
    def dashboard_summary(self, request):
        user = request.user
        restaurant_slug = request.query_params.get("restaurant")

        # Base QuerySets
        tables = Table.objects.select_related("restaurant")
        orders = RestaurantOrder.objects.select_related("restaurant")

        # -----------------------------------
        # ROLE-BASED DATA SCOPING
        # -----------------------------------

        if user.is_superuser:
            pass

        else:
            role = getattr(user, "role", None)
            if not role:
                return Response(
                    {"error": "Unauthorized access."},
                    status=status.HTTP_403_FORBIDDEN
                )

            role_name = role.name.lower()

            # Admin → own restaurant
            if role_name == "admin":
                tables = tables.filter(
                    restaurant__owner=user
                )
                orders = orders.filter(
                    restaurant__owner=user
                )

            # Staff → assigned restaurant
            elif role_name == "staff":
                if hasattr(user, "staff_profile") and user.staff_profile.restaurant:
                    restaurant = user.staff_profile.restaurant
                    tables = tables.filter(restaurant=restaurant)
                    orders = orders.filter(restaurant=restaurant)
                else:
                    return Response(
                        {"error": "Staff not linked to any restaurant."},
                        status=status.HTTP_403_FORBIDDEN
                    )

            # Customer → no dashboard
            elif role_name == "customer":
                return Response(
                    {"error": "Dashboard not available for customers."},
                    status=status.HTTP_403_FORBIDDEN
                )

            else:
                return Response(
                    {"error": "Unauthorized role."},
                    status=status.HTTP_403_FORBIDDEN
                )

        # -----------------------------------
        # OPTIONAL RESTAURANT FILTER (slug)
        # -----------------------------------
        if restaurant_slug:
            tables = tables.filter(
                restaurant__slug=restaurant_slug
            )
            orders = orders.filter(
                restaurant__slug=restaurant_slug
            )

        # -----------------------------------
        # DASHBOARD METRICS
        # -----------------------------------

        # 1️⃣ Available tables
        available_tables = tables.filter(
            status="available"
        ).count()

        # 2️⃣ Active orders (today)
        today = date.today()
        active_orders = orders.filter(
            order_time__date=today,
            status__in=["pending", "preparing", "served"]
        ).count()

        # 3️⃣ Today’s revenue
        todays_revenue = (
            orders.filter(
                order_time__date=today,
                status__in=["served", "completed"]
            ).aggregate(total=Sum("grand_total"))["total"] or 0
        )

        # 4️⃣ Average wait time (completed orders)
        avg_wait_minutes = 0
        avg_expr = ExpressionWrapper(
            F("completed_at") - F("order_time"),
            output_field=DurationField()
        )

        avg_wait_time = (
            orders.filter(
                status="completed",
                completed_at__isnull=False
            ).aggregate(avg=Avg(avg_expr))["avg"]
        )

        if avg_wait_time:
            avg_wait_minutes = round(
                avg_wait_time.total_seconds() / 60, 2
            )

        # -----------------------------------
        # RESPONSE
        # -----------------------------------
        return Response({
            "available_tables": available_tables,
            "active_orders": active_orders,
            "todays_revenue": float(todays_revenue),
            "avg_wait_time": f"{avg_wait_minutes} min",
        })


        
        
class TableReservationViewSet(ProtectedModelViewSet):
    """
    Manage Table Reservations.
    - Superuser: full access
    - Admin: reservations of their restaurant
    - Staff: reservations of assigned restaurant
    - Customer: only their own reservations
    """
    queryset = TableReservation.objects.select_related(
        "table",
        "table__restaurant"
    ).order_by("-created_at")

    serializer_class = TableReservationSerializer
    model_name = "TableReservation"  # required for RoleModelPermission mapping

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

        # 1️⃣ Superuser → all reservations
        if user.is_superuser:
            return qs

        role = getattr(user, "role", None)
        if not role:
            return qs.none()

        role_name = role.name.lower()

        # 2️⃣ Admin → own restaurant reservations
        if role_name == "admin":
            return qs.filter(
                table__restaurant__owner=user
            )

        # 3️⃣ Staff → assigned restaurant reservations
        if role_name == "staff":
            if hasattr(user, "staff_profile") and user.staff_profile.restaurant:
                return qs.filter(
                    table__restaurant=user.staff_profile.restaurant
                )
            return qs.none()

        # 4️⃣ Customer → only their reservations
        # (assuming reservation stores customer email)
        if role_name == "customer":
            return qs.filter(
                email=user.email
            )

        # 5️⃣ Others → no access
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