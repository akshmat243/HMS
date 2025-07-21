from MBP.views import ProtectedModelViewSet
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


class MenuItemViewSet(ProtectedModelViewSet):
    queryset = MenuItem.objects.all()
    serializer_class = MenuItemSerializer
    model_name = 'MenuItem'


class TableViewSet(ProtectedModelViewSet):
    queryset = Table.objects.all()
    serializer_class = TableSerializer
    model_name = 'Table'


class RestaurantOrderViewSet(ProtectedModelViewSet):
    queryset = RestaurantOrder.objects.all()
    serializer_class = RestaurantOrderSerializer
    model_name = 'RestaurantOrder'


class OrderItemViewSet(ProtectedModelViewSet):
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializer
    model_name = 'OrderItem'
