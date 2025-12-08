from rest_framework import serializers
from .models import HotelReview, RestaurantReview, ServiceReview
from Hotel.models import Hotel
from Restaurant.models import MenuItem

class HotelReviewSerializer(serializers.ModelSerializer):
    hotel = serializers.SlugRelatedField(slug_field='slug', queryset=Hotel.objects.all())

    class Meta:
        model = HotelReview
        fields = '__all__'
        read_only_fields = ['id', 'slug', 'date', 'user']

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
        read_only_fields = ['id', 'slug', 'date', 'user']

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
        read_only_fields = ['id', 'slug', 'date', 'user']

    def validate(self, data):
        user = self.context['request'].user
        service_type = data.get('service_type')
        ref_id = data.get('reference_id')
        if self.instance is None and ServiceReview.objects.filter(user=user, service_type=service_type, reference_id=ref_id).exists():
            raise serializers.ValidationError("You have already submitted a review for this service.")
        return data

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


# Serializer for Public Display
class UnifiedReviewSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    type = serializers.CharField()  # 'hotel' ya 'restaurant' batane ke liye
    
    # User Details
    user_name = serializers.SerializerMethodField()
    
    # Review Details
    rating = serializers.IntegerField()
    comment = serializers.CharField()
    date = serializers.DateTimeField()
    
    # Card pe kya dikhana hai (Hotel Name ya Dish Name)
    entity_name = serializers.SerializerMethodField()
    entity_image = serializers.SerializerMethodField()

    def get_user_name(self, obj):
        if obj.user:
            return obj.user.get_full_name() or obj.user.username
        return "Guest User"

    def get_entity_name(self, obj):
        # Agar Hotel Review hai
        if hasattr(obj, 'hotel'):
            return obj.hotel.name
        # Agar Restaurant/Menu Review hai
        if hasattr(obj, 'menu_item') and obj.menu_item:
            return obj.menu_item.name
        return "Service"

    def get_entity_image(self, obj):
        request = self.context.get('request')
        image = None
        
        # Hotel Image
        if hasattr(obj, 'hotel') and obj.hotel.cover_image:
            image = obj.hotel.cover_image
        # Menu Item Image
        elif hasattr(obj, 'menu_item') and obj.menu_item and obj.menu_item.image:
            image = obj.menu_item.image
            
        if image and request:
            return request.build_absolute_uri(image.url)
        return None