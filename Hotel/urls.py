from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    HotelViewSet,
    RoomCategoryViewSet,
    RoomViewSet,
    BookingViewSet,
    RoomServiceRequestViewSet,
    # RoomMediaViewSet
)

router = DefaultRouter()
router.register('hotels', HotelViewSet)
router.register('room-categories', RoomCategoryViewSet)
router.register('rooms', RoomViewSet)
router.register('bookings', BookingViewSet)
router.register('room-service-requests', RoomServiceRequestViewSet)
# router.register(r'room-media', RoomMediaViewSet, basename='room-media')


urlpatterns = [
    path('api/', include(router.urls)),
]
