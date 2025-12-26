from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import NotificationViewSet, MessageViewSet, FeedbackViewSet

# Create the router and register our viewsets with it.
router = DefaultRouter()
router.register(r'notifications', NotificationViewSet)
router.register(r'messages', MessageViewSet)
router.register(r'feedback', FeedbackViewSet)

# The router URLs are now automatically determined.
urlpatterns = [
    path('api/', include(router.urls)),
]