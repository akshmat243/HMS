from rest_framework import serializers
from .models import (
    MenuCategory, MenuItem, Table, RestaurantOrder, OrderItem
)


class MenuCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuCategory
        fields = '__all__'

    def validate_name(self, value):
        hotel = self.initial_data.get('hotel')
        qs = MenuCategory.objects.filter(name=value, hotel_id=hotel)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("This category already exists for the hotel.")
        return value


class MenuItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItem
        fields = '__all__'

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
    class Meta:
        model = Table
        fields = '__all__'

    def validate_number(self, value):
        hotel = self.initial_data.get('hotel')
        qs = Table.objects.filter(number=value, hotel_id=hotel)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("Table with this number already exists in this hotel.")
        return value


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = '__all__'


class RestaurantOrderSerializer(serializers.ModelSerializer):
    order_items = OrderItemSerializer(many=True, required=False)

    class Meta:
        model = RestaurantOrder
        fields = '__all__'

    def create(self, validated_data):
        items_data = validated_data.pop('order_items', [])
        order = RestaurantOrder.objects.create(**validated_data)
        for item in items_data:
            OrderItem.objects.create(order=order, **item)
        return order

    def update(self, instance, validated_data):
        items_data = validated_data.pop('order_items', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if items_data is not None:
            instance.order_items.all().delete()
            for item in items_data:
                OrderItem.objects.create(order=instance, **item)

        return instance
