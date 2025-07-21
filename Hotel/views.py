from MBP.views import ProtectedModelViewSet
from .models import Hotel, RoomCategory, Room, Booking, RoomServiceRequest
from .serializers import (
    HotelSerializer,
    RoomCategorySerializer,
    RoomSerializer,
    BookingSerializer,
    RoomServiceRequestSerializer,
)


class HotelViewSet(ProtectedModelViewSet):
    queryset = Hotel.objects.all()
    serializer_class = HotelSerializer
    model_name = 'Hotel'


class RoomCategoryViewSet(ProtectedModelViewSet):
    queryset = RoomCategory.objects.all()
    serializer_class = RoomCategorySerializer
    model_name = 'RoomCategory'


class RoomViewSet(ProtectedModelViewSet):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    model_name = 'Room'


class BookingViewSet(ProtectedModelViewSet):
    queryset = Booking.objects.all()
    serializer_class = BookingSerializer
    model_name = 'Booking'


class RoomServiceRequestViewSet(ProtectedModelViewSet):
    queryset = RoomServiceRequest.objects.all()
    serializer_class = RoomServiceRequestSerializer
    model_name = 'RoomServiceRequest'

