from rest_framework import serializers
from .models import Supplier, InventoryItem, InventoryCategory, PurchaseOrder, PurchaseOrderItem
from datetime import date


# Supplier
class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = '__all__'

    def validate_name(self, value):
        if len(value.strip()) < 3:
            raise serializers.ValidationError("Supplier name must be at least 3 characters long.")
        return value

    def validate_email(self, value):
        if value and not value.endswith(".com"):
            raise serializers.ValidationError("Supplier email must be a valid domain (e.g. example@gmail.com).")
        return value

    def validate_rating(self, value):
        if not (0 <= value <= 5):
            raise serializers.ValidationError("Rating must be between 0 and 5.")
        return value


# Category
class InventoryCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryCategory
        fields = '__all__'

    def validate_name(self, value):
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Category name must have at least 2 letters.")
        return value


# Item
class InventoryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryItem
        fields = '__all__'
        read_only_fields = ['total_value', 'status', 'last_restocked']

    def validate(self, data):
        min_stock = data.get('min_stock', 0)
        max_stock = data.get('max_stock', 0)
        stock_level = data.get('stock_level', 0)

        if min_stock >= max_stock:
            raise serializers.ValidationError({
                "min_stock": "Minimum stock must be less than maximum stock."
            })

        if stock_level < 0:
            raise serializers.ValidationError({
                "stock_level": "Stock level cannot be negative."
            })

        if data.get('cost_per_unit', 0) < 0:
            raise serializers.ValidationError({
                "cost_per_unit": "Cost per unit cannot be negative."
            })

        if data.get('total_value', 0) < 0:
            raise serializers.ValidationError({
                "total_value": "Total value cannot be negative."
            })

        if data.get('last_restocked') and data['last_restocked'] > date.today():
            raise serializers.ValidationError({
                "last_restocked": "Restock date cannot be in the future."
            })

        return data


# purchase order
class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    total_cost = serializers.ReadOnlyField()

    class Meta:
        model = PurchaseOrderItem
        fields = ['slug', 'order', 'item', 'quantity', 'cost_per_unit', 'total_cost']

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0.")
        return value

    def validate_cost_per_unit(self, value):
        if value <= 0:
            raise serializers.ValidationError("Cost per unit must be greater than 0.")
        return value


class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = PurchaseOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = ['slug', 'supplier', 'status', 'created_at', 'items']

    def validate_status(self, value):
        valid_status = ["Pending", "Completed", "Cancelled"]
        if value not in valid_status:
            raise serializers.ValidationError(f"Invalid status. Choose from {valid_status}.")
        return value
