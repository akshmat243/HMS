from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    HotelReviewViewSet,
    RestaurantReviewViewSet,
    ServiceReviewViewSet,
)

router = DefaultRouter()
router.register(r'hotel-reviews', HotelReviewViewSet)
router.register(r'restaurant-reviews', RestaurantReviewViewSet)
router.register(r'service-reviews', ServiceReviewViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
]
