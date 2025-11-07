from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PageViewSet, FAQViewSet, BannerViewSet, MetaTagViewSet, SidebarAppViewSet

router = DefaultRouter()
router.register(r'pages', PageViewSet, basename='page')
router.register(r'faqs', FAQViewSet, basename='faq')
router.register(r'banners', BannerViewSet, basename='banner')
router.register(r'meta-tags', MetaTagViewSet, basename='metatag')
router.register(r'sidebar-apps', SidebarAppViewSet, basename='sidebarapp')

urlpatterns = [
    path('api/', include(router.urls)),
]
