# events/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *

router = DefaultRouter()
router.register(r"venues", VenueViewSet, basename="venue")
router.register(r"events", EventViewSet, basename="event")
router.register(r"event-types", EventTypeViewSet, basename="event-type")
# router.register(r"event-bookings", BookingViewSet, basename="event-booking")

urlpatterns = [
    path("api/events/", include(router.urls)),
]
