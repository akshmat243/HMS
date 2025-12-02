from rest_framework import routers
from django.urls import path, include
from .views import *

router = routers.DefaultRouter()
router.register(r'service-categories', ServiceCategoryViewSet, basename='service-categories')
router.register(r'available-services', GuestServiceViewSet, basename='guest-services')
router.register(r'service-requests', ServiceRequestViewSet, basename='service-request')



urlpatterns = [
    path('api/guest-services/', include(router.urls)),

    # Dashboard summary API
    path('api/guest-services/summary/', ServiceSummaryAPIView.as_view(), name='service-summary'),

    # analytics API 
    path('api/guest-services/analytics/', ServiceAnalyticsAPIView.as_view(), name='service-analytics'),

    # Guest profiles API
    path('api/guest-services/guest-profiles/', GuestProfileListAPIView.as_view(), name="guest-profiles"),
]
