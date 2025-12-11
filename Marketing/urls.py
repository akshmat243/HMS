from rest_framework.routers import DefaultRouter
from .views import CampaignViewSet, PromotionViewSet, MarketingOverviewAPIView, MarketingAnalyticsAPIView, ReviewMetricsAPIView
from django.urls import path, include


router = DefaultRouter()
router.register(r'campaigns', CampaignViewSet, basename='campaign')
router.register(r'promotions', PromotionViewSet, basename='promotion')


campaign_events = CampaignViewSet.as_view({'post': 'events'})
campaign_metrics = CampaignViewSet.as_view({'get': 'metrics'})

urlpatterns = [
    path('api/marketing/', include(router.urls)),
    path('api/marketing/analytics/', MarketingAnalyticsAPIView.as_view(), name='marketing-analytics'),
    path('api/marketing/overview/', MarketingOverviewAPIView.as_view(), name='marketing-overview'),
    path('api/marketing/campaigns/<slug:slug>/events/', campaign_events, name='campaign-events'),
    path('api/marketing/campaigns/<slug:slug>/metrics/', campaign_metrics, name='campaign-metrics'),
    path('api/marketing/reviews/', ReviewMetricsAPIView.as_view(), name='marekting-reviews'),
    

]