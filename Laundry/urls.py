from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LaundryServiceViewSet, LaundryOrderViewSet

router = DefaultRouter()
router.register(r'laundry-services', LaundryServiceViewSet, basename='laundry-service')
router.register(r'laundry-orders', LaundryOrderViewSet, basename='laundry-order')

urlpatterns = [
    path('api/', include(router.urls)),
]
