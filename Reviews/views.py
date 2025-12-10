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
from django.db.models import Count, Avg, Q  
from rest_framework.permissions import AllowAny,IsAuthenticated
from rest_framework import status
from django.utils import timezone
from rest_framework.views import APIView
from Hotel.models import Hotel,RoomServiceRequest

class HotelReviewViewSet(ProtectedModelViewSet):
    serializer_class = HotelReviewSerializer
    model_name = 'HotelReview'
    lookup_field = 'slug'
    def get_queryset(self):
        user = self.request.user

        # SUPERUSER → full access
        if user.is_superuser:
            return HotelReview.objects.all().select_related("hotel", "user")

        # HOTEL ADMIN
        if hasattr(user, "hotel") and user.hotel:
            return HotelReview.objects.filter(hotel=user.hotel).select_related("hotel", "user")

        # STAFF → via staff_profile
        if hasattr(user, "staff_profile") and user.staff_profile.hotel:
            return HotelReview.objects.filter(hotel=user.staff_profile.hotel).select_related("hotel", "user")

        # DEFAULT → No Access
        return HotelReview.objects.none()


class RestaurantReviewViewSet(ProtectedModelViewSet):
    serializer_class = RestaurantReviewSerializer
    model_name = 'RestaurantReview'
    lookup_field = 'slug'

    def get_queryset(self):
        user = self.request.user

        if user.is_superuser:
            return RestaurantReview.objects.all().select_related("menu_item", "user")

        # HOTEL ADMIN
        if hasattr(user, "hotel") and user.hotel:
            return RestaurantReview.objects.filter(
                menu_item__category__hotel=user.hotel
            ).select_related("menu_item", "user")

        # STAFF
        if hasattr(user, "staff_profile") and user.staff_profile.hotel:
            return RestaurantReview.objects.filter(
                menu_item__category__hotel=user.staff_profile.hotel
            ).select_related("menu_item", "user")

        return RestaurantReview.objects.none()

class ServiceReviewViewSet(ProtectedModelViewSet):
    serializer_class = ServiceReviewSerializer
    model_name = 'ServiceReview'
    lookup_field = 'slug'

    def get_queryset(self):
        user = self.request.user

        if user.is_superuser:
            return ServiceReview.objects.all()

        # HOTEL ADMIN
        if hasattr(user, "hotel") and user.hotel:
            valid_ids = RoomServiceRequest.objects.filter(
                room__hotel=user.hotel
            ).values_list("id", flat=True)

            return ServiceReview.objects.filter(reference_id__in=valid_ids)

        # STAFF
        if hasattr(user, "staff_profile") and user.staff_profile.hotel:
            valid_ids = RoomServiceRequest.objects.filter(
                room__hotel=user.staff_profile.hotel
            ).values_list("id", flat=True)

            return ServiceReview.objects.filter(reference_id__in=valid_ids)

        return ServiceReview.objects.none()


class PublicReviewViewSet(ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    queryset = HotelReview.objects.none()
    serializer_class = UnifiedReviewSerializer

    def list(self, request):
        """
        /api/public-reviews/
        Returns top reviews (rating >= 4) without any extra path.
        """

        limit = 10

        # Fetch hotel reviews rating 4+
        hotel_reviews = list(
            HotelReview.objects.filter(rating__gte=4)
            .select_related('user')
            .order_by('-date')
        )

        # Fetch restaurant reviews rating 4+
        restro_reviews = list(
            RestaurantReview.objects.filter(rating__gte=4)
            .select_related('user')
            .order_by('-date')
        )

        # Combine & sort by date
        combined = hotel_reviews + restro_reviews
        combined = sorted(combined, key=lambda x: x.date, reverse=True)

        # Limit top 10
        final_list = combined[:limit]

        serializer = UnifiedReviewSerializer(
            final_list, many=True, context={'request': request}
        )

        return Response(serializer.data)
    

# class ReviewDashboardStatsView(APIView):


class ReviewDashboardStatsView(APIView):
    """
    API for the Review Stats Cards:
    1. Overall Rating
    2. Total Reviews
    3. This Month Reviews
    4. Response Rate
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        target_hotel = None

        # ====================================================
        # STEP 1: ISOLATION LOGIC (Define Scope)
        # ====================================================
        if user.is_superuser:
            # Superuser can filter by hotel_id, otherwise Global
            hotel_id = request.query_params.get('hotel_id')
            if hotel_id:
                target_hotel = Hotel.objects.filter(id=hotel_id).first()
        else:
            # Regular Admin/Staff Logic
            if hasattr(user, 'role') and user.role.name.lower() == 'admin':
                target_hotel = getattr(user, 'hotel', None)
            elif hasattr(user, 'staff_profile') and user.staff_profile.hotel:
                target_hotel = user.staff_profile.hotel
            
            # Security Check
            if not target_hotel:
                return Response(
                    {"error": "Access Denied: No hotel associated with this user."}, 
                    status=status.HTTP_403_FORBIDDEN
                )

        # ====================================================
        # STEP 2: DATE FILTERS
        # ====================================================
        now = timezone.now()
        current_month = now.month
        current_year = now.year

        # ====================================================
        # STEP 3: HELPER FUNCTION (Aggregation Logic)
        # ====================================================
        def calculate_stats(queryset):
            data = queryset.aggregate(
                avg_rating=Avg('rating'),
                total_count=Count('id'),
                this_month_count=Count('id', filter=Q(date__year=current_year, date__month=current_month)),
                replied_count=Count('id', filter=~Q(reply='') & ~Q(reply=None))
            )
            return {
                'avg': data['avg_rating'] or 0,
                'count': data['total_count'] or 0,
                'month': data['this_month_count'] or 0,
                'replied': data['replied_count'] or 0
            }

        # ====================================================
        # STEP 4: FETCH DATA (With Specific Paths)
        # ====================================================
        
        # --- A. Hotel Reviews ---
        # Path: Direct 'hotel' field
        qs_hotel = HotelReview.objects.all()
        if target_hotel:
            qs_hotel = qs_hotel.filter(hotel=target_hotel)
        
        hotel_stats = calculate_stats(qs_hotel)

        # --- B. Restaurant Reviews ---
        # Path: menu_item -> category -> hotel
        qs_rest = RestaurantReview.objects.all()
        if target_hotel:
            qs_rest = qs_rest.filter(menu_item__category__hotel=target_hotel)
        
        rest_stats = calculate_stats(qs_rest)

        # --- C. Service Reviews (The Tricky One) ---
        # Path: ServiceReview ke pass direct relation nahi hai, sirf 'reference_id' hai.
        # Logic: Pehle Hotel ke saare 'RoomServiceRequest' ids nikalo, fir match karo.
        qs_service = ServiceReview.objects.all()
        
        if target_hotel:
            # 1. Get all RoomServiceRequest IDs for this hotel
            valid_service_ids = RoomServiceRequest.objects.filter(
                room__hotel=target_hotel
            ).values_list('id', flat=True)
            
            # 2. Filter ServiceReviews jo in IDs se match karein
            qs_service = qs_service.filter(reference_id__in=valid_service_ids)

        service_stats = calculate_stats(qs_service)

        # ====================================================
        # STEP 5: COMBINE & CALCULATE TOTALS
        # ====================================================
        
        total_reviews = hotel_stats['count'] + rest_stats['count'] + service_stats['count']
        total_this_month = hotel_stats['month'] + rest_stats['month'] + service_stats['month']
        total_replied = hotel_stats['replied'] + rest_stats['replied'] + service_stats['replied']

        # Weighted Average Calculation
        overall_rating = 0
        if total_reviews > 0:
            total_score = (
                (hotel_stats['avg'] * hotel_stats['count']) +
                (rest_stats['avg'] * rest_stats['count']) +
                (service_stats['avg'] * service_stats['count'])
            )
            overall_rating = total_score / total_reviews

        # Response Rate Calculation
        response_rate = 0
        if total_reviews > 0:
            response_rate = (total_replied / total_reviews) * 100

        # ====================================================
        # STEP 6: RETURN RESPONSE
        # ====================================================
        return Response({
            "scope": target_hotel.name if target_hotel else "Global Stats",
            "overall_rating": round(overall_rating, 1),
            "total_reviews": total_reviews,
            "this_month": total_this_month,
            "response_rate": f"{int(response_rate)}%"
        }, status=status.HTTP_200_OK)
    

class RatingBreakdownView(APIView):
    """
    API for Rating Breakdown Cards (Hotel, Restaurant, Services)
    Returns list of categories with rating and review count.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        target_hotel = None

        # ====================================================
        # 1. ISOLATION LOGIC (Same as before)
        # ====================================================
        if user.is_superuser:
            hotel_id = request.query_params.get('hotel_id')
            if hotel_id:
                target_hotel = Hotel.objects.filter(id=hotel_id).first()
        else:
            if hasattr(user, 'role') and user.role.name.lower() == 'admin':
                target_hotel = getattr(user, 'hotel', None)
            elif hasattr(user, 'staff_profile') and user.staff_profile.hotel:
                target_hotel = user.staff_profile.hotel
            
            if not target_hotel:
                return Response({"error": "No hotel access"}, status=403)

        # ====================================================
        # 2. HELPER TO CALCULATE STATS
        # ====================================================
        def get_category_stats(name, queryset):
            stats = queryset.aggregate(avg=Avg('rating'), count=Count('id'))
            return {
                "category": name,
                "rating": round(stats['avg'], 1) if stats['avg'] else 0.0,
                "reviews": stats['count'] or 0
            }

        data = []

        # ====================================================
        # 3. CARD 1: HOTEL SERVICE
        # ====================================================
        qs_hotel = HotelReview.objects.all()
        if target_hotel:
            qs_hotel = qs_hotel.filter(hotel=target_hotel)
        
        data.append(get_category_stats("Hotel Service", qs_hotel))

        # ====================================================
        # 4. CARD 2: RESTAURANT
        # ====================================================
        qs_rest = RestaurantReview.objects.all()
        if target_hotel:
            # Path: menu_item -> category -> hotel
            qs_rest = qs_rest.filter(menu_item__category__hotel=target_hotel)
        
        data.append(get_category_stats("Restaurant", qs_rest))

        # ====================================================
        # 5. CARD 3: ROOM SERVICES (Laundry, Spa, etc.)
        # ====================================================
        # Humare paas ServiceReview model hai, to iska card bana dete hain
        qs_service = ServiceReview.objects.all()
        if target_hotel:
            # Logic: Find IDs from RoomServiceRequest linked to this hotel
            valid_ids = RoomServiceRequest.objects.filter(
                room__hotel=target_hotel
            ).values_list('id', flat=True)
            qs_service = qs_service.filter(reference_id__in=valid_ids)

        data.append(get_category_stats("Room & Services", qs_service))

        return Response(data, status=status.HTTP_200_OK)