from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LeadViewSet, CustomerViewSet, InteractionViewSet

router = DefaultRouter()
router.register(r'leads', LeadViewSet, basename='lead')
router.register(r'customers', CustomerViewSet, basename='customer')
router.register(r'interactions', InteractionViewSet, basename='interaction')

urlpatterns = [
    path('api/', include(router.urls)),
]
