from MBP.views import ProtectedModelViewSet
from .models import HotelReview, RestaurantReview, ServiceReview
from .serializers import (
    HotelReviewSerializer,
    RestaurantReviewSerializer,
    ServiceReviewSerializer,
    UnifiedReviewSerializer
)
import random
from rest_framework.viewsets import ReadOnlyModelViewSet 
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

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


# ✅ NEW: Public API for Home Page Reviews
class PublicReviewViewSet(ReadOnlyModelViewSet):
    """
    Public ViewSet for fetching Reviews without Login.
    Use this for the Website/Home Page.
    """
    permission_classes = [AllowAny]  # ✅ No Token Required
    queryset = HotelReview.objects.none() # Dummy queryset required by DRF
    serializer_class = UnifiedReviewSerializer

    @action(detail=False, methods=['get'], url_path='top')
    def top_reviews(self, request):
        """
        API: /api/public-reviews/top/
        Returns mixed top 10 reviews (Hotel + Restaurant)
        """
        limit = 10
        
        # 1. Fetch Top Hotel Reviews (Rating 4+)
        hotel_reviews = list(HotelReview.objects.filter(rating__gte=4).select_related('user', 'hotel').order_by('-date')[:limit])
        
        # 2. Fetch Top Menu Reviews (Rating 4+)
        restro_reviews = list(RestaurantReview.objects.filter(rating__gte=4).select_related('user', 'menu_item').order_by('-date')[:limit])

        combined_list = []

        # 3. Add 'type' manually so serializer knows
        for r in hotel_reviews:
            r.type = 'hotel'
            combined_list.append(r)

        for r in restro_reviews:
            r.type = 'restaurant'
            combined_list.append(r)

        # 4. Shuffle & Limit
        random.shuffle(combined_list)
        final_list = combined_list[:limit]

        serializer = UnifiedReviewSerializer(final_list, many=True, context={'request': request})
        return Response(serializer.data)