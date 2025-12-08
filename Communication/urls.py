from rest_framework.routers import DefaultRouter
from .views import NotificationViewSet, MessageViewSet, FeedbackViewSet, NewsletterSubscribeView
from django.urls import path, include

router = DefaultRouter()
router.register(r'notifications', NotificationViewSet)
router.register(r'messages', MessageViewSet)
router.register(r'feedback', FeedbackViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
    path("api/subscribe/", NewsletterSubscribeView.as_view(), name="newsletter-subscribe")
]