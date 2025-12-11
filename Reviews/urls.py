from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    HotelReviewViewSet,
    RestaurantReviewViewSet,
    ServiceReviewViewSet,
    PublicReviewViewSet,
    ReviewDashboardStatsView,
    RatingBreakdownView
)

router = DefaultRouter()
router.register(r'hotel-reviews', HotelReviewViewSet, basename='hotel-reviews')
router.register(r'restaurant-reviews', RestaurantReviewViewSet, basename='restaurant-reviews')
router.register(r'service-reviews', ServiceReviewViewSet, basename="service-reviews")
router.register(r'public-reviews', PublicReviewViewSet, basename='public-reviews')

urlpatterns = [
    path('api/', include(router.urls)),
    path('api/review-dashboard/', ReviewDashboardStatsView.as_view(), name='review-stats'),
    path('api/rating-breakdown/', RatingBreakdownView.as_view(), name='rating-breakdown'),
]
