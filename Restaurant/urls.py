from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    MenuCategoryViewSet, MenuItemViewSet, TableViewSet,
    RestaurantOrderViewSet, OrderItemViewSet, RestaurantDashboardViewSet
)

router = DefaultRouter()
router.register(r'menu-categories', MenuCategoryViewSet)
router.register(r'menu-items', MenuItemViewSet)
router.register(r'tables', TableViewSet)
router.register(r'restaurant-orders', RestaurantOrderViewSet)
router.register(r'order-items', OrderItemViewSet)
router.register(r'dashboard', RestaurantDashboardViewSet, basename='restaurant-dashboard')

urlpatterns = [
    path('api/', include(router.urls)),
]
