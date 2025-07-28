from MBP.views import ProtectedModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import (
    MenuCategory, MenuItem, Table, RestaurantOrder, OrderItem
)
from .serializers import (
    MenuCategorySerializer, MenuItemSerializer, TableSerializer,
    RestaurantOrderSerializer, OrderItemSerializer
)


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
    queryset = RestaurantOrder.objects.all()
    serializer_class = RestaurantOrderSerializer
    model_name = 'RestaurantOrder'
    lookup_field = 'slug'
    
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
