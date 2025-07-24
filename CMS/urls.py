from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PageViewSet, FAQViewSet, BannerViewSet, MetaTagViewSet

router = DefaultRouter()
router.register(r'pages', PageViewSet, basename='page')
router.register(r'faqs', FAQViewSet, basename='faq')
router.register(r'banners', BannerViewSet, basename='banner')
router.register(r'meta-tags', MetaTagViewSet, basename='metatag')

urlpatterns = [
    path('api/', include(router.urls)),
]
