from rest_framework.routers import DefaultRouter
from .views import CampaignViewSet, PromotionViewSet
from django.urls import path, include

router = DefaultRouter()
router.register(r'campaigns', CampaignViewSet)
router.register(r'promotions', PromotionViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
]