from MBP.views import ProtectedModelViewSet
from .models import Notification, Message, Feedback, Subscriber
from .serializers import NotificationSerializer, MessageSerializer, FeedbackSerializer, NewsletterSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from .utils import send_newsletter

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



class NewsletterSubscribeView(APIView):
    authentication_classes = []      # No login required
    permission_classes = []          # Anyone can use

    def post(self, request):
        email = request.data.get("email")

        if not email:
            return Response({"error": "Email is required."}, status=400)

        serializer = NewsletterSerializer(data=request.data)

        if serializer.is_valid():
            try:
                subscriber = serializer.save()

                # Send confirmation email
                send_newsletter(email)

                return Response(
                    {"message": "Subscribed successfully."},
                    status=status.HTTP_201_CREATED
                )

            except Exception:
                return Response(
                    {"error": "Email already subscribed."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        return Response(serializer.errors, status=400)

    def get(self, request):
        subs = Subscriber.objects.all()
        serializer = NewsletterSerializer(subs, many=True)
        return Response(serializer.data, status=200)