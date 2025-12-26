from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    HotelViewSet,
    RoomCategoryViewSet,
    RoomViewSet,
    BookingViewSet,
    RoomServiceRequestViewSet,
    FeaturedListingView,
    DownloadAndroidAppView, 
    DownloadIOSAppView,
    PackageViewSet,
    # HomeDashboardViewSet
    # RoomMediaViewSet
)

router = DefaultRouter()
router.register('hotels', HotelViewSet)
router.register('room-categories', RoomCategoryViewSet)
router.register('rooms', RoomViewSet)
router.register('bookings', BookingViewSet)
router.register('room-service-requests', RoomServiceRequestViewSet)
router.register(r'packages', PackageViewSet, basename='packages')
# router.register(r'dashboard-unified', HomeDashboardViewSet, basename='home-dashboard')
# router.register(r'room-media', RoomMediaViewSet, basename='room-media')


urlpatterns = [
    path('api/', include(router.urls)),
    path('api/featured-list/', FeaturedListingView.as_view(), name='featured-list'),
    path('api/download/android/', DownloadAndroidAppView.as_view(), name='download-android'),
    path('api/download/ios/', DownloadIOSAppView.as_view(), name='download-ios'),
]