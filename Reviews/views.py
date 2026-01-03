from MBP.views import ProtectedModelViewSet
from .models import HotelReview, RestaurantReview, ServiceReview, StaffReview
from .serializers import (
    HotelReviewSerializer,
    RestaurantReviewSerializer,
    ServiceReviewSerializer,
    UnifiedReviewSerializer,
    StaffReviewSerializer
)
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Avg, Q  
from rest_framework.permissions import AllowAny
from rest_framework import status
from django.utils import timezone
from Hotel.models import Hotel,RoomServiceRequest
from django.utils.timesince import timesince
from staff.models import Staff

class HotelReviewViewSet(ProtectedModelViewSet):
    serializer_class = HotelReviewSerializer
    model_name = 'HotelReview'
    lookup_field = 'slug'
    
    def get_queryset(self):
        user = self.request.user
        qs = HotelReview.objects.all().select_related("hotel", "user")

        # 1️⃣ Superuser → all reviews
        if user.is_superuser:
            return qs

        role = getattr(user, "role", None)
        if not role:
            return HotelReview.objects.none()

        role_name = role.name.lower()

        # 2️⃣ Hotel Admin → only reviews of their hotel
        if role_name == "admin":
            return qs.filter(hotel__owner=user)

        # 3️⃣ Staff → reviews of assigned hotel
        if role_name == "staff":
            if hasattr(user, "staff_profile") and user.staff_profile.hotel:
                return qs.filter(hotel=user.staff_profile.hotel)
            return HotelReview.objects.none()

        # 4️⃣ Customer → can read reviews (optional: filter by hotel via query param)
        if role_name == "customer":
            hotel_slug = self.request.query_params.get("hotel")
            if hotel_slug:
                return qs.filter(hotel__slug=hotel_slug)
            return qs  # show all hotel reviews

        # 5️⃣ Vendor / Others → no access
        return HotelReview.objects.none()

    
    #  ACTION: ADMIN REPLY 
    @action(detail=True, methods=['patch'], url_path='submit-reply')
    def submit_reply(self, request, slug=None):
        """
        Endpoint for Admin to reply to a review.
        """
        review = self.get_object()
        user = request.user

        # Permission Check: Only Superuser or Admin allowed
        is_admin = user.is_superuser or (hasattr(user, 'role') and user.role.name.lower() == 'admin')
        
        if not is_admin:
             return Response({"error": "Only Admins can reply to reviews."}, status=status.HTTP_403_FORBIDDEN)

        reply_text = request.data.get('reply')
        if not reply_text:
            return Response({"error": "Reply text is required."}, status=status.HTTP_400_BAD_REQUEST)

        review.reply = reply_text
        review.save()

        return Response({
            "message": "Reply submitted successfully.",
            "reply": review.reply
        }, status=status.HTTP_200_OK)
    
    def _get_target_hotel(self, request):
        user = request.user
        target_hotel = None
        if user.is_superuser:
            hotel_id = request.query_params.get('hotel_id')
            if hotel_id:
                target_hotel = Hotel.objects.filter(id=hotel_id).first()
        else:
            if hasattr(user, 'role') and user.role.name.lower() == 'admin':
                target_hotel = getattr(user, 'hotel', None)
            elif hasattr(user, 'staff_profile') and user.staff_profile.hotel:
                target_hotel = user.staff_profile.hotel
        return target_hotel

    # ====================================================
    # PUBLIC REVIEWS (Formerly PublicReviewViewSet)
    # URL: /api/hotel-reviews/public_reviews/
    # ====================================================
    @action(detail=False, methods=['get'], permission_classes=[AllowAny], url_path='public-reviews')
    def public_reviews(self, request):
        """
        Returns top reviews (rating >= 4) without authentication.
        """
        limit = 3

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

        # Limit top 3
        final_list = combined[:limit]

        serializer = UnifiedReviewSerializer(
            final_list, many=True, context={'request': request}
        )

        return Response(serializer.data)


    # ====================================================
    # DASHBOARD STATS (Formerly ReviewDashboardStatsView)
    # URL: /api/hotel-reviews/dashboard_stats/
    # ====================================================
    @action(detail=False, methods=['get'], url_path='dashboard-stats')
    def dashboard_stats(self, request):
        user = request.user
        target_hotel = self._get_target_hotel(request)

        # Security Check for Non-Superusers without hotel
        if not user.is_superuser and not target_hotel:
             return Response(
                {"error": "Access Denied: No hotel associated with this user."}, 
                status=status.HTTP_403_FORBIDDEN
            )

        now = timezone.now()
        current_month = now.month
        current_year = now.year

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

        # ---  Hotel Reviews ---
        qs_hotel = HotelReview.objects.all()
        if target_hotel:
            qs_hotel = qs_hotel.filter(hotel=target_hotel)
        hotel_stats = calculate_stats(qs_hotel)

        # ---  Restaurant Reviews ---
        qs_rest = RestaurantReview.objects.all()
        if target_hotel:
            qs_rest = qs_rest.filter(menu_item__category__hotel=target_hotel)
        rest_stats = calculate_stats(qs_rest)

        # ---  Service Reviews ---
        qs_service = ServiceReview.objects.all()
        if target_hotel:
            valid_service_ids = RoomServiceRequest.objects.filter(
                room__hotel=target_hotel
            ).values_list('id', flat=True)
            qs_service = qs_service.filter(reference_id__in=valid_service_ids)
        service_stats = calculate_stats(qs_service)

        # --- Staff Reviews ---
        qs_staff = StaffReview.objects.all()
        if target_hotel:
            qs_staff = qs_staff.filter(staff_member__hotel=target_hotel)
        staff_stats = calculate_stats(qs_staff)

        # --- Combine ---
        total_reviews = hotel_stats['count'] + rest_stats['count'] + service_stats['count'] + staff_stats['count']
        total_this_month = hotel_stats['month'] + rest_stats['month'] + service_stats['month'] + staff_stats['month']
        total_replied = hotel_stats['replied'] + rest_stats['replied'] + service_stats['replied'] + staff_stats['replied']

        overall_rating = 0
        if total_reviews > 0:
            total_score = (
                (hotel_stats['avg'] * hotel_stats['count']) +
                (rest_stats['avg'] * rest_stats['count']) +
                (service_stats['avg'] * service_stats['count']) + 
                (staff_stats['avg'] * staff_stats['count'])
            )
            overall_rating = total_score / total_reviews

        response_rate = (total_replied / total_reviews * 100) if total_reviews > 0 else 0

        return Response({
            "scope": target_hotel.name if target_hotel else "Global Stats",
            "overall_rating": round(overall_rating, 1),
            "total_reviews": total_reviews,
            "this_month": total_this_month,
            "response_rate": f"{int(response_rate)}%"
        }, status=status.HTTP_200_OK)

    # ====================================================
    #  RATING BREAKDOWN 
    # URL: /api/hotel-reviews/rating_breakdown/
    # ====================================================
    @action(detail=False, methods=['get'], url_path='rating-breakdown')
    def rating_breakdown(self, request):
        user = request.user
        target_hotel = self._get_target_hotel(request)

        # Security Check
        if not user.is_superuser and not target_hotel:
            return Response({"error": "No hotel access"}, status=403)

        def get_category_stats(name, queryset):
            stats = queryset.aggregate(avg=Avg('rating'), count=Count('id'))
            return {
                "category": name,
                "rating": round(stats['avg'], 1) if stats['avg'] else 0.0,
                "reviews": stats['count'] or 0
            }

        data = []

        # 1. Hotel Service
        qs_hotel = HotelReview.objects.all()
        if target_hotel:
            qs_hotel = qs_hotel.filter(hotel=target_hotel)
        data.append(get_category_stats("Hotel Service", qs_hotel))

        # 2. Restaurant
        qs_rest = RestaurantReview.objects.all()
        if target_hotel:
            qs_rest = qs_rest.filter(menu_item__category__hotel=target_hotel)
        data.append(get_category_stats("Restaurant", qs_rest))

        qs_services_base = ServiceReview.objects.all()
        if target_hotel:
            valid_ids = RoomServiceRequest.objects.filter(room__hotel=target_hotel).values_list('id', flat=True)
            qs_services_base = qs_services_base.filter(reference_id__in=valid_ids)

        # 3. Housekeeping (Specific)
        # Note: Check EXACT string stored in DB ('House keeping' or 'house_keeping')
        qs_house = qs_services_base.filter(service_type__iexact='house keeping') 
        data.append(get_category_stats("Housekeeping", qs_house))

        # 4. Other Room Services (Excluding Housekeeping)
        qs_others = qs_services_base.exclude(service_type__iexact='house keeping')
        data.append(get_category_stats("Room & Services", qs_others))

        # 5. Staff (New Model)
        qs_staff = StaffReview.objects.all()
        if target_hotel:
            qs_staff = qs_staff.filter(staff_member__hotel=target_hotel)
        data.append(get_category_stats("Staff", qs_staff))

        return Response(data, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'], url_path='recent-reviews')
    def recent_reviews(self, request):
        """
        Fetches the most recent reviews across Hotels, Restaurants, Services, AND Staff.
        """
        target_hotel = self._get_target_hotel(request)
        user = request.user

        # Security Check
        if not user.is_superuser and not target_hotel:
            return Response({"error": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        # Limit per category (Optimization)
        limit = 6
        
        # 1. Fetch Top Reviews from each category
        
        # A. Hotel Reviews
        qs_hotel = HotelReview.objects.select_related('user').order_by('-date')
        if target_hotel:
            qs_hotel = qs_hotel.filter(hotel=target_hotel)
        list_hotel = list(qs_hotel[:limit])

        # B. Restaurant Reviews
        qs_rest = RestaurantReview.objects.select_related('user', 'menu_item').order_by('-date')
        if target_hotel:
            qs_rest = qs_rest.filter(menu_item__category__hotel=target_hotel)
        list_rest = list(qs_rest[:limit])

        # C. Service Reviews (Services & Housekeeping)
        qs_service = ServiceReview.objects.select_related('user').order_by('-date')
        if target_hotel:
            valid_ids = RoomServiceRequest.objects.filter(room__hotel=target_hotel).values_list('id', flat=True)
            qs_service = qs_service.filter(reference_id__in=valid_ids)
        list_service = list(qs_service[:limit])

        # D. Staff Reviews 
        qs_staff = StaffReview.objects.select_related('user', 'staff_member__user').order_by('-date')
        if target_hotel:
            qs_staff = qs_staff.filter(staff_member__hotel=target_hotel)
        list_staff = list(qs_staff[:limit])


        # 2. Helper to Format Data
        def format_review(obj, review_type):
            # User Data Extraction (Reviewer)
            user_name = "Guest"
            user_img = None
            if obj.user:
                if hasattr(obj.user, "full_name") and obj.user.full_name:
                    user_name = obj.user.full_name
                else:
                    user_name = obj.user.email.split('@')[0]
                
                # Try getting image
                try:
                    if hasattr(obj.user, 'profile') and obj.user.profile.profile_picture:
                        user_img = request.build_absolute_uri(obj.user.profile.profile_picture.url)
                except:
                    pass

            # Target Name Logic (Kis cheez ka review h?)
            target_name = ""
            display_category = review_type # For UI Icons

            if review_type == "Hotel":
                target_name = obj.hotel.name
            
            elif review_type == "Dining":
                target_name = obj.menu_item.name if obj.menu_item else "Unknown Item"
            
            elif review_type == "Service":
                # Check specific service type for better UI labels
                if obj.service_type.lower() == 'house keeping':
                    target_name = "Housekeeping"
                    display_category = "Housekeeping" # Alag icon dikha sakte ho
                else:
                    target_name = obj.get_service_type_display() # "Room Service", "Laundry"

            elif review_type == "Staff":
                # Staff ka naam dikhao
                if obj.staff_member and obj.staff_member.user:
                    target_name = obj.staff_member.user.full_name
                else:
                    target_name = "Staff Member"

            return {
                "id": str(obj.id),
                "user_name": user_name,
                "user_image": user_img,
                "category": display_category,     # UI: "Staff", "Dining", "Hotel"
                "target": target_name,            # UI: "Ramesh (Waiter)", "Pasta", "Grand Hotel"
                "rating": obj.rating,
                "comment": obj.comment,
                "time_ago": timesince(obj.date, timezone.now()) + " ago",
                "timestamp": obj.date             # Sorting ke liye
            }

        # 3. Combine All Lists
        combined_list = []
        for r in list_hotel: combined_list.append(format_review(r, "Hotel"))
        for r in list_rest: combined_list.append(format_review(r, "Dining"))
        for r in list_service: combined_list.append(format_review(r, "Service"))
        for r in list_staff: combined_list.append(format_review(r, "Staff")) # ✅ Added here

        # 4. Sort by Date Descending (Latest first)
        combined_list.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # 5. Take Top 6 (or whatever limit you want on dashboard)
        final_data = combined_list[:6]

        # Cleanup timestamp before sending JSON
        for item in final_data:
            del item['timestamp']

        return Response(final_data, status=status.HTTP_200_OK)

class RestaurantReviewViewSet(ProtectedModelViewSet):
    serializer_class = RestaurantReviewSerializer
    model_name = 'RestaurantReview'
    lookup_field = 'slug'

    def get_queryset(self):
        user = self.request.user
        qs = RestaurantReview.objects.all().select_related(
            "menu_item", "user", "menu_item__category"
        )

        # 1️⃣ Superuser → all reviews
        if user.is_superuser:
            return qs

        role = getattr(user, "role", None)
        if not role:
            return RestaurantReview.objects.none()

        role_name = role.name.lower()

        # 2️⃣ Restaurant Admin → reviews of their own restaurant
        if role_name == "admin":
            # Restaurant admin (owns a restaurant)
            if hasattr(user, "restaurant"):
                return qs.filter(
                    menu_item__category__restaurant=user.restaurant
                )

            # Hotel admin → reviews of restaurant(s) under their hotel
            return qs.filter(
                menu_item__category__restaurant__hotel__owner=user
            )

        # 3️⃣ Staff → reviews of restaurant linked to their hotel
        if role_name == "staff":
            if hasattr(user, "staff_profile") and user.staff_profile.hotel:
                return qs.filter(
                    menu_item__category__restaurant__hotel=user.staff_profile.hotel
                )
            return RestaurantReview.objects.none()

        # 4️⃣ Customer → read-only access
        if role_name == "customer":
            restaurant_slug = self.request.query_params.get("restaurant")
            if restaurant_slug:
                return qs.filter(
                    menu_item__category__restaurant__slug=restaurant_slug
                )
            return qs

        # 5️⃣ Vendor / Others → no access
        return RestaurantReview.objects.none()

    
    #  ACTION: ADMIN REPLY
    @action(detail=True, methods=['patch'], url_path='submit-reply')
    def submit_reply(self, request, slug=None):
        review = self.get_object()
        user = request.user
        is_admin = user.is_superuser or (hasattr(user, 'role') and user.role.name.lower() == 'admin')
        
        if not is_admin:
             return Response({"error": "Only Admins can reply to reviews."}, status=status.HTTP_403_FORBIDDEN)

        reply_text = request.data.get('reply')
        if not reply_text:
            return Response({"error": "Reply text is required."}, status=status.HTTP_400_BAD_REQUEST)

        review.reply = reply_text
        review.save()
        return Response({"message": "Reply submitted successfully.", "reply": review.reply}, status=status.HTTP_200_OK)

class ServiceReviewViewSet(ProtectedModelViewSet):
    serializer_class = ServiceReviewSerializer
    model_name = 'ServiceReview'
    lookup_field = 'slug'

    def get_queryset(self):
        user = self.request.user
        qs = ServiceReview.objects.all()

        # 1️⃣ Superuser → all reviews
        if user.is_superuser:
            return qs

        role = getattr(user, "role", None)
        if not role:
            return ServiceReview.objects.none()

        role_name = role.name.lower()

        # 2️⃣ Hotel Admin → reviews for their hotel's service requests
        if role_name == "admin":
            valid_ids = RoomServiceRequest.objects.filter(
                room__hotel__owner=user
            ).values_list("id", flat=True)

            return qs.filter(reference_id__in=valid_ids)

        # 3️⃣ Staff → reviews for assigned hotel
        if role_name == "staff":
            if hasattr(user, "staff_profile") and user.staff_profile.hotel:
                valid_ids = RoomServiceRequest.objects.filter(
                    room__hotel=user.staff_profile.hotel
                ).values_list("id", flat=True)

                return qs.filter(reference_id__in=valid_ids)

            return ServiceReview.objects.none()

        # 4️⃣ Customer → only their own reviews
        if role_name == "customer":
            return qs.filter(user=user)

        # 5️⃣ Vendor / Others → no access
        return ServiceReview.objects.none()


    #  ACTION: ADMIN REPLY 
    @action(detail=True, methods=['patch'], url_path='submit-reply')
    def submit_reply(self, request, slug=None):
        review = self.get_object()
        user = request.user
        is_admin = user.is_superuser or (hasattr(user, 'role') and user.role.name.lower() == 'admin')
        
        if not is_admin:
             return Response({"error": "Only Admins can reply to reviews."}, status=status.HTTP_403_FORBIDDEN)

        reply_text = request.data.get('reply')
        if not reply_text:
            return Response({"error": "Reply text is required."}, status=status.HTTP_400_BAD_REQUEST)

        review.reply = reply_text
        review.save()
        return Response({"message": "Reply submitted successfully.", "reply": review.reply}, status=status.HTTP_200_OK)

# StaffReview ViewSet 
class StaffReviewViewSet(ProtectedModelViewSet):
    """
    ViewSet for Managing Staff Reviews.
    Isolation Logic:
    - Superuser: All reviews
    - Admin: Reviews of staff in their hotel
    - Staff: Reviews about themselves (optional)
    """
    serializer_class = StaffReviewSerializer
    model_name = 'StaffReview'  # Ensure permissions are set for this name
    lookup_field = 'slug'

    def get_queryset(self):
        user = self.request.user
        qs = StaffReview.objects.all().select_related(
            'staff_member', 'user'
        )

        # 1️⃣ Superuser → all reviews
        if user.is_superuser:
            return qs

        role = getattr(user, "role", None)
        if not role:
            return StaffReview.objects.none()

        role_name = role.name.lower()

        # 2️⃣ Hotel Admin → reviews of staff in their hotel
        if role_name == "admin":
            return qs.filter(
                staff_member__hotel__owner=user
            )

        # 3️⃣ Staff → only reviews about themselves
        if role_name == "staff":
            if hasattr(user, "staff_profile"):
                return qs.filter(
                    staff_member=user.staff_profile
                )
            return StaffReview.objects.none()

        # 4️⃣ Others → no access
        return StaffReview.objects.none()

    
    # --- ACTION: ADMIN REPLY (Added Here) ---
    @action(detail=True, methods=['patch'], url_path='submit-reply')
    def submit_reply(self, request, slug=None):
        review = self.get_object()
        user = request.user
        is_admin = user.is_superuser or (hasattr(user, 'role') and user.role.name.lower() == 'admin')
        
        if not is_admin:
             return Response({"error": "Only Admins can reply to reviews."}, status=status.HTTP_403_FORBIDDEN)

        reply_text = request.data.get('reply')
        if not reply_text:
            return Response({"error": "Reply text is required."}, status=status.HTTP_400_BAD_REQUEST)

        review.reply = reply_text
        review.save()
        return Response({"message": "Reply submitted successfully.", "reply": review.reply}, status=status.HTTP_200_OK)