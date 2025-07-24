from rest_framework import serializers
from .models import LaundryService, LaundryOrder
from Hotel.models import Room
from django.contrib.auth import get_user_model

User = get_user_model()


class LaundryServiceSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(read_only=True)

    class Meta:
        model = LaundryService
        fields = '__all__'

    def validate_name(self, value):
        qs = LaundryService.objects.filter(name=value)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("Laundry service with this name already exists.")
        return value


class LaundryOrderSerializer(serializers.ModelSerializer):
    room = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Room.objects.all()
    )
    service = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=LaundryService.objects.all()
    )
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = LaundryOrder
        fields = '__all__'

    def validate(self, data):
        service = data.get('service')
        weight = data.get('weight')
        quantity = data.get('quantity')

        if service:
            if service.rate_type == 'per_kg' and not weight:
                raise serializers.ValidationError("Weight is required for per_kg rate type.")
            if service.rate_type == 'per_piece' and not quantity:
                raise serializers.ValidationError("Quantity is required for per_piece rate type.")

        return data
