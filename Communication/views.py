from MBP.views import ProtectedModelViewSet
from .models import Notification, Message, Feedback
from .serializers import NotificationSerializer, MessageSerializer, FeedbackSerializer


class NotificationViewSet(ProtectedModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    model_name = 'Notification'
    lookup_field = 'slug'  # Using slug for secure URL handling


class MessageViewSet(ProtectedModelViewSet):
    queryset = Message.objects.all()
    serializer_class = MessageSerializer
    model_name = 'Message'
    lookup_field = 'slug'


class FeedbackViewSet(ProtectedModelViewSet):
    queryset = Feedback.objects.all()
    serializer_class = FeedbackSerializer
    model_name = 'Feedback'
    lookup_field = 'slug'
