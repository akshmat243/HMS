from MBP.views import ProtectedModelViewSet
from .models import HotelReview, RestaurantReview, ServiceReview
from .serializers import (
    HotelReviewSerializer,
    RestaurantReviewSerializer,
    ServiceReviewSerializer,
)

class HotelReviewViewSet(ProtectedModelViewSet):
    queryset = HotelReview.objects.all()
    serializer_class = HotelReviewSerializer
    model_name = 'HotelReview'
    lookup_field = 'slug'


class RestaurantReviewViewSet(ProtectedModelViewSet):
    queryset = RestaurantReview.objects.all()
    serializer_class = RestaurantReviewSerializer
    model_name = 'RestaurantReview'
    lookup_field = 'slug'


class ServiceReviewViewSet(ProtectedModelViewSet):
    queryset = ServiceReview.objects.all()
    serializer_class = ServiceReviewSerializer
    model_name = 'ServiceReview'
    lookup_field = 'slug'
