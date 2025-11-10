from rest_framework import serializers
from django.utils import timezone
from .models import (
    MenuCategory, MenuItem, Table, RestaurantOrder, OrderItem, TableReservation
)
from Hotel.models import Hotel
from django.core.validators import RegexValidator



class MenuCategorySerializer(serializers.ModelSerializer):
    hotel = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Hotel.objects.all()
    )

    class Meta:
        model = MenuCategory
        fields = '__all__'
        read_only_fields = ['slug']

    def validate_name(self, value):
        hotel_slug = self.initial_data.get('hotel')
        hotel = Hotel.objects.filter(slug=hotel_slug).first()
        if not hotel:
            raise serializers.ValidationError("Invalid hotel.")
        qs = MenuCategory.objects.filter(name=value, hotel=hotel)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("This category already exists for the hotel.")
        return value


class MenuItemSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=MenuCategory.objects.all()
    )

    class Meta:
        model = MenuItem
        fields = '__all__'
        read_only_fields = ['slug']

    def validate(self, data):
        name = data.get('name', self.instance.name if self.instance else None)
        category = data.get('category', self.instance.category if self.instance else None)
        qs = MenuItem.objects.filter(name=name, category=category)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("This item already exists in this category.")
        return data


class TableSerializer(serializers.ModelSerializer):
    hotel = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Hotel.objects.all()
    )

    class Meta:
        model = Table
        fields = '__all__'
        read_only_fields = ['slug']

    def validate_number(self, value):
        hotel_slug = self.initial_data.get('hotel')
        hotel = Hotel.objects.filter(slug=hotel_slug).first()
        if not hotel:
            raise serializers.ValidationError("Invalid hotel.")
        qs = Table.objects.filter(number=value, hotel=hotel)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("Table with this number already exists in this hotel.")
        return value

class OrderItemSerializer(serializers.ModelSerializer):
    menu_item = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=MenuItem.objects.all()
    )

    class Meta:
        model = OrderItem
        fields = ['slug', 'menu_item', 'quantity', 'price']
        read_only_fields = ['slug']

    def validate(self, data):
        """Ensure quantity and price are valid."""
        if data.get('quantity', 0) <= 0:
            raise serializers.ValidationError({"quantity": "Quantity must be greater than zero."})
        if data.get('price', 0) <= 0:
            raise serializers.ValidationError({"price": "Price must be greater than zero."})
        return data
    
class RestaurantOrderSerializer(serializers.ModelSerializer):
    table = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Table.objects.all(),
        allow_null=True,
        write_only=True
    )

    table_code = serializers.SerializerMethodField()
    hotel = serializers.SlugRelatedField(slug_field='slug', read_only=True)
    order_items = OrderItemSerializer(many=True, required=False)
    status_duration = serializers.SerializerMethodField()

    class Meta:
        model = RestaurantOrder
        fields = [
            'slug', 'order_code', 'table_code', 'hotel', 'table',
            'guest_name', 'guest_phone', 'remarks', 'status',
            'order_time', 'completed_at', 'order_items',
            'total_quantity', 'subtotal', 'sgst', 'cgst',
            'discount', 'discount_rule', 'grand_total',
            'status_duration'
        ]
        read_only_fields = [
            'slug', 'order_code', 'table_code', 'order_time',
            'completed_at', 'total_quantity', 'subtotal',
            'sgst', 'cgst', 'discount', 'discount_rule',
            'grand_total', 'status_duration'
        ]

    def get_table_code(self, obj):
        return obj.table.table_code if obj.table else None

    def get_status_duration(self, obj):
        if not obj.status_updated_at:
            return "0 min"
        diff = timezone.now() - obj.status_updated_at
        return f"{int(diff.total_seconds() // 60)} min"

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user

        # Assign hotel from logged-in user
        if hasattr(user, 'hotel_profile'):
            validated_data['hotel'] = user.hotel_profile.hotel
        elif hasattr(user, 'hotel'):
            validated_data['hotel'] = user.hotel
        else:
            raise serializers.ValidationError("User has no hotel assigned.")

        items_data = validated_data.pop('order_items', [])
        order = RestaurantOrder.objects.create(**validated_data)

        for item in items_data:
            OrderItem.objects.create(order=order, **item)

        return order

    def update(self, instance, validated_data):
        items_data = validated_data.pop('order_items', None)

        # Update fields including table
        for attr, val in validated_data.items():
            setattr(instance, attr, val)

        instance.save()

        if items_data is not None:
            instance.order_items.all().delete()
            for item in items_data:
                OrderItem.objects.create(order=instance, **item)

        return instance


class TableReservationSerializer(serializers.ModelSerializer):
    table = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Table.objects.all()
    )

    class Meta:
        model = TableReservation
        fields = '__all__'
        read_only_fields = ['slug', 'created_at', 'status']

    def validate(self, data):
        table = data.get('table')
        date = data.get('reservation_date')
        time = data.get('reservation_time')

        # Check for overlapping reservations
        existing = TableReservation.objects.filter(
            table=table,
            reservation_date=date,
            reservation_time=time,
            status__in=['pending', 'confirmed']
        )
        if existing.exists():
            raise serializers.ValidationError("This table is already reserved at the selected time.")

        return data
    
class RestaurantDashboardSerializer(serializers.Serializer):
    available_tables = serializers.IntegerField()
    active_orders = serializers.IntegerField()
    todays_revenue = serializers.FloatField()
    avg_wait_time = serializers.CharField()
