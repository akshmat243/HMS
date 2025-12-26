from rest_framework import serializers
from .models import HotelReview, RestaurantReview, ServiceReview, StaffReview
from Hotel.models import Hotel, RoomServiceRequest
from Restaurant.models import MenuItem
from staff.models import Staff

class HotelReviewSerializer(serializers.ModelSerializer):
    hotel = serializers.SlugRelatedField(slug_field='slug', queryset=Hotel.objects.all())

    class Meta:
        model = HotelReview
        fields = '__all__'
        read_only_fields = ['id', 'slug', 'date', 'user', 'reply']

    def validate(self, data):
        user = self.context['request'].user
        hotel = data.get('hotel')
        if self.instance is None and HotelReview.objects.filter(user=user, hotel=hotel).exists():
            raise serializers.ValidationError("You have already reviewed this hotel.")
        return data

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class RestaurantReviewSerializer(serializers.ModelSerializer):
    menu_item = serializers.SlugRelatedField(slug_field='slug', queryset=MenuItem.objects.all())

    class Meta:
        model = RestaurantReview
        fields = '__all__'
        read_only_fields = ['id', 'slug', 'date', 'user', 'reply']

    def validate(self, data):
        user = self.context['request'].user
        item = data.get('menu_item')
        if self.instance is None and RestaurantReview.objects.filter(user=user, menu_item=item).exists():
            raise serializers.ValidationError("You have already reviewed this menu item.")
        return data

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class ServiceReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceReview
        fields = '__all__'
        read_only_fields = ['id', 'slug', 'date', 'user', 'reply']

    def validate(self, data):
        user = self.context['request'].user
        service_type = data.get('service_type')
        ref_id = data.get('reference_id')

        # VALIDATION LOGIC (Requested by User)
        # Check if the reference_id actually exists in RoomServiceRequest table
        # Applicable for: Laundry, Room Service, House Keeping, Spa
        if service_type in ['laundry', 'room_service', 'house_keeping', 'spa', 'House keeping']:
            if not RoomServiceRequest.objects.filter(id=ref_id).exists():
                 raise serializers.ValidationError({"reference_id": "Invalid Service Request ID. This request does not exist in the database."})

        # Check Duplicate
        if self.instance is None and ServiceReview.objects.filter(user=user, service_type=service_type, reference_id=ref_id).exists():
            raise serializers.ValidationError("You have already submitted a review for this service.")
        
        return data

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


# Serializer for Public Display
class UnifiedReviewSerializer(serializers.Serializer):
    comment = serializers.CharField()
    rating = serializers.IntegerField()
    user_name = serializers.SerializerMethodField()
    user_image = serializers.SerializerMethodField()

    def get_user_name(self, obj):
        if not obj.user:
            return "Guest User"

        # CASE 1: If user has full_name FIELD (string)
        if hasattr(obj.user, "full_name") and obj.user.full_name:
            return obj.user.full_name

        # CASE 2: If Django has full name function
        try:
            name = obj.user.get_full_name()
            if name:
                return name
        except:
            pass

        # CASE 3: fallback → username
        return obj.user.username

    def get_user_image(self, obj):
        request = self.context.get('request')

        try:
            if obj.user.profile.profile_picture:
                return request.build_absolute_uri(obj.user.profile.profile_picture.url)
        except:
            return None

        return None
    
#  Staff Review Serializer
class StaffReviewSerializer(serializers.ModelSerializer):
    # Input Staff ID (UUID) lega
    staff_member = serializers.SlugRelatedField(
        slug_field='slug', 
        queryset=Staff.objects.all()
    )

    class Meta:
        model = StaffReview
        fields = '__all__'
        read_only_fields = ['id', 'slug', 'date', 'user', 'reply']

    def validate(self, data):
        user = self.context['request'].user
        staff = data.get('staff_member')

        # Check for duplicate review by same user for same staff
        if self.instance is None and StaffReview.objects.filter(user=user, staff_member=staff).exists():
            raise serializers.ValidationError("You have already reviewed this staff member.")
        
        return data

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)